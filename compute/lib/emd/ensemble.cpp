// emd 0.8.1 sift.py 的集成算法适配；实际随包许可证与归属见 lib/LICENSE.emd。
#include <emd/ensemble.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <stdexcept>
#include <utility>

namespace cnn_compute::emd {
namespace {

    std::span< const double > view(const Array &values) {
        return { values.data( ), static_cast< std::size_t >(values.size( )) };
    }
    std::span< double > writable(Array &values) {
        return { values.data( ), static_cast< std::size_t >(values.size( )) };
    }

    bool failed(Status status) {
        return status == Status::iteration_limit || status == Status::numerical_failure;
    }
    Result failure(Status status) {
        Result result;
        result.status = status;
        return result;
    }

    void validate_ensemble(int count, double amplitude) {
        if (count <= 0 || !std::isfinite(amplitude) || amplitude < 0.0)
            throw std::invalid_argument("集成次数必须为正，噪声幅值必须有限且非负");
    }
    void validate_input(std::span< const double > signal, std::span< const double > noise,
                        int count) {
        if (signal.size( ) < 3) throw std::invalid_argument("集成分解输入至少三个采样点");
        if (noise.size( ) / signal.size( ) != static_cast< std::size_t >(count)
            || noise.size( ) % signal.size( ) != 0)
            throw std::invalid_argument("标准正态噪声必须按 nensembles × samples 逐行排列");
        if (!std::all_of(signal.begin( ), signal.end( ), [](double x) { return std::isfinite(x); })
            || !std::all_of(noise.begin( ), noise.end( ), [](double x) { return std::isfinite(x); }))
            throw std::invalid_argument("集成分解输入和噪声必须有限");
    }

}    // namespace

void EnsembleWorkspace::prepare(std::size_t samples, int nensembles, int pad_width) {
    const auto size = static_cast< Eigen::Index >(samples);
    trial.resize(size);
    next.resize(size);
    normalized.resize(size);
    white_noise.resize(size);
    local_mean.resize(size);
    previous.resize(size);
    accumulator.resize(size);
    members.resize(static_cast< std::size_t >(nensembles));
    sift.prepare(samples, pad_width);
}

void validate(const EnsembleOptions &options) {
    validate(options.sift);
    validate_ensemble(options.nensembles, options.ensemble_noise);
    if (!options.sift.energy_thresh || *options.sift.energy_thresh != 50.0
        || options.sift.rilling_thresh)
        throw std::invalid_argument("ensemble_sift 的外层 energy_thresh 固定为 50，rilling_thresh 为空");
    if (options.noise_mode != NoiseMode::single && options.noise_mode != NoiseMode::flip)
        throw std::invalid_argument("无效集成噪声模式");
}
void validate(const CompleteEnsembleOptions &options) {
    validate(options.sift);
    validate_ensemble(options.nensembles, options.ensemble_noise);
}

Result ensemble_sift(std::span< const double > signal, std::span< const double > normal_noise,
                     const EnsembleOptions &options) {
    validate(options);
    validate_input(signal, normal_noise, options.nensembles);
    EnsembleWorkspace workspace;
    return execution::ensemble_sift(signal, normal_noise, options, workspace);
}

Result complete_ensemble_sift(std::span< const double >      signal,
                              std::span< const double >      normal_noise,
                              const CompleteEnsembleOptions &options) {
    validate(options);
    validate_input(signal, normal_noise, options.nensembles);
    EnsembleWorkspace workspace;
    return execution::complete_ensemble_sift(signal, normal_noise, options, workspace);
}

namespace execution {

    Result ensemble_sift(std::span< const double > signal, std::span< const double > normal_noise,
                         const EnsembleOptions &options, EnsembleWorkspace &workspace) {
        const auto samples = signal.size( );
        workspace.prepare(samples, options.nensembles, options.sift.envelope.pad_width);
        const core::Map              original(signal.data( ), static_cast< Eigen::Index >(samples));
        const double                 noise_scaling = standard_deviation(signal) * options.ensemble_noise;
        std::map< std::size_t, int > counts;

        for (int member = 0; member < options.nensembles; ++member) {
            const core::Map noise(normal_noise.data( ) + static_cast< std::size_t >(member) * samples,
                                  static_cast< Eigen::Index >(samples));
            workspace.trial = noise * noise_scaling;
            workspace.trial += original;
            auto result = execution::sift(view(workspace.trial), options.sift, workspace.sift);
            if (result.status != Status::success) return failure(result.status);

            if (options.noise_mode == NoiseMode::flip) {
                workspace.trial = noise * noise_scaling;
                workspace.trial = original - workspace.trial;
                auto flipped    = execution::sift(view(workspace.trial), options.sift, workspace.sift);
                if (flipped.status != Status::success) return failure(flipped.status);
                const auto columns = result.components.size( );
                if (flipped.components.size( ) != columns && flipped.components.size( ) != 1)
                    throw std::invalid_argument("正负噪声分解的模态列数不满足上游原位广播规则");
                for (std::size_t column = 0; column < columns; ++column) {
                    const auto other = flipped.components.size( ) == 1 ? 0 : column;
                    result.components[column] += flipped.components[other];
                    result.components[column] /= 2.0;
                }
            }
            ++counts[result.components.size( )];
            workspace.members[static_cast< std::size_t >(member)] = std::move(result);
        }

        // np.unique 排序，argmax 在并列时选择最小列数。
        std::size_t target        = 0;
        int         largest_group = -1;
        for (const auto &[columns, count] : counts)
            if (count > largest_group) {
                target        = columns;
                largest_group = count;
            }
        if (options.sift.max_imfs > 0)
            target = std::min(target, static_cast< std::size_t >(options.sift.max_imfs));

        Result result;
        result.components.reserve(target);
        for (std::size_t column = 0; column < target; ++column) {
            workspace.accumulator.setZero( );
            int retained = 0;
            for (const auto &member : workspace.members)
                if (member.components.size( ) >= target) {
                    workspace.accumulator += member.components[column];
                    ++retained;
                }
            // NumPy 对非连续集成轴顺序累加，最后除以成员数。
            workspace.accumulator /= static_cast< double >(retained);
            result.components.emplace_back(workspace.accumulator);
        }
        return result;
    }

    Result complete_ensemble_sift(std::span< const double >      signal,
                                  std::span< const double >      normal_noise,
                                  const CompleteEnsembleOptions &options,
                                  EnsembleWorkspace             &workspace) {
        const auto samples = signal.size( );
        workspace.prepare(samples, options.nensembles, options.sift.envelope.pad_width);
        const double input_std = standard_deviation(signal);
        if (input_std == 0.0 || !std::isfinite(input_std))
            return failure(Status::numerical_failure);
        workspace.normalized = core::Map(signal.data( ), static_cast< Eigen::Index >(samples)) / input_std;

        // 上游对白噪声完整 sift，不沿用目标信号的 max_imfs/外层终止参数。
        Options noise_options;
        noise_options.imf      = options.sift.imf;
        noise_options.envelope = options.sift.envelope;
        for (int member = 0; member < options.nensembles; ++member) {
            const auto   row       = normal_noise.subspan(static_cast< std::size_t >(member) * samples, samples);
            const double mean      = execution::sum(row) / static_cast< double >(samples);
            const double deviation = standard_deviation(row);
            if (deviation <= std::abs(std::numeric_limits< double >::epsilon( ) * mean))
                return failure(Status::numerical_failure);
            workspace.white_noise = core::Map(row.data( ), static_cast< Eigen::Index >(samples));
            workspace.white_noise -= mean;
            workspace.white_noise /= deviation;
            auto noise_modes = execution::sift(view(workspace.white_noise), noise_options, workspace.sift);
            if (noise_modes.status != Status::success) return failure(noise_modes.status);
            workspace.members[static_cast< std::size_t >(member)] = std::move(noise_modes);
        }

        workspace.accumulator.setZero( );
        for (const auto &member : workspace.members) {
            if (member.components.empty( ))
                throw std::out_of_range("complete ensemble 白噪声缺少第一模态");
            const auto  &first     = member.components.front( );
            const double deviation = standard_deviation(view(first));
            if (deviation == 0.0 || !std::isfinite(deviation))
                return failure(Status::numerical_failure);
            // 保留 ensemble_noise * IMF / std 的运算次序。
            workspace.trial = first * options.ensemble_noise;
            workspace.trial /= deviation;
            workspace.trial += workspace.normalized;
            const auto info = execution::get_next_imf(view(workspace.trial), writable(workspace.next),
                                                      options.sift.imf, options.sift.envelope,
                                                      workspace.sift);
            if (failed(info.status)) return failure(info.status);
            workspace.accumulator += workspace.trial - workspace.next;
        }
        workspace.local_mean = workspace.accumulator / static_cast< double >(options.nensembles);
        Result result;
        result.components.emplace_back(workspace.normalized - workspace.local_mean);

        int  layer      = 1;
        bool keep_going = execution::check_continue(view(workspace.normalized), view(workspace.local_mean),
                                                    layer, options.sift, workspace.sift);
        while (keep_going) {
            workspace.previous     = workspace.local_mean;
            const double local_std = standard_deviation(view(workspace.previous));
            workspace.accumulator.setZero( );
            for (const auto &member : workspace.members) {
                if (member.components.size( ) <= static_cast< std::size_t >(layer))
                    throw std::out_of_range("complete ensemble 白噪声模态不足，无法访问当前层");
                // 上游 snrflag 固定为 1，后续噪声模态不逐层标准化。
                workspace.trial = member.components[static_cast< std::size_t >(layer)] * options.ensemble_noise;
                workspace.trial *= local_std;
                workspace.trial += workspace.previous;
                const auto info = execution::get_next_imf(view(workspace.trial), writable(workspace.next),
                                                          options.sift.imf, options.sift.envelope,
                                                          workspace.sift);
                if (failed(info.status)) return failure(info.status);
                workspace.accumulator += workspace.trial - workspace.next;
            }
            workspace.local_mean = workspace.accumulator / static_cast< double >(options.nensembles);
            result.components.emplace_back(workspace.previous - workspace.local_mean);
            // layer 表示已经生成的 IMF 数，先递增再检查真实模态上限。
            ++layer;
            keep_going = execution::check_continue(view(workspace.normalized), view(workspace.local_mean),
                                                   layer, options.sift, workspace.sift);
        }
        result.components.emplace_back(workspace.local_mean);
        for (auto &component : result.components) component *= input_std;
        return result;
    }

}    // namespace execution
}    // namespace cnn_compute::emd
