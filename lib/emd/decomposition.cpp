#include <emd/execution.hpp>

// 行为参照本地 emd 0.8.1 sift.py；GPL 归属见 ../LICENSE.emd。
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace cnn_compute::emd {
namespace {
    std::span< const double > view(const Array &x) {
        return { x.data( ), static_cast< std::size_t >(x.size( )) };
    }
    std::span< double > write(Array &x) {
        return { x.data( ), static_cast< std::size_t >(x.size( )) };
    }

    // 与 NumPy 连续 double 归约的八路累加/128点分块次序一致。
    template < class F >
    double pairwise(std::size_t n, const F &value, std::size_t offset = 0) {
        if (n < 8) {
            double result = -0.0;
            for (std::size_t i = 0; i < n; ++i) result += value(offset + i);
            return result;
        }
        if (n <= 128) {
            double r[8];
            for (int i = 0; i < 8; ++i) r[i] = value(offset + i);
            std::size_t i = 8;
            for (; i + 7 < n; i += 8)
                for (int j = 0; j < 8; ++j) r[j] += value(offset + i + j);
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
        std::size_t above = 0;
        bool        high  = false;
        for (std::size_t i = 0; i < upper.size( ); ++i) {
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

    NextInfo get_next_imf(std::span< const double > signal, std::span< double > output,
                          const IMFOptions &options, const envelope::Options &envelope_options,
                          Workspace &w) {
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
            if (!envelope::execution::extrema_envelopes(view(w.current), write(w.upper), write(w.lower),
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

    bool check_continue(std::span< const double > original, std::span< const double > residual,
                        int layer, const Options &options, Workspace &w, bool initial) {
        const auto [maxima, minima] = envelope::execution::count_extrema(residual);
        bool result                 = !(options.max_imfs && layer == options.max_imfs) && maxima >= 2 && minima >= 2;
        if (!initial) {
            if (options.sift_thresh && absolute_sum(residual) < *options.sift_thresh) result = false;
            if (options.energy_thresh && energy_difference(original, residual) > *options.energy_thresh) result = false;
        }
        if (options.rilling_thresh && maxima >= 2 && minima >= 2) {
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
            const NextInfo info = get_next_imf(view(w.residual), write(next), options.imf, options.envelope, w);
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
