#include "result.hpp"
#include <diagnostic/api.hpp>
#include <rotation/api.hpp>
#include <sequence/api.hpp>

using namespace cnn_capi;
namespace cc = cnn_compute;
namespace {
Result speed(cc::rotation::SpeedResult v) {
    auto r = std::make_unique< cnn_result >( );
    r->real("frequency", v.frequency);
    r->text("source", v.source);
    r->text("reason", v.reason);
    return r;
}
void cusum(cnn_result &r, const cc::sequence::CusumResult &v) {
    r.real("positive", v.positive);
    r.real("negative", v.negative);
    r.real("final_positive", v.final_positive);
    r.real("final_negative", v.final_negative);
    r.real("ewma", v.ewma);
}
}    // namespace
cnn_result *CNN_CALL cnn_teager(cnn_span x, cnn_error *e) {
    return boundary(e, [&] { return values(cc::diagnostic::teager(span(x))); });
}
cnn_result *CNN_CALL cnn_complex_spectral_kurtosis(cnn_complex_span x, cnn_error *e) {
    return boundary(e, [&] { return scalar(cc::diagnostic::complex_spectral_kurtosis(unpack(x))); });
}
cnn_result *CNN_CALL cnn_filter_bank_kurtogram(cnn_span x, double fs, int level, double minimum, int order, cnn_error *e) {
    return boundary(e, [&] {auto bands=cc::diagnostic::filter_bank_kurtogram(span(x),fs,level,minimum,order);std::vector<double> packed;packed.reserve(bands.size()*6);
        for(auto b:bands)packed.insert(packed.end(),{b.low_hz,b.high_hz,static_cast<double>(b.level),b.spectral_kurtosis,b.impulsiveness,b.signal_to_background});
        auto r=values(std::move(packed),"bands");r->fields[0].rows=bands.size();r->fields[0].columns=6;return r; });
}
cnn_result *CNN_CALL cnn_cepstral_prewhiten(cnn_span x, double fs, cnn_span comb, double width, cnn_error *e) {
    return boundary(e, [&] { return values(cc::diagnostic::cepstral_prewhiten(span(x), fs, span(comb), width)); });
}
cnn_result *CNN_CALL cnn_sc_scoh(cnn_span x, double fs, cnn_span alpha, size_t segment, size_t step, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::diagnostic::sc_scoh(span(x),fs,span(alpha),segment,step));
        r->complex("correlation",v.correlation,v.rows,v.columns);r->array("coherence",v.coherence,v.rows,v.columns);r->size("segments",v.segments);r->real("input_scale",v.input_scale);return r; });
}
cnn_result *CNN_CALL cnn_modulation_bispectrum(cnn_span x, double fs, cnn_span carriers, cnn_span modulation, size_t segment, size_t step, size_t minimum, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::diagnostic::modulation_bispectrum(span(x),fs,span(carriers),span(modulation),segment,step,minimum));
        r->complex("mean",v.mean,v.rows,v.columns);r->array("coherence",v.coherence,v.rows,v.columns);r->field("valid",CNN_U8,v.valid.data(),v.rows,v.columns);r->size("segments",v.segments);return r; });
}
cnn_result *CNN_CALL cnn_integrate(cnn_span time, cnn_span speed, cnn_error *e) {
    return boundary(e, [&] { return values(cc::rotation::integrate(span(time), span(speed))); });
}
cnn_result *CNN_CALL cnn_rotation_interpolate(cnn_span x, cnn_span y, cnn_span target, int zero, cnn_error *e) {
    return boundary(e, [&] { return values(cc::rotation::interpolate(span(x), span(y), span(target), zero != 0)); });
}
cnn_result *CNN_CALL cnn_angle_resample(cnn_span x, cnn_span phase, int samples, cnn_error *e) {
    return boundary(e, [&] { return values(cc::rotation::angle_resample(span(x), span(phase), samples)); });
}
cnn_result *CNN_CALL cnn_amplitude_spectrum(cnn_span x, int center, cnn_error *e) {
    return boundary(e, [&] { return values(cc::rotation::amplitude_spectrum(span(x), center != 0)); });
}
cnn_result *CNN_CALL cnn_periodic_components(cnn_span cycle, cnn_span orders, cnn_error *e) {
    return boundary(e, [&] { return values(cc::rotation::periodic_components(span(cycle), span(orders))); });
}
cnn_result *CNN_CALL cnn_tsa_components(cnn_span cycle, cnn_span mesh, cnn_span regular, int revolutions, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::rotation::tsa_components(span(cycle),span(mesh),span(regular),revolutions));
        r->array("mesh",v.mesh);r->array("regular",v.regular);r->array("residual",v.residual);r->array("differential",v.differential);r->array("amplitude",v.amplitude);return r; });
}
cnn_result *CNN_CALL cnn_tsa(cnn_span x, int samples, int minimum, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::rotation::tsa(span(x),samples,minimum));r->array("cycle",v.first);r->array("repeated",v.second);return r; });
}
cnn_result *CNN_CALL cnn_zoom_spectrum(cnn_span x, double fs, double low, double high, int points, cnn_error *e) {
    return boundary(e, [&] { return values(cc::rotation::zoom_spectrum(span(x), fs, low, high, points)); });
}
cnn_result *CNN_CALL cnn_real_cepstrum(cnn_span x, cnn_error *e) {
    return boundary(e, [&] { return values(cc::rotation::real_cepstrum(span(x))); });
}
cnn_result *CNN_CALL cnn_amfm(cnn_span x, double fs, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::rotation::amfm(span(x),fs));r->array("envelope",v.envelope);r->array("frequency",v.frequency);return r; });
}
cnn_result *CNN_CALL cnn_band_envelope(cnn_span x, double fs, double low, double high, cnn_error *e) {
    return boundary(e, [&] { return values(cc::rotation::band_envelope(span(x), fs, low, high)); });
}
cnn_result *CNN_CALL cnn_window_peaks(cnn_span axis, cnn_span amplitude, cnn_span centers, double width, int disjoint, cnn_error *e) {
    return boundary(e, [&] { return values(cc::rotation::window_peaks(span(axis), span(amplitude), span(centers), width, disjoint != 0)); });
}
cnn_result *CNN_CALL cnn_band_sum(cnn_span axis, cnn_span v, double center, double width, cnn_error *e) {
    return boundary(e, [&] { return scalar(cc::rotation::band_sum(span(axis), span(v), center, width)); });
}
cnn_result *CNN_CALL cnn_local_peak(cnn_span axis, cnn_span amplitude, double center, double width, double inner, double outer, cnn_span exclusions, int median, cnn_error *e) {
    return boundary(e, [&] {auto v=cc::rotation::local_peak(span(axis),span(amplitude),center,width,inner,outer,span(exclusions),median!=0);auto r=std::make_unique<cnn_result>();
        r->real("coordinate",v.coordinate);r->real("amplitude",v.amplitude);r->real("background",v.background);r->size("background_count",v.background_count);r->integer("found",v.found);return r; });
}
cnn_result *CNN_CALL cnn_car_features(cnn_span axis, cnn_span cepstrum, cnn_span targets, double width, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::rotation::car_features(span(axis),span(cepstrum),span(targets),width));r->array("coordinate",v.coordinate);r->array("amplitude",v.amplitude);r->real("background",v.background);r->size("background_count",v.background_count);return r; });
}
cnn_result *CNN_CALL cnn_order_statistics(cnn_span amplitude, cnn_error *e) {
    return boundary(e, [&] {auto v=cc::rotation::order_statistics(span(amplitude));auto r=scalar(v.first,"concentration");r->real("spectral_kurtosis",v.second);return r; });
}
cnn_ridge_options CNN_CALL cnn_ridge_defaults(void) {
    return { 8, .12, .6, .2, 2 };
}
cnn_result *CNN_CALL cnn_speed_ridge(cnn_span x, double fs, double low, double high, int window, int hop, const cnn_ridge_options *p, cnn_error *e) {
    return boundary(e, [&] {cc::rotation::RidgeParameters o;if(p)o={p->peak_to_background,p->local_energy,p->reliable_fraction,p->boundary_fraction,p->consecutive_boundaries};
        auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::rotation::speed_ridge(span(x),fs,low,high,window,hop,o));r->array("frequency",v.frequency);r->integer("reliable",v.reliable);r->integer("total",v.total);r->text("reason",v.reason);return r; });
}
cnn_result *CNN_CALL cnn_spectrum_speed(cnn_span x, double fs, double low, double high, int harmonics, double bandwidth, double smoothing, cnn_error *e) {
    return boundary(e, [&] { return speed(cc::rotation::spectrum_speed(span(x), fs, low, high, harmonics, bandwidth, smoothing)); });
}
cnn_result *CNN_CALL cnn_autocorrelation_speed(cnn_span x, double fs, double low, double high, cnn_error *e) {
    return boundary(e, [&] { return speed(cc::rotation::autocorrelation_speed(span(x), fs, low, high)); });
}
cnn_result *CNN_CALL cnn_envelope_speed(cnn_span x, double fs, double carrier, double low, double high, double bandwidth, cnn_error *e) {
    return boundary(e, [&] { return speed(cc::rotation::envelope_speed(span(x), fs, carrier, low, high, bandwidth)); });
}
cnn_result *CNN_CALL cnn_cvs(cnn_span x, cnn_span carrier, cnn_span planet, double azimuth, double sensor, double width, int samples, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::rotation::cvs(span(x),span(carrier),span(planet),azimuth,sensor,width,samples));
        r->array("signal",v.signal);std::vector<size_t> intervals;intervals.reserve(v.intervals.size()*2);for(auto i:v.intervals){intervals.push_back(i.first);intervals.push_back(i.second);}
        auto& packed=r->keep(std::move(intervals));r->field("intervals",CNN_SIZE,packed.data(),v.intervals.size(),2);r->integer("cycles",v.cycles);r->real("coverage",v.coverage);r->size("completed_intervals",v.completed_intervals);return r; });
}
cnn_result *CNN_CALL cnn_holt(cnn_span x, int steps, double alpha, double beta, double gamma, int period, double trend, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::sequence::holt(span(x),steps,alpha,beta,gamma,period,trend));
        r->array("level",v.level);r->array("trend",v.trend);r->array("season",v.season);r->array("fitted",v.fitted);r->array("forecast",v.forecast);return r; });
}
cnn_result *CNN_CALL cnn_kalman(cnn_span x, double process, double measurement, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::sequence::kalman(span(x),process,measurement));r->array("score",v.score);r->array("rate",v.rate);r->real("variance",v.variance);return r; });
}
cnn_result *CNN_CALL cnn_cusum(cnn_span x, double allowance, double alpha, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();cusum(*r,cc::sequence::cusum(span(x),allowance,alpha));return r; });
}
cnn_result *CNN_CALL cnn_mann_whitney_z(cnn_span x, cnn_span reference, int window, cnn_error *e) {
    return boundary(e, [&] { return values(cc::sequence::mann_whitney_z(span(x), span(reference), window)); });
}
cnn_result *CNN_CALL cnn_regression(cnn_span x, cnn_span y, cnn_error *e) {
    return boundary(e, [&] {auto v=cc::sequence::regression(span(x),span(y));auto r=scalar(v.first,"slope");r->real("intercept",v.second);return r; });
}
cnn_result *CNN_CALL cnn_central_moment(cnn_span x, int degree, int scale, cnn_error *e) {
    return boundary(e, [&] {auto v=cc::sequence::central_moment(span(x),degree,scale!=0);auto r=scalar(v.first,"moment");r->real("variance",v.second);return r; });
}
cnn_result *CNN_CALL cnn_window_moments(cnn_span x, int window, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::sequence::window_moments(span(x),window));r->array("rms",v.first);r->array("kurtosis",v.second);return r; });
}
cnn_result *CNN_CALL cnn_robust_standardize(cnn_span x, cnn_error *e) {
    return boundary(e, [&] { return values(cc::sequence::robust_standardize(span(x))); });
}
cnn_result *CNN_CALL cnn_sign_cusum(cnn_span x, double reference, int median, cnn_error *e) {
    return boundary(e, [&] {auto v=cc::sequence::sign_cusum(span(x),reference,median!=0);auto r=std::make_unique<cnn_result>();cusum(*r,v.first);r->real("reference",v.second);return r; });
}
