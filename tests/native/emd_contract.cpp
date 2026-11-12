#include <emd/execution.hpp>
#include <cmath>
#include <future>
#include <iostream>
#include <stdexcept>

namespace {
using namespace cnn_compute;

std::span< const double > view(const core::Array &x) {
    return { x.data( ), static_cast< std::size_t >(x.size( )) };
}
std::span< double > output(core::Array &x) {
    return { x.data( ), static_cast< std::size_t >(x.size( )) };
}
void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}
core::Array signal(std::size_t n) {
    core::Array result(n);
    for (std::size_t i = 0; i < n; ++i) {
        const double t = static_cast< double >(i) / n;
        result[i]      = std::sin(6.283185307179586 * 23.0 * t)
                         + .3 * std::cos(6.283185307179586 * 5.0 * t) + .1 * t;
    }
    return result;
}
void equal(const core::Array &actual, const core::Array &expected, const char *message) {
    require(actual.size( ) == expected.size( ), message);
    require((actual - expected).abs( ).maxCoeff( ) < 1e-12, message);
}
emd::Options options( ) {
    emd::Options result;
    result.max_imfs               = 3;
    result.imf.stop_method        = emd::StopMethod::fixed;
    result.imf.max_iters          = 4;
    result.envelope.interpolation = interpolation::Method::pchip;
    return result;
}
void check_workspace_reuse( ) {
    emd::Workspace workspace;
    auto           config = options( );
    const auto     first = signal(512), original = first;
    auto           preserved = emd::get_next_imf(view(first), config.imf, config.envelope);
    const auto     snapshot  = preserved.imf;
    for (std::size_t n : { 512u, 2048u, 128u, 512u }) {
        auto        input    = signal(n);
        auto        expected = emd::get_next_imf(view(input), config.imf, config.envelope);
        core::Array actual(n);
        const auto  info = emd::execution::get_next_imf(view(input), output(actual), config.imf,
                                                        config.envelope, workspace);
        require(info.status == expected.info.status, "execution status mismatch");
        require(info.iterations == expected.info.iterations, "execution iterations mismatch");
        equal(actual, expected.imf, "workspace reuse changed result");
        equal(preserved.imf, snapshot, "later execution overwrote owned output");
    }
    equal(first, original, "input was modified");
    {
        emd::Workspace temporary;
        auto           result = emd::execution::sift(view(first), config, temporary);
        preserved.imf         = result.components.front( );
    }
    require(preserved.imf.isFinite( ).all( ), "result owner did not outlive workspace");
}
void check_failure_recovery( ) {
    auto           input  = signal(512);
    auto           config = options( );
    emd::Workspace workspace;
    core::Array    actual(input.size( ));
    auto           failing = config.imf;
    failing.stop_method    = emd::StopMethod::sd;
    failing.sd_thresh      = 1e-300;
    failing.max_iters      = 1;
    auto info              = emd::execution::get_next_imf(view(input), output(actual), failing, config.envelope, workspace);
    require(info.status == emd::Status::iteration_limit, "iteration-limit status was lost");
    emd::execution::get_next_imf(view(input), output(actual), config.imf, config.envelope, workspace);
    equal(actual, emd::get_next_imf(view(input), config.imf, config.envelope).imf,
          "workspace cannot recover after iteration limit");
    core::Array monotonic    = core::Array::LinSpaced(64, 0.0, 1.0);
    auto        insufficient = emd::sift(view(monotonic), config);
    require(insufficient.status == emd::Status::insufficient_extrema, "insufficient extrema disguised as success");
    equal(insufficient.components.front( ), monotonic, "insufficient extrema lost residual");
}
void check_decomposition_and_concurrency( ) {
    const auto input    = signal(512);
    const auto config   = options( );
    const auto expected = emd::sift(view(input), config);
    auto       task     = [&]( ) {
        emd::Workspace workspace;
        return emd::execution::sift(view(input), config, workspace);
    };
    auto a = std::async(std::launch::async, task), b = std::async(std::launch::async, task);
    for (auto result : { a.get( ), b.get( ) }) {
        require(result.status == expected.status, "concurrent status changed");
        require(result.components.size( ) == expected.components.size( ), "concurrent mode count changed");
        core::Array reconstructed = core::Array::Zero(input.size( ));
        for (std::size_t i = 0; i < result.components.size( ); ++i) {
            equal(result.components[i], expected.components[i], "concurrent independent workspace changed output");
            reconstructed += result.components[i];
        }
        equal(reconstructed, input, "decomposition lost reconstruction");
    }
}
}    // namespace

int main( ) {
    try {
        check_workspace_reuse( );
        check_failure_recovery( );
        check_decomposition_and_concurrency( );
        std::cout << "PASS: C++ public/execution, ownership, workspace reuse, failure recovery, concurrency\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what( ) << '\n';
        return 1;
    }
}
