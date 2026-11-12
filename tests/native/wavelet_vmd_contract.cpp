#include <wavelet/api.hpp>
#include <vmd/api.hpp>
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <vector>

namespace {
void require(bool condition) { if (!condition) throw std::runtime_error("native wavelet/VMD contract failed"); }
bool close(double a, double b) { return std::abs(a - b) < 1e-9; }
}
int main() {
    using namespace cnn_compute;
    std::vector<double> signal(1025);
    for (std::size_t i = 0; i < signal.size(); ++i)
        signal[i] = std::sin(2 * 3.141592653589793 * 30 * i / 1024)
                    + 0.6 * std::sin(2 * 3.141592653589793 * 150 * i / 1024);
    const wavelet::Plan plan("db8");
    wavelet::Coefficients coefficients;
    wavelet::Workspace wavelet_workspace;
    wavelet::prepare_coefficients(coefficients, plan, signal.size(), 3, true);
    wavelet_workspace.prepare(plan, signal.size(), 3, true);
    auto* scratch = wavelet_workspace.first.data();
    auto* leaf = coefficients.bands[0].data();
    wavelet::decompose_into(signal, plan, coefficients, wavelet_workspace);
    auto retained = wavelet::reconstruct(coefficients, plan);
    for (std::size_t i = 0; i < signal.size(); ++i) require(close(retained[i], signal[i]));
    wavelet::decompose_into(signal, plan, coefficients, wavelet_workspace);
    require(scratch == wavelet_workspace.first.data() && leaf == coefficients.bands[0].data());
    std::vector<double> component(signal.size());
    wavelet::reconstruct_component_into(coefficients, 3, plan, component, wavelet_workspace);
    const std::vector<std::size_t> selected{3};
    const auto public_component = wavelet::reconstruct_selected(coefficients, plan, selected);
    for (std::size_t i = 0; i < signal.size(); ++i) require(close(component[i], public_component[i]));

    vmd::Parameters parameters;
    parameters.modes = 2;
    parameters.max_samples = 0;
    vmd::Workspace workspace;
    workspace.prepare(signal.size(), parameters.modes);
    vmd::Result result;
    vmd::prepare_result(result, signal.size(), parameters);
    auto* current = workspace.current.data();
    auto* previous = workspace.previous.data();
    vmd::execute(signal, 1024, parameters, result, workspace);
    const auto saved = result.modes;
    auto* output = result.modes.data();
    vmd::execute(signal, 1024, parameters, result, workspace);
    require(result.modes.data() == output);
    require((workspace.current.data() == current || workspace.current.data() == previous)
            && (workspace.previous.data() == current || workspace.previous.data() == previous));
    require((result.modes - saved).abs().maxCoeff() == 0);
    const auto public_result = vmd::decompose(signal, 1024, parameters);
    require((result.modes - public_result.modes).abs().maxCoeff() == 0);
    std::fill(signal.begin(), signal.end(), 1.0);
    vmd::execute(signal, 1024, parameters, result, workspace);
    require(result.status == "indeterminate" && result.modes.size() == 0
            && result.center_frequencies_hz.size() == 0 && result.center_frequency_history_hz.size() == 0);
    require(saved.size() == 2050 && saved.abs().maxCoeff() > 0);
    // 工作区可准备为新规模；结果失败清空后按契约重新准备。
    workspace.prepare(512, parameters.modes);
    vmd::prepare_result(result, 512, parameters);
    vmd::execute(std::span<const double>(signal.data(), 512), 1024, parameters, result, workspace);
    require(result.residual.size() == 512);
}
