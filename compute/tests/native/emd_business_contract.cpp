#include <emd/family.hpp>
#include <cmath>
#include <future>
#include <iostream>
#include <random>
#include <stdexcept>

namespace {
using namespace cnn_compute;
namespace family = emd::family;
std::span< const double > view(const core::Array &x) {
    return { x.data( ), static_cast< std::size_t >(x.size( )) };
}
void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}
void close(const core::Array &a, const core::Array &b) {
    require(a.size( ) == b.size( ), "array shape mismatch");
    const double error = (a - b).abs( ).maxCoeff( );
    if (error >= 1e-10) throw std::runtime_error("array mismatch: max=" + std::to_string(error));
}
double sigma(const core::Array &x) {
    return std::sqrt((x - x.mean( )).square( ).mean( ));
}
core::Array signal(int n) {
    core::Array x(n);
    for (int i = 0; i < n; ++i) x[i] = std::sin(6.283185307179586 * 23 * i / n)
                                       + .4 * std::sin(6.283185307179586 * 4 * i / n) + .2 * i / n;
    return x;
}
core::Array reconstruct(const family::Result &r) {
    core::Array x = r.residual;
    for (const auto &imf : r.imfs) x += imf;
    return x;
}
void equal(const family::Result &a, const family::Result &b) {
    require(a.reason == b.reason && a.iterations == b.iterations && a.converged == b.converged
                && a.imfs.size( ) == b.imfs.size( ),
            "metadata mismatch");
    close(a.residual, b.residual);
    for (std::size_t i = 0; i < a.imfs.size( ); ++i) close(a.imfs[i], b.imfs[i]);
}
std::vector< core::Array > noises(int count, int n, const std::vector< std::uint32_t > &seed) {
    std::seed_seq                      sequence(seed.begin( ), seed.end( ));
    std::mt19937_64                    rng(sequence);
    std::normal_distribution< double > normal;
    std::vector< core::Array >         result(count);
    for (auto &x : result) {
        x.resize(n);
        for (auto &value : x) value = normal(rng);
    }
    return result;
}
void formula(family::Method method) {
    const auto        x          = signal(512);
    const core::Array unit       = x / x.abs( ).maxCoeff( );
    const double      scale      = x.abs( ).maxCoeff( ) * sigma(unit);
    const core::Array normalized = unit / sigma(unit);
    family::Options   options;
    options.max_imfs      = 3;
    options.ensemble_size = 4;
    const std::vector< std::uint32_t > seed{ 123, 456 };
    const auto                         white  = noises(options.ensemble_size, x.size( ), seed);
    const auto                         actual = family::decompose(view(x), method, options, seed);
    require(!actual.imfs.empty( ), "ensemble returned no modes");
    std::vector< core::Array > expected;
    core::Array                residual = normalized;
    if (method == family::Method::eemd) {
        std::vector< family::Result > members;
        std::size_t                   count = 0;
        for (const auto &noise : white) {
            core::Array trial = normalized + options.noise_scale * noise;
            members.push_back(family::decompose(view(trial), family::Method::emd, options));
            count = std::max(count, members.back( ).imfs.size( ));
        }
        for (std::size_t order = 0; order < count; ++order) {
            core::Array mode     = core::Array::Zero(x.size( ));
            int         selected = 0;
            for (const auto &member : members)
                if (order < member.imfs.size( )) {
                    mode += member.imfs[order];
                    ++selected;
                }
            mode /= selected;
            residual -= mode;
            expected.push_back(mode * scale);
        }
    } else {
        std::vector< family::Result > noise_modes;
        for (const auto &noise : white)
            noise_modes.push_back(family::decompose(view(noise), family::Method::emd, options));
        auto one     = options;
        one.max_imfs = 1;
        for (std::size_t order = 0; order < actual.imfs.size( ); ++order) {
            core::Array mode     = core::Array::Zero(x.size( ));
            int         selected = 0;
            for (std::size_t member = 0; member < white.size( ); ++member) {
                core::Array noise = core::Array::Zero(x.size( ));
                if (order == 0)
                    noise = white[member];
                else if (order - 1 < noise_modes[member].imfs.size( )) {
                    const auto &component = noise_modes[member].imfs[order - 1];
                    if (sigma(component) > 0) noise = component / sigma(component);
                }
                core::Array trial  = residual + options.noise_scale * (order == 0 ? 1 : sigma(residual)) * noise;
                auto        result = family::decompose(view(trial), family::Method::emd, one);
                if (!result.imfs.empty( )) {
                    mode += result.imfs[0];
                    ++selected;
                }
            }
            require(selected > 0, "CEEMDAN oracle lost ensemble members");
            mode /= selected;
            residual -= mode;
            expected.push_back(mode * scale);
        }
    }
    require(actual.imfs.size( ) == expected.size( ), "ensemble formula mode count");
    for (std::size_t i = 0; i < expected.size( ); ++i) close(actual.imfs[i], expected[i]);
    close(actual.residual, core::Array(residual * scale));
    close(reconstruct(actual), x);
}
void lifecycle( ) {
    family::Workspace workspace;
    family::Options   options;
    options.max_imfs      = 3;
    options.ensemble_size = 3;
    const std::vector< std::uint32_t > seed{ 17 };
    const auto                         x = signal(512), original = x;
    auto                               preserved = family::decompose(view(x), family::Method::emd, options);
    const auto                         snapshot  = preserved;
    for (auto method : { family::Method::emd, family::Method::eemd, family::Method::ceemdan }) {
        for (int n : { 512, 1024, 128, 512 }) {
            const auto     input = signal(n);
            family::Result result;
            family::execution::decompose(view(input), method, options, seed, result, workspace);
            equal(result, family::decompose(view(input), method, options, seed));
            close(reconstruct(result), input);
        }
        auto task  = [&] { return family::decompose(view(x), method, options, seed); };
        auto first = std::async(std::launch::async, task), second = std::async(std::launch::async, task);
        equal(first.get( ), second.get( ));
    }
    close(x, original);
    equal(preserved, snapshot);
    options.sift.max_sifts    = 1;
    options.sift.sd_threshold = 1e-30;
    family::Result result;
    family::execution::decompose(view(x), family::Method::emd, options, seed, result, workspace);
    require(result.reason == family::Reason::maximum_sifts_reached, "lost iteration limit");
    options.sift.max_sifts    = 100;
    options.sift.sd_threshold = .2;
    family::execution::decompose(view(x), family::Method::emd, options, seed, result, workspace);
    equal(result, snapshot);
    auto invalid     = options;
    invalid.max_imfs = 0;
    bool rejected    = false;
    try {
        family::decompose(view(x), family::Method::emd, invalid);
    } catch (const std::invalid_argument &) {
        rejected = true;
    }
    require(rejected, "public C++ boundary accepted invalid options");
}
}    // namespace

int main( ) {
    try {
        std::cout << "EEMD formula\n";
        formula(family::Method::eemd);
        std::cout << "CEEMDAN formula\n";
        formula(family::Method::ceemdan);
        std::cout << "Lifecycle\n";
        lifecycle( );
        std::cout << "PASS: streaming EEMD, Torres CEEMDAN, ownership, workspace and concurrency\n";
    } catch (const std::exception &error) {
        std::cerr << error.what( ) << '\n';
        return 1;
    }
}
