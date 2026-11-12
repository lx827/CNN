#include <emd/mask.hpp>
#include <cmath>
#include <future>
#include <stdexcept>

namespace {
using namespace cnn_compute;
std::span<const double> view(const core::Array& x) { return {x.data(), static_cast<std::size_t>(x.size())}; }
std::span<double> output(core::Array& x) { return {x.data(), static_cast<std::size_t>(x.size())}; }
void require(bool result) { if (!result) throw std::runtime_error("mask 工作区契约失败"); }
core::Array signal(std::size_t count) {
    core::Array result(count);
    for (std::size_t i = 0; i < count; ++i)
        result[i] = std::cos(6.283185307179586 * .17 * i)
            + .35 * std::cos(6.283185307179586 * .052 * i);
    return result;
}
void check_reuse() {
    emd::MaskOptions options;
    options.max_imfs = 2;
    options.mask_freqs = {.2, .07};
    options.imf.stop_method = emd::StopMethod::fixed;
    options.imf.max_iters = 3;
    emd::MaskWorkspace workspace;
    std::vector<core::Array> retained;
    for (std::size_t size : {257u, 512u, 129u}) {
        auto x = signal(size);
        const auto original = x;
        workspace.prepare(size, options.envelope.pad_width);
        auto result = emd::execution::mask_sift(view(x), options, workspace);
        const auto reference = emd::mask_sift(view(x), options);
        require(result.decomposition.components.size() == reference.decomposition.components.size());
        for (std::size_t i = 0; i < result.decomposition.components.size(); ++i) {
            require((result.decomposition.components[i] - reference.decomposition.components[i]).abs().maxCoeff() == 0.0);
        }
        require((x - original).abs().maxCoeff() == 0.0);
        retained.push_back(result.decomposition.components[0]);
        core::Array next(size);
        const auto info = emd::execution::get_next_imf_mask(view(x), output(next), .2, 1., 4,
                                                           options.imf, options.envelope, workspace);
        require(info.status == emd::Status::success);
        auto frequency = transforms::frequency_transform(view(x), 1., false);
        require(frequency.phase.isFinite().all() && frequency.frequency.isFinite().all());
    }
    require(retained[0].size() == 257 && retained[1].size() == 512 && retained[2].size() == 129);
}
}
int main() {
    auto first = std::async(std::launch::async, check_reuse);
    auto second = std::async(std::launch::async, check_reuse);
    first.get(); second.get();
}
