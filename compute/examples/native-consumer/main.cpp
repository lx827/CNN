#include <adaptive/api.hpp>
#include <core/build_info.hpp>
#include <deconvolution/api.hpp>
#include <diagnostic/api.hpp>
#include <emd/second_layer.hpp>
#include <filtering/api.hpp>
#include <fourier/api.hpp>
#include <ica/api.hpp>
#include <numeric/api.hpp>
#include <rotation/api.hpp>
#include <sequence/api.hpp>
#include <solvers/api.hpp>
#include <transforms/hilbert.hpp>
#include <vmd/api.hpp>
#include <wavelet/api.hpp>
#include <cmath>
#include <iostream>
#include <vector>

int main( ) {
    namespace cc = cnn_compute;
    std::vector< double > signal(256);
    for (size_t i = 0; i < signal.size( ); ++i) signal[i] = std::sin(i * .25);
    cc::wavelet::Plan plan("db4");
    auto              coefficients = cc::wavelet::decompose(signal, plan, 2);
    auto              restored     = cc::wavelet::reconstruct(coefficients, plan);
    for (size_t i = 0; i < signal.size( ); ++i)
        if (std::abs(restored[i] - signal[i]) > 1e-11) return 1;
    auto spectrum = cc::numeric::spectrum(signal, 256);
    auto filtered = cc::sequence::kalman(signal, .1, .2);
    if (spectrum.frequency.size( ) != 129 || filtered.score.size( ) != 256) return 2;
    std::cout << cc::core::build_info( ).compiler_id << ": installed C++ targets and vendor static dependency passed\n";
}
