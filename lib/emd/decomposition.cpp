#include <emd/execution.hpp>

// 行为参照本地 emd 0.8.1 sift.py；GPL 归属见 ../LICENSE.emd。
#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdint>
#include <stdexcept>

namespace cnn_compute::emd {
namespace {
    using Packet         = Eigen::internal::packet_traits< double >::type;
    constexpr auto lanes = Eigen::internal::unpacket_traits< Packet >::size;

    std::span< const double > view(const Array &x) {
        return { x.data( ), static_cast< std::size_t >(x.size( )) };
    }
    std::span< double > write(Array &x) {
        return { x.data( ), static_cast< std::size_t >(x.size( )) };
    }

    // 与 NumPy 连续 double 归约的八路累加/128点分块次序一致；八路累加器
    // 按 packet 宽度分组进包（SSE2 四包、AVX2 两包），各 lane 的加法序列
    // 与标量八路相同，树归约保持标量。
    template < class F >
    double pairwise(std::size_t n, const F &value, std::size_t offset = 0) {
        if (n < 8) {
            double result = -0.0;
            for (std::size_t i = 0; i < n; ++i) result += value(offset + i);
            return result;
        }
        if (n <= 128) {
            constexpr auto groups = 8 / lanes;
            static_assert(8 % lanes == 0, "八路累加器须整除 packet 宽度");
            double r[8];
            for (int i = 0; i < 8; ++i) r[i] = value(offset + i);
            Packet accumulators[groups];
            for (int g = 0; g < groups; ++g)
                accumulators[g] = Eigen::internal::ploadu< Packet >(r + g * lanes);
            double      block[8];
            std::size_t i = 8;
            for (; i + 7 < n; i += 8) {
                for (int b = 0; b < 8; ++b) block[b] = value(offset + i + b);
                for (int g = 0; g < groups; ++g)
                    accumulators[g] = Eigen::internal::padd(
                        accumulators[g], Eigen::internal::ploadu< Packet >(block + g * lanes));
            }
            for (int g = 0; g < groups; ++g)
                Eigen::internal::pstoreu(r + g * lanes, accumulators[g]);
            double result = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
            for (; i < n; ++i) result += value(offset + i);
            return result;
        }
        const auto half = (n / 2) - (n / 2) % 8;
        return pairwise(half, value, offset) + pairwise(n - half, value, offset + half);
    }
    double squares(std::span< const double > x) {
        return pairwise(x.size( ), [&](std::size_t i) { return x[i] * x[i]; });
    }
    double absolute_sum(std::span< const double > x) {
        return pairwise(x.size( ), [&](std::size_t i) { return std::abs(x[i]); });
    }
    bool rilling_stop(std::span< const double > upper, std::span< const double > lower,
                      const std::array< double, 3 > &threshold) {
        // packet 层无 double pcmp_gt；ratio>t 等价 t<ratio，两序 NaN 均为假。
        // 掩码 lane 为全 1 或全 0，按整数位计数。
        const Packet two            = Eigen::internal::pset1< Packet >(2.0);
        const Packet low            = Eigen::internal::pset1< Packet >(threshold[0]);
        const Packet high_threshold = Eigen::internal::pset1< Packet >(threshold[1]);
        double       mask[lanes];
        std::size_t  above = 0;
        bool         high  = false;
        const auto   count = upper.size( );
        const auto   full  = count / lanes * lanes;
        std::size_t  i     = 0;
        for (; i + lanes <= count; i += lanes) {
            const Packet u         = Eigen::internal::ploadu< Packet >(upper.data( ) + i);
            const Packet l         = Eigen::internal::ploadu< Packet >(lower.data( ) + i);
            const Packet mean      = Eigen::internal::pdiv(Eigen::internal::padd(u, l), two);
            const Packet amplitude = Eigen::internal::pdiv(
                Eigen::internal::pabs(Eigen::internal::psub(u, l)), two);
            const Packet ratio = Eigen::internal::pdiv(Eigen::internal::pabs(mean), amplitude);
            Eigen::internal::pstoreu(mask, Eigen::internal::pcmp_lt(low, ratio));
            for (int lane = 0; lane < lanes; ++lane)
                above += std::bit_cast< std::int64_t >(mask[lane]) != 0;
            Eigen::internal::pstoreu(mask, Eigen::internal::pcmp_lt(high_threshold, ratio));
            for (int lane = 0; lane < lanes; ++lane)
                high = high || std::bit_cast< std::int64_t >(mask[lane]) != 0;
        }
        for (; i < count; ++i) {
            const double mean      = (upper[i] + lower[i]) / 2.0;
            const double amplitude = std::abs(upper[i] - lower[i]) / 2.0;
            const double ratio     = std::abs(mean) / amplitude;
            above += ratio > threshold[0];
            high = high || ratio > threshold[1];
        }
        return !(static_cast< double >(above) / upper.size( ) > threshold[2] || high);
    }
    void validate_input(std::span< const double > signal) {
        if (signal.size( ) < 3) throw std::invalid_argument("EMD 输入至少三个采样点");
        for (double value : signal)
            if (!std::isfinite(value)) throw std::invalid_argument("EMD 输入必须有限");
    }
}    // namespace

void Workspace::prepare(std::size_t samples, int pad_width) {
    for (auto *item : { &current, &updated, &upper, &lower, &average, &residual }) item->resize(samples);
    envelope.prepare(samples, pad_width);
}
void validate(const IMFOptions &options, const envelope::Options &envelope_options) {
    if (!std::isfinite(options.env_step_size) || options.env_step_size <= 0.0
        || options.env_step_size > 1.0 || options.max_iters <= 0
        || !std::isfinite(options.sd_thresh) || options.sd_thresh <= 0.0
        || !std::isfinite(options.energy_thresh)) throw std::invalid_argument("IMF 参数无效");
    const auto &t = options.rilling_thresh;
    if (!std::isfinite(t[0]) || !std::isfinite(t[1]) || !std::isfinite(t[2])
        || t[0] <= 0 || t[1] < t[0] || t[2] < 0 || t[2] > 1)
        throw std::invalid_argument("Rilling 阈值无效");
    if (envelope_options.pad_width < 1)
        throw std::invalid_argument("完整输入包络要求正延拓宽度");
    if (envelope_options.padding == envelope::Padding::rilling && envelope_options.parabolic_extrema)
        throw std::invalid_argument("参考实现不支持 Rilling 与抛物线极值组合");
}
void validate(const Options &options) {
    validate(options.imf, options.envelope);
    if (options.max_imfs < 0 || (options.sift_thresh && (!std::isfinite(*options.sift_thresh) || *options.sift_thresh < 0)) || (options.energy_thresh && !std::isfinite(*options.energy_thresh)))
        throw std::invalid_argument("EMD 参数无效");
    if (options.rilling_thresh) {
        const auto &t = *options.rilling_thresh;
        if (!std::isfinite(t[0]) || !std::isfinite(t[1]) || !std::isfinite(t[2])
            || t[0] <= 0 || t[1] < t[0] || t[2] < 0 || t[2] > 1)
            throw std::invalid_argument("外层 Rilling 阈值无效");
    }
}

namespace execution {
    double sum(std::span< const double > signal) {
        return pairwise(signal.size( ), [&](std::size_t i) { return signal[i]; });
    }
    double standard_deviation(std::span< const double > signal) {
        const double mean     = sum(signal) / signal.size( );
        const double variance = pairwise(signal.size( ), [&](std::size_t i) {
                                    const double delta = signal[i] - mean;
                                    return delta * delta;
                                })
                                / signal.size( );
        return std::sqrt(variance);
    }
    double energy_difference(std::span< const double > signal, std::span< const double > residual) {
        return 20.0 * std::log10(squares(signal)) - 20.0 * std::log10(squares(residual));
    }

    // envelopes_ready 只由同一 sift 调用中紧邻的继续检查提供；不把有效性存入工作区。
    static NextInfo extract_imf(std::span< const double > signal, std::span< double > output,
                                const IMFOptions &options, const envelope::Options &envelope_options,
                                Workspace &w, bool envelopes_ready) {
        w.prepare(signal.size( ), envelope_options.pad_width);
        w.current = core::Map(signal.data( ), signal.size( ));
        NextInfo info;
        while (true) {
            // 上游先判断 niters>max_iters，再递增，故最多执行 max_iters+1 轮。
            if (options.stop_method != StopMethod::fixed && info.iterations > options.max_iters) {
                info.status = Status::iteration_limit;
                break;
            }
            ++info.iterations;
            const bool envelopes = envelopes_ready;
            envelopes_ready      = false;
            if (!envelopes
                && !envelope::execution::extrema_envelopes(view(w.current), write(w.upper), write(w.lower),
                                                           envelope_options, w.envelope)) {
                info.continue_flag = false;
                info.status        = Status::insufficient_extrema;
                break;
            }
            w.average = (w.upper + w.lower) / 2.0;
            w.updated = w.current - options.env_step_size * w.average;
            bool stop = false;
            if (options.stop_method == StopMethod::sd) {
                const double numerator = pairwise(signal.size( ), [&](std::size_t i) {
                    const double delta = w.updated[i] - w.current[i];
                    return delta * delta;
                });
                stop                   = numerator / squares(view(w.updated)) < options.sd_thresh;
            } else if (options.stop_method == StopMethod::rilling) {
                stop = rilling_stop(view(w.upper), view(w.lower), options.rilling_thresh);
                if (stop) break;    // Rilling 接受更新前 proto_imf。
            } else if (options.stop_method == StopMethod::energy) {
                stop = energy_difference(signal, view(w.average)) > options.energy_thresh;
            } else
                stop = info.iterations == options.max_iters;
            w.current.swap(w.updated);
            if (stop) break;
        }
        if (!w.current.isFinite( ).all( )) info.status = Status::numerical_failure;
        std::copy_n(w.current.data( ), signal.size( ), output.data( ));
        return info;
    }

    NextInfo get_next_imf(std::span< const double > signal, std::span< double > output,
                          const IMFOptions &options, const envelope::Options &envelope_options,
                          Workspace &w) {
        return extract_imf(signal, output, options, envelope_options, w, false);
    }

    bool check_continue(std::span< const double > original, std::span< const double > residual,
                        int layer, const Options &options, Workspace &w, bool initial) {
        const auto [maxima, minima] = envelope::execution::count_extrema(residual);
        bool result                 = !(options.max_imfs && layer == options.max_imfs) && maxima >= 2 && minima >= 2;
        if (!initial) {
            if (options.sift_thresh && absolute_sum(residual) < *options.sift_thresh) result = false;
            if (options.energy_thresh && energy_difference(original, residual) > *options.energy_thresh) result = false;
        }
        if (result && options.rilling_thresh) {
            envelope::execution::extrema_envelopes(residual, write(w.upper), write(w.lower), options.envelope, w.envelope);
            // emd 0.8.1 check_sift_continue 忽略用户阈值内容，使用默认Rilling值，且反向使用stop标志。
            result = result && rilling_stop(view(w.upper), view(w.lower), { 0.05, 0.5, 0.05 });
        }
        return result;
    }

    Result sift(std::span< const double > signal, const Options &options, Workspace &w) {
        w.prepare(signal.size( ), options.envelope.pad_width);
        w.residual = core::Map(signal.data( ), signal.size( ));
        Result result;
        int    layer = 0;
        bool   more  = check_continue(signal, view(w.residual), layer, options, w, true);
        if (!more) {
            result.status = Status::insufficient_extrema;
            result.components.emplace_back(w.residual);
            return result;    // 上游此边界会引用未定义imf；明确返回不可判定原残差。
        }
        while (more) {
            Array          next(signal.size( ));
            const NextInfo info = extract_imf(view(w.residual), write(next), options.imf,
                                              options.envelope, w, options.rilling_thresh.has_value( ));
            result.components.push_back(std::move(next));
            result.iterations.push_back(info.iterations);
            if (info.status == Status::iteration_limit || info.status == Status::numerical_failure) {
                result.status = info.status;
                return result;
            }
            // 残差递推与数学定义等价，避免每阶重扫全部已提取模态。
            w.residual -= result.components.back( );
            ++layer;
            more = check_continue(signal, view(w.residual), layer, options, w);
        }
        if (absolute_sum(view(w.residual)) != 0.0) result.components.emplace_back(w.residual);
        return result;
    }
}    // namespace execution

NextResult get_next_imf(std::span< const double > signal, const IMFOptions &options,
                        const envelope::Options &envelope_options) {
    validate_input(signal);
    validate(options, envelope_options);
    NextResult result{ Array(signal.size( )), {} };
    Workspace  w;
    result.info = execution::get_next_imf(signal, write(result.imf), options, envelope_options, w);
    return result;
}
Result sift(std::span< const double > signal, const Options &options) {
    validate_input(signal);
    validate(options);
    Workspace w;
    return execution::sift(signal, options, w);
}
}    // namespace cnn_compute::emd
