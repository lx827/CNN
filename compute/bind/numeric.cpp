#include "arrays.hpp"
#include "modules.hpp"
#include <filtering/api.hpp>
#include <fourier/api.hpp>
#include <numeric/api.hpp>
#include <pybind11/complex.h>
#include <pybind11/stl.h>
#include <memory>

namespace cnn_compute::bind {
namespace {
    // 本组公开 C++ 入口负责数值前提；绑定只检查维数/布局，不重复扫描输入。
    std::span< const double > values(const ArrayInput &a) {
        if (a.ndim( ) != 1) throw py::value_error("input must be one dimensional");
        return { a.data( ), static_cast< std::size_t >(a.size( )) };
    }
    template < class Owner, class T >
    py::array_t< T > owned(Owner &&data, std::vector< py::ssize_t > shape) {
        using Storage     = std::decay_t< Owner >;
        auto        owner = std::make_unique< Storage >(std::move(data));
        auto       *p     = owner.get( );
        py::capsule capsule(p, [](void *v) { delete static_cast< Storage * >(v); });
        owner.release( );
        std::vector< py::ssize_t > strides(shape.size( ));
        py::ssize_t                stride = sizeof(T);
        for (std::size_t i = shape.size( ); i-- > 0;) {
            strides[i] = stride;
            stride *= shape[i];
        }
        return py::array_t< T >(shape, strides, reinterpret_cast< T * >(p->data( )), capsule);
    }
    template < class T >
    auto vector_output(std::vector< T > &&v) {
        auto n = static_cast< py::ssize_t >(v.size( ));
        return owned< std::vector< T >, T >(std::move(v), { n });
    }
    auto matrix_output(numeric::Matrix &&m) {
        auto rows = m.rows( ), cols = m.cols( );
        return owned< numeric::Matrix, double >(std::move(m), { rows, cols });
    }
    auto sos_output(std::vector< filtering::Sos > &&v) {
        auto rows = static_cast< py::ssize_t >(v.size( ));
        return owned< std::vector< filtering::Sos >, double >(std::move(v), { rows, 6 });
    }
}    // namespace
void bind_numeric(py::module_ &root) {
    auto m = root.def_submodule("numeric", "基础数值计算，独立拥有的 NumPy 结果");
    m.def("spectrum", [](const ArrayInput &a, double fs, bool center) {
        auto x=values(a); numeric::Spectrum r;
        {py::gil_scoped_release release;r=numeric::spectrum(x,fs,center);}
        return py::make_tuple(output(std::move(r.frequency)),output(std::move(r.amplitude)),output(std::move(r.power))); }, py::arg("signal"), py::arg("fs"), py::arg("remove_mean") = true);
    m.def("stft", [](const ArrayInput &a, double fs, int window, int overlap, int nfft) {
        auto          x = values(a);
        numeric::Stft r;
        {
            py::gil_scoped_release release;
            r = numeric::stft(x, fs, window, overlap, nfft);
        }
        return py::make_tuple(output(std::move(r.time)), output(std::move(r.frequency)), matrix_output(std::move(r.amplitude)));
    });
    m.def("time_domain", [](const ArrayInput &a, double fs, int window, int step) {
        auto x=values(a); numeric::TimeDomain r;
        {py::gil_scoped_release release;r=numeric::time_domain(x,fs,window,step);}
        return py::make_tuple(r.overall,output(std::move(r.time)),matrix_output(std::move(r.values)),r.window,r.step); }, py::arg("signal"), py::arg("fs"), py::arg("window") = 1024, py::arg("step") = 0);
    m.def("statistics", [](const ArrayInput &a, double floor) {auto x=values(a);py::gil_scoped_release release;return numeric::statistics(x,floor); }, py::arg("signal"), py::arg("margin_floor") = 1e-12);
    m.def("segmented_rms", [](const ArrayInput &a, double fs, std::size_t segment, bool center) {
        auto x=values(a);numeric::Matrix r;{py::gil_scoped_release release;r=numeric::segmented_rms(x,fs,segment,center);}return matrix_output(std::move(r)); }, py::arg("signal"), py::arg("fs"), py::arg("segment"), py::arg("remove_mean") = true);
    m.def("extrema", [](const ArrayInput &a, const ArrayInput &b, std::size_t maximum) {
        auto            x = values(a), y = values(b);
        numeric::Matrix r;
        {
            py::gil_scoped_release release;
            r = numeric::extrema(x, y, maximum);
        }
        return matrix_output(std::move(r));
    });
    m.def("autocorrelation", [](const ArrayInput &a, bool center) {auto x=values(a);core::Array r;{py::gil_scoped_release release;r=numeric::autocorrelation(x,center);}return output(std::move(r)); }, py::arg("signal"), py::arg("demean") = true);
    m.def("cepstrum", [](const ArrayInput &a) {auto x=values(a);core::Array r;{py::gil_scoped_release release;r=numeric::cepstrum(x);}return output(std::move(r)); });
    m.def("hilbert_envelope", [](const ArrayInput &a) {auto x=values(a);core::Array r;{py::gil_scoped_release release;r=numeric::hilbert_envelope(x);}return output(std::move(r)); });

    auto f = root.def_submodule("filtering", "SOS、趋势与多项式平滑");
    f.def("butterworth", [](int order, double low, double high, double fs) {std::vector<filtering::Sos> r;{py::gil_scoped_release release;r=filtering::butterworth(order,low,high,fs);}return sos_output(std::move(r)); });
    f.def("sosfiltfilt", [](const ArrayInput &a, const ArrayInput &sos, int pad) {
        auto x=values(a);
        if(sos.ndim()!=2||sos.shape(1)!=6)throw py::value_error("SOS shape must be (sections,6)");
        auto coefficients=std::span<const filtering::Sos>(reinterpret_cast<const filtering::Sos*>(sos.data()),sos.shape(0));
        std::vector<double> r;{py::gil_scoped_release release;r=filtering::sosfiltfilt(x,coefficients,pad);}return vector_output(std::move(r)); }, py::arg("signal"), py::arg("sos"), py::arg("padlen") = -1);
    f.def("hann", [](std::size_t n) { return vector_output(filtering::hann(n)); });
    f.def("detrend", [](const ArrayInput &a, bool linear) {auto x=values(a);std::vector<double> r;{py::gil_scoped_release release;r=filtering::detrend(x,linear);}return vector_output(std::move(r)); }, py::arg("signal"), py::arg("linear") = false);
    f.def("savgol", [](const ArrayInput &a, int window, int order, int derivative, double delta) {auto x=values(a);std::vector<double> r;{py::gil_scoped_release release;r=filtering::savgol(x,window,order,derivative,delta);}return vector_output(std::move(r)); }, py::arg("signal"), py::arg("window"), py::arg("order"), py::arg("derivative") = 0, py::arg("delta") = 1.0);

    auto fft = root.def_submodule("fourier", "pocketfft 单线程 Fourier 变换");
    fft.def("fft_real", [](const ArrayInput &a) {auto x=values(a);std::vector<fourier::Complex> r;{py::gil_scoped_release release;r=fourier::fft(x);}return vector_output(std::move(r)); });
    fft.def("rfft", [](const ArrayInput &a) {auto x=values(a);std::vector<fourier::Complex> r;{py::gil_scoped_release release;r=fourier::rfft(x);}return vector_output(std::move(r)); });
    using ComplexInput = py::array_t< fourier::Complex, py::array::c_style >;
    auto complex_fft   = [](const ComplexInput &a, bool inverse) {
        if (a.ndim( ) != 1) throw py::value_error("input must be one dimensional");
        std::span< const fourier::Complex > x(a.data( ), a.size( ));
        std::vector< fourier::Complex >     r;
        {
            py::gil_scoped_release release;
            r = inverse ? fourier::ifft(x) : fourier::fft(x);
        }
        return vector_output(std::move(r));
    };
    fft.def("fft", [complex_fft](const ComplexInput &a) { return complex_fft(a, false); });
    fft.def("ifft", [complex_fft](const ComplexInput &a) { return complex_fft(a, true); });
    fft.def("irfft", [](const ComplexInput &a, std::size_t samples) {
        if (a.ndim( ) != 1) throw py::value_error("input must be one dimensional");
        std::span< const fourier::Complex > x(a.data( ), a.size( ));
        std::vector< double >               r;
        {
            py::gil_scoped_release release;
            r = fourier::irfft(x, samples);
        }
        return vector_output(std::move(r));
    });
    fft.def("convolve", [](const ArrayInput &a, const ArrayInput &b) {auto x=values(a),y=values(b);std::vector<double> r;{py::gil_scoped_release release;r=fourier::convolve(x,y);}return vector_output(std::move(r)); });
}
}    // namespace cnn_compute::bind
