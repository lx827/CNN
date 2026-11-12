#include <fourier/api.hpp>
#include <numeric/api.hpp>
#include <cmath>
#include <stdexcept>

int main( ) {
    using namespace cnn_compute;
    // 任意复谱的实部逆变换不等同于 Hermitian 半谱逆变换。
    std::vector< fourier::Complex > input{ { 1, 2 }, { 3, -4 }, { 2, 5 }, { -1, 1 }, { 4, -3 } };
    const auto                      expected = fourier::ifft(input);
    fourier::Plan                   plan(input.size( ));
    std::vector< double >           real(input.size( ));
    plan.inverse_real(input, real);
    for (std::size_t i = 0; i < real.size( ); ++i)
        if (std::abs(real[i] - expected[i].real( )) > 1e-13) throw std::runtime_error("complex inverse real-part contract");
    std::vector< double >           samples{ 1, 2, -1, 3, 4 };
    std::vector< fourier::Complex > half(samples.size( ) / 2 + 1);
    plan.forward_half(samples, half);
    plan.inverse_half(half, real);
    for (std::size_t i = 0; i < real.size( ); ++i)
        if (std::abs(real[i] - samples[i]) > 1e-13) throw std::runtime_error("odd real FFT contract");
    // 同规模重复执行，先前返回的拥有型结果不受 Plan 后续使用影响。
    const auto spectrum = numeric::spectrum(samples, 1000);
    plan.forward_half(samples, half);
    if (spectrum.amplitude.size( ) != 3) throw std::runtime_error("spectrum shape");
}
