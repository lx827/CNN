#include "options.hpp"
#include <filtering/api.hpp>
#include <fourier/api.hpp>
#include <numeric/api.hpp>
#include <solvers/api.hpp>
#include <transforms/hilbert.hpp>

using namespace cnn_capi;
namespace cc = cnn_compute;

cnn_result *CNN_CALL cnn_fft(cnn_span x, cnn_error *e) {
    return boundary(e, [&] { return complex_values(cc::fourier::fft(span(x))); });
}
cnn_result *CNN_CALL cnn_fft_complex(cnn_complex_span x, cnn_error *e) {
    return boundary(e, [&] { return complex_values(cc::fourier::fft(unpack(x))); });
}
cnn_result *CNN_CALL cnn_ifft(cnn_complex_span x, cnn_error *e) {
    return boundary(e, [&] { return complex_values(cc::fourier::ifft(unpack(x))); });
}
cnn_result *CNN_CALL cnn_convolve(cnn_span a, cnn_span b, cnn_error *e) {
    return boundary(e, [&] { return values(cc::fourier::convolve(span(a), span(b))); });
}
cnn_result *CNN_CALL cnn_butterworth(int order, double low, double high, double fs, cnn_error *e) {
    return boundary(e, [&] {auto sos=cc::filtering::butterworth(order,low,high,fs);std::vector<double> packed;packed.reserve(sos.size()*6);
        for(const auto& section:sos)packed.insert(packed.end(),section.begin(),section.end());
        auto r=values(std::move(packed),"sos");r->fields.front().rows=sos.size();r->fields.front().columns=6;return r; });
}
cnn_result *CNN_CALL cnn_sosfiltfilt(cnn_span x, cnn_span coefficients, int padlen, cnn_error *e) {
    return boundary(e, [&] {auto input=span(coefficients);if(input.size()%6)throw std::invalid_argument("SOS requires six coefficients per section");
        std::vector<cc::filtering::Sos> sos(input.size()/6);for(size_t i=0;i<sos.size();++i)std::copy_n(input.data()+i*6,6,sos[i].begin());
        return values(cc::filtering::sosfiltfilt(span(x),sos,padlen)); });
}
cnn_result *CNN_CALL cnn_hann(size_t n, cnn_error *e) {
    return boundary(e, [&] { return values(cc::filtering::hann(n)); });
}
cnn_result *CNN_CALL cnn_detrend(cnn_span x, int linear, cnn_error *e) {
    return boundary(e, [&] { return values(cc::filtering::detrend(span(x), linear != 0)); });
}
cnn_result *CNN_CALL cnn_savgol(cnn_span x, int window, int order, int derivative, double delta, cnn_error *e) {
    return boundary(e, [&] { return values(cc::filtering::savgol(span(x), window, order, derivative, delta)); });
}
cnn_result *CNN_CALL cnn_solve_tridiagonal(cnn_span lower, cnn_span diagonal, cnn_span upper, cnn_span rhs, cnn_error *e) {
    return boundary(e, [&] { return values(cc::solvers::solve_tridiagonal(copy(lower), copy(diagonal), copy(upper), copy(rhs))); });
}
cnn_result *CNN_CALL cnn_interpolate(cnn_span x, cnn_span y, cnn_span query, cnn_interpolation method, cnn_error *e) {
    return boundary(e, [&] { return values(cc::interpolation::interpolate(span(x), span(y), span(query), enumeration< cc::interpolation::Method >(method, 2))); });
}
cnn_envelope_options CNN_CALL cnn_envelope_defaults(void) {
    return { CNN_SPLREP, CNN_RILLING_PADDING, 2, 0 };
}
cnn_result *CNN_CALL cnn_find_extrema(cnn_span x, int maxima, int parabolic, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::envelope::find_extrema(span(x),maxima!=0,parabolic!=0));r->array("locations",v.locations);r->array("values",v.values);return r; });
}
cnn_result *CNN_CALL cnn_extrema_envelopes(cnn_span x, const cnn_envelope_options *p, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::envelope::extrema_envelopes(span(x),options(p)));
        r->text("status",v?"valid":"insufficient_extrema");if(v){r->array("upper",v->upper);r->array("lower",v->lower);}return r; });
}
cnn_result *CNN_CALL cnn_upper_envelope(cnn_span x, const cnn_envelope_options *p, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::envelope::upper_envelope(span(x),options(p)));
        r->text("status",v?"valid":"insufficient_extrema");if(v)r->array("values",*v);return r; });
}
cnn_result *CNN_CALL cnn_combined_envelope(cnn_span x, const cnn_envelope_options *p, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::envelope::combined_envelope(span(x),options(p)));
        r->text("status",v?"valid":"insufficient_extrema");if(v)r->array("values",*v);return r; });
}
cnn_result *CNN_CALL cnn_analytic_signal(cnn_span x, cnn_error *e) {
    return boundary(e, [&] { return complex_values(cc::transforms::analytic_signal(span(x))); });
}
cnn_result *CNN_CALL cnn_amplitude_normalise(cnn_span x, cnn_error *e) {
    return boundary(e, [&] { return values(cc::transforms::amplitude_normalise(span(x))); });
}
cnn_result *CNN_CALL cnn_frequency_transform(cnn_span x, double fs, int normalised, int smooth_phase, int smooth_frequency, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::transforms::frequency_transform(span(x),fs,normalised!=0,smooth_phase,smooth_frequency));
        r->array("phase",v.phase);r->array("frequency",v.frequency);r->array("amplitude",v.amplitude);return r; });
}
cnn_result *CNN_CALL cnn_spectrum(cnn_span x, double fs, int remove_mean, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::numeric::spectrum(span(x),fs,remove_mean!=0));
        r->array("frequency",v.frequency);r->array("amplitude",v.amplitude);r->array("power",v.power);return r; });
}
cnn_result *CNN_CALL cnn_stft(cnn_span x, double fs, int window, int overlap, int nfft, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::numeric::stft(span(x),fs,window,overlap,nfft));
        r->array("time",v.time);r->array("frequency",v.frequency);r->array("amplitude",v.amplitude,v.amplitude.rows(),v.amplitude.cols());return r; });
}
cnn_result *CNN_CALL cnn_cepstrum(cnn_span x, cnn_error *e) {
    return boundary(e, [&] { return values(cc::numeric::cepstrum(span(x))); });
}
cnn_result *CNN_CALL cnn_hilbert_envelope(cnn_span x, cnn_error *e) {
    return boundary(e, [&] { return values(cc::numeric::hilbert_envelope(span(x))); });
}
cnn_result *CNN_CALL cnn_statistics(cnn_span x, double floor, cnn_error *e) {
    return boundary(e, [&] { return values(cc::numeric::statistics(span(x), floor), "statistics"); });
}
cnn_result *CNN_CALL cnn_time_domain(cnn_span x, double fs, int window, int step, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::numeric::time_domain(span(x),fs,window,step));
        r->array("overall",v.overall);r->array("time",v.time);r->array("values",v.values,v.values.rows(),v.values.cols());r->integer("window",v.window);r->integer("step",v.step);return r; });
}
cnn_result *CNN_CALL cnn_segmented_rms(cnn_span x, double fs, size_t segment, int remove_mean, cnn_error *e) {
    return boundary(e, [&] {auto r=values(cc::numeric::segmented_rms(span(x),fs,segment,remove_mean!=0));auto& v=*static_cast<cc::numeric::Matrix*>(r->owners[0].get());
        r->fields[0].rows=v.rows();r->fields[0].columns=v.cols();return r; });
}
cnn_result *CNN_CALL cnn_extrema(cnn_span x, cnn_span y, size_t maximum, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::numeric::extrema(span(x),span(y),maximum));r->array("values",v,v.rows(),v.cols());return r; });
}
cnn_result *CNN_CALL cnn_autocorrelation(cnn_span x, int demean, cnn_error *e) {
    return boundary(e, [&] { return values(cc::numeric::autocorrelation(span(x), demean != 0)); });
}
