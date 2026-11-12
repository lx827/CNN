#include <emd/ensemble.hpp>
#include <cmath>
#include <future>
#include <iostream>
#include <random>
#include <stdexcept>

namespace {
using namespace cnn_compute;
std::span<const double> view(const core::Array& x) {
    return {x.data(), static_cast<std::size_t>(x.size())};
}
void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
core::Array signal(std::size_t n) {
    core::Array result(n);
    for (std::size_t i = 0; i < n; ++i) {
        const double t = static_cast<double>(i) / n;
        result[i] = std::sin(6.283185307179586 * 19.0 * t)
            + .3 * std::cos(6.283185307179586 * 5.0 * t) + .1 * t;
    }
    return result;
}
core::Array noise(std::size_t n, int trials) {
    core::Array result(n * static_cast<std::size_t>(trials));
    std::mt19937 generator(20261112);
    std::normal_distribution<double> normal;
    for (auto& value : result) value = normal(generator);
    return result;
}
emd::Options options() {
    emd::Options result;
    result.max_imfs = 2;
    result.imf.stop_method = emd::StopMethod::fixed;
    result.imf.max_iters = 4;
    result.envelope.interpolation = interpolation::Method::pchip;
    return result;
}
void equal(const emd::Result& actual, const emd::Result& expected) {
    require(actual.status == expected.status, "ensemble status changed");
    require(actual.components.size() == expected.components.size(), "ensemble column count changed");
    require(actual.iterations.empty(), "aggregate fabricated a single sift iteration count");
    for (std::size_t column = 0; column < actual.components.size(); ++column) {
        require(actual.components[column].size() == expected.components[column].size(), "ensemble sample count changed");
        require((actual.components[column] == expected.components[column]).all(), "ensemble output changed");
    }
}
void workspace_and_owners() {
    emd::EnsembleOptions config;
    config.sift = options();
    config.nensembles = 3;
    emd::EnsembleWorkspace workspace;
    const auto original = signal(256), normal = noise(256, config.nensembles);
    auto owned = emd::execution::ensemble_sift(view(original), view(normal), config, workspace);
    const auto saved = owned;
    for (std::size_t n : {256u, 1024u, 127u, 256u}) {
        const auto input = signal(n), noisy = noise(n, config.nensembles);
        equal(emd::execution::ensemble_sift(view(input), view(noisy), config, workspace),
              emd::ensemble_sift(view(input), view(noisy), config));
        equal(owned, saved);
    }
    emd::CompleteEnsembleOptions complete;
    complete.sift = config.sift;
    complete.nensembles = config.nensembles;
    for (std::size_t n : {256u, 127u, 512u}) {
        const auto input = signal(n), noisy = noise(n, complete.nensembles);
        equal(emd::execution::complete_ensemble_sift(view(input), view(noisy), complete, workspace),
              emd::complete_ensemble_sift(view(input), view(noisy), complete));
    }
    {
        emd::EnsembleWorkspace temporary;
        owned = emd::execution::ensemble_sift(view(original), view(normal), config, temporary);
    }
    equal(owned, saved);
    require((original == signal(256)).all(), "input signal was modified");
    require((normal == noise(256, config.nensembles)).all(), "input noise was modified");
    const auto empty_noise = core::Array::Zero(normal.size()).eval();
    auto failed = emd::execution::complete_ensemble_sift(view(original), view(empty_noise), complete, workspace);
    require(failed.status == emd::Status::numerical_failure, "constant noise disguised as valid zscore");
    equal(emd::execution::complete_ensemble_sift(view(original), view(normal), complete, workspace),
          emd::complete_ensemble_sift(view(original), view(normal), complete));
}
void concurrent_calls() {
    const auto input = signal(256), normal = noise(256, 3);
    emd::EnsembleOptions config;
    config.sift = options();
    config.nensembles = 3;
    auto expected = emd::ensemble_sift(view(input), view(normal), config);
    auto task = [&]() {
        emd::EnsembleWorkspace workspace;
        return emd::execution::ensemble_sift(view(input), view(normal), config, workspace);
    };
    auto first = std::async(std::launch::async, task);
    auto second = std::async(std::launch::async, task);
    equal(first.get(), expected);
    equal(second.get(), expected);
}
}
int main() {
    try {
        workspace_and_owners(); concurrent_calls();
        std::cout << "PASS: ensemble execution reuse, independent owners, failure recovery, concurrency\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
