#include <emd/family.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <random>
#include <stdexcept>

namespace cnn_compute::emd::family {
namespace {
    using core::Map;
    std::span< const double > view(const Array &x) {
        return { x.data( ), static_cast< std::size_t >(x.size( )) };
    }
    double deviation(const Array &x) {
        return std::sqrt((x - x.mean( )).square( ).mean( ));
    }
    bool oscillating(const Array &x) {
        int maxima = 0, minima = 0;
        for (Eigen::Index i = 1; i + 1 < x.size( ); ++i) {
            const double left = x[i] - x[i - 1], right = x[i + 1] - x[i];
            maxima += left > 0 && right <= 0;
            minima += left < 0 && right >= 0;
            if (maxima >= 2 && minima >= 2) return true;
        }
        return false;
    }

    // 一套多模态计算实现；emit 消费当前 IMF view 与物理幅值因子，
    // 直接写最终数组/聚合，不为每个集成成员分配完整分解结果。
    template < class Emit >
    void extract(const Array &input, int maximum, const SiftParameters &parameters,
                 DecompositionWorkspace &workspace, Emit emit) {
        const double amplitude = input.abs( ).maxCoeff( );
        if (amplitude == 0) return;
        workspace.residual = input / amplitude;
        const double floor = std::numeric_limits< double >::epsilon( ) * deviation(workspace.residual);
        if (floor == 0) return;
        workspace.mode.resize(input.size( ));
        for (int order = 0; order < maximum; ++order) {
            const auto info = emd::execution::sift(view(workspace.residual),
                                                   { workspace.mode.data( ), static_cast< std::size_t >(input.size( )) }, parameters, workspace.sift);
            if (!info || deviation(workspace.mode) <= floor) break;
            workspace.residual -= workspace.mode;
            emit(order, workspace.mode, amplitude, *info);
            if (!oscillating(workspace.residual)) break;
        }
    }

    void append(Result &result, const Array &mode, double scale, SiftInfo info) {
        result.imfs.emplace_back(mode * scale);
        result.iterations.push_back(info.iterations);
        result.converged.push_back(info.converged);
    }
    void accumulate(Result &result, std::vector< int > &members, int order,
                    const Array &mode, double scale, SiftInfo info) {
        if (order == static_cast< int >(result.imfs.size( ))) {
            result.imfs.emplace_back(Array::Zero(mode.size( )));
            result.iterations.push_back(0);
            result.converged.push_back(true);
            members.push_back(0);
        }
        result.imfs[order] += mode * scale;
        result.iterations[order] = std::max(result.iterations[order], info.iterations);
        result.converged[order]  = result.converged[order] && info.converged;
        ++members[order];
    }
    void finite_trial(const Array &x) {
        if (!x.isFinite( ).all( )) throw std::runtime_error("EMD 集成产生非有限值");
    }
    void validate(std::span< const double > signal, Method method, const Options &options) {
        if (signal.size( ) < 8 || !Map(signal.data( ), signal.size( )).isFinite( ).all( ))
            throw std::invalid_argument("EMD 输入必须有限且至少包含 8 个采样点");
        const auto &s                        = options.sift;
        const auto [first, second, fraction] = s.rilling_thresholds;
        if (options.max_imfs <= 0 || s.max_sifts <= 0 || s.mirror_extrema <= 0
            || !std::isfinite(s.sd_threshold) || s.sd_threshold <= 0
            || !std::isfinite(first) || !std::isfinite(second) || !std::isfinite(fraction)
            || first <= 0 || second < first || fraction < 0 || fraction > 1
            || (s.interpolation != core::Interpolation::pchip && s.interpolation != core::Interpolation::cubic)
            || (s.stopping_rule != StoppingRule::sd && s.stopping_rule != StoppingRule::rilling)
            || options.ensemble_size <= 0 || !std::isfinite(options.noise_scale) || options.noise_scale < 0
            || (method != Method::emd && method != Method::eemd && method != Method::ceemdan))
            throw std::invalid_argument("EMD 算法参数无效");
    }
}    // namespace

void execution::decompose(std::span< const double > signal, Method method, const Options &options,
                          std::span< const std::uint32_t > seed, Result &result, Workspace &workspace) {
    result = Result{};
    workspace.members.clear( );
    const Map input(signal.data( ), signal.size( ));
    result.residual   = input;
    const double peak = input.abs( ).maxCoeff( );
    if (peak == 0) {
        result.reason = Reason::zero_variance;
        return;
    }
    workspace.normalized  = input / peak;
    const double unit_std = deviation(workspace.normalized);
    if (unit_std == 0) {
        result.reason = Reason::zero_variance;
        return;
    }
    if (method == Method::emd || options.noise_scale == 0) {
        extract(workspace.normalized, options.max_imfs, options.sift, workspace.decomposition,
                [&](int, const Array &mode, double amplitude, SiftInfo info) {
                    append(result, mode, amplitude * peak, info);
                });
        if (result.imfs.empty( ))
            result.reason = Reason::insufficient_extrema;
        else
            result.residual = workspace.decomposition.residual
                              * workspace.normalized.abs( ).maxCoeff( ) * peak;
    } else {
        const double scale = peak * unit_std;
        workspace.normalized /= unit_std;
        workspace.residual = workspace.normalized;
        workspace.trial.resize(input.size( ));
        const std::uint32_t zero = 0;
        if (seed.empty( )) seed = { &zero, 1 };
        std::seed_seq                      sequence(seed.begin( ), seed.end( ));
        std::mt19937_64                    rng(sequence);
        std::normal_distribution< double > normal;
        if (method == Method::eemd) {
            for (int member = 0; member < options.ensemble_size; ++member) {
                for (Eigen::Index i = 0; i < input.size( ); ++i)
                    workspace.trial[i] = workspace.normalized[i] + options.noise_scale * normal(rng);
                finite_trial(workspace.trial);
                extract(workspace.trial, options.max_imfs, options.sift, workspace.decomposition,
                        [&](int order, const Array &mode, double amplitude, SiftInfo info) {
                            accumulate(result, workspace.members, order, mode, amplitude, info);
                        });
            }
            for (std::size_t i = 0; i < result.imfs.size( ); ++i) {
                result.imfs[i] /= workspace.members[i];
                workspace.residual -= result.imfs[i];
                result.imfs[i] *= scale;
            }
        } else {
            struct Noise {
                Array                white;
                std::vector< Array > modes;
            };
            std::vector< Noise > noises(options.ensemble_size);
            for (auto &noise : noises) {
                noise.white.resize(input.size( ));
                for (auto &value : noise.white) value = normal(rng);
                extract(noise.white, options.max_imfs - 1, options.sift, workspace.decomposition,
                        [&](int, const Array &mode, double, SiftInfo) {
                            const double sigma = deviation(mode);
                            noise.modes.emplace_back(sigma > 0 ? Array(mode / sigma) : Array::Zero(mode.size( )));
                        });
            }
            for (int order = 0; order < options.max_imfs; ++order) {
                const double amplitude = order == 0 ? 1.0 : deviation(workspace.residual);
                for (const auto &noise : noises) {
                    const Array *component = order == 0                                            ? &noise.white
                                             : order - 1 < static_cast< int >(noise.modes.size( )) ? &noise.modes[order - 1]
                                                                                                   : nullptr;
                    if (component)
                        workspace.trial = workspace.residual + options.noise_scale * amplitude * *component;
                    else
                        workspace.trial = workspace.residual;
                    finite_trial(workspace.trial);
                    extract(workspace.trial, 1, options.sift, workspace.decomposition,
                            [&](int, const Array &mode, double factor, SiftInfo info) {
                                accumulate(result, workspace.members, order, mode, factor, info);
                            });
                }
                if (static_cast< int >(result.imfs.size( )) <= order) break;
                auto &mode = result.imfs.back( );
                mode /= workspace.members[order];
                if (deviation(mode) <= std::numeric_limits< double >::epsilon( )) {
                    result.imfs.pop_back( );
                    result.iterations.pop_back( );
                    result.converged.pop_back( );
                    break;
                }
                workspace.residual -= mode;
                mode *= scale;
                if (!oscillating(workspace.residual)) break;
            }
        }
        if (result.imfs.empty( ))
            result.reason = Reason::no_valid_ensemble_member;
        else
            result.residual = workspace.residual * scale;
    }
    if (!result.imfs.empty( ) && !std::all_of(result.converged.begin( ), result.converged.end( ), [](bool x) { return x; }))
        result.reason = Reason::maximum_sifts_reached;
    for (const auto &mode : result.imfs)
        if (!mode.isFinite( ).all( )) throw std::runtime_error("EMD 模态产生非有限值");
    if (!result.residual.isFinite( ).all( )) throw std::runtime_error("EMD 残差产生非有限值");
}

Result decompose(std::span< const double > signal, Method method, const Options &options,
                 std::span< const std::uint32_t > seed) {
    validate(signal, method, options);
    Workspace workspace;
    Result    result;
    execution::decompose(signal, method, options, seed, result, workspace);
    return result;
}

}    // namespace cnn_compute::emd::family
