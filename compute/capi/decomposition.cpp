#include "options.hpp"
#include <emd/second_layer.hpp>
#include <vmd/api.hpp>
#include <deconvolution/api.hpp>
#include <ica/api.hpp>
#include <adaptive/api.hpp>

using namespace cnn_capi;
namespace cc = cnn_compute;
namespace {
void decomposition(cnn_result &r, const cc::emd::Result &v, const std::string &prefix = "") {
    r.size(prefix + "component_count", v.components.size( ));
    for (size_t i = 0; i < v.components.size( ); ++i) r.array(prefix + "component." + std::to_string(i), v.components[i]);
    static_assert(sizeof(int) == sizeof(int32_t));
    r.field(prefix + "iterations", CNN_I32, v.iterations.data( ), v.iterations.size( ));
    r.integer(prefix + "status", static_cast< int >(v.status));
}
Result pack(cc::emd::Result v) {
    auto r = std::make_unique< cnn_result >( );
    decomposition(*r, r->keep(std::move(v)));
    return r;
}
Result pack(cc::emd::NextResult v) {
    auto  r    = std::make_unique< cnn_result >( );
    auto &data = r->keep(std::move(v));
    r->array("imf", data.imf);
    r->integer("continue_flag", data.info.continue_flag);
    r->integer("iterations", data.info.iterations);
    r->integer("status", static_cast< int >(data.info.status));
    return r;
}
void mask(cnn_result &r, const cc::emd::MaskResult &v) {
    decomposition(r, v.decomposition);
    r.array("mask_frequencies", v.mask_frequencies);
}
Result pack(cc::emd::MaskResult v) {
    auto r = std::make_unique< cnn_result >( );
    mask(*r, r->keep(std::move(v)));
    return r;
}
std::vector< std::span< const double > > layers(const cnn_span *first, size_t count) {
    if (count && !first) throw std::invalid_argument("first_layer requires spans");
    std::vector< std::span< const double > > result;
    result.reserve(count);
    for (size_t i = 0; i < count; ++i) result.push_back(span(first[i]));
    return result;
}
Result pack(cc::emd::SecondLayerResult v) {
    auto  r    = std::make_unique< cnn_result >( );
    auto &data = r->keep(std::move(v));
    r->size("layer_count", data.layers.size( ));
    r->size("output_depth", data.output_depth);
    for (size_t i = 0; i < data.layers.size( ); ++i) decomposition(*r, data.layers[i], "layer." + std::to_string(i) + ".");
    return r;
}
cc::wavelet::Plan plan(const char *wavelet, const char *mode) {
    return cc::wavelet::Plan(text(wavelet, "db8"), text(mode, "symmetric"));
}
const cc::wavelet::Coefficients &coefficients(const cnn_result *result) {
    if (!result || !result->coefficients) throw std::invalid_argument("requires wavelet decomposition result");
    return *result->coefficients;
}
cc::deconvolution::Options options(const cnn_deconvolution_options *p) {
    if (!p) return {};
    return { p->filter_length, p->max_iterations, p->tolerance, p->ridge };
}
Result pack(cc::deconvolution::Result v) {
    auto  r    = std::make_unique< cnn_result >( );
    auto &data = r->keep(std::move(v));
    r->array("signal", data.signal);
    r->array("filter", data.filter);
    r->array("objective_history", data.objective_history);
    r->integer("iterations", data.info.iterations);
    r->integer("converged", data.info.converged);
    return r;
}
}    // namespace

cnn_imf_options CNN_CALL cnn_imf_defaults(void) {
    return { 1, 1000, 50, CNN_STOP_SD, .1, { .05, .5, .05 } };
}
cnn_emd_options CNN_CALL cnn_emd_defaults(void) {
    return { cnn_imf_defaults( ), cnn_envelope_defaults( ), 0, 1, 1e-8, 1, 50, 0, { 0, 0, 0 } };
}
cnn_mask_options CNN_CALL cnn_mask_defaults(void) {
    return { cnn_imf_defaults( ), cnn_envelope_defaults( ), { nullptr, 0 }, CNN_MASK_ZERO_CROSSINGS, .25, { nullptr, 0 }, CNN_MASK_RATIO_SIGNAL, 2, 9, 4, 1e-8 };
}
cnn_iterated_mask_options CNN_CALL cnn_iterated_mask_defaults(void) {
    auto mask_defaults           = cnn_mask_defaults( );
    mask_defaults.max_imfs       = 6;
    mask_defaults.amplitude_mode = CNN_MASK_RATIO_IMF;
    return { mask_defaults, 15, 1, .1, 1, 2, 1, 0 };
}
cnn_result *CNN_CALL cnn_next_imf(cnn_span x, const cnn_imf_options *imf, const cnn_envelope_options *env, cnn_error *e) {
    return boundary(e, [&] { return pack(cc::emd::get_next_imf(span(x), options(imf), options(env))); });
}
cnn_result *CNN_CALL cnn_sift(cnn_span x, const cnn_emd_options *p, cnn_error *e) {
    return boundary(e, [&] { return pack(cc::emd::sift(span(x), options(p))); });
}
cnn_result *CNN_CALL cnn_ensemble_sift(cnn_span x, cnn_span noise, const cnn_emd_options *p, int count, double scale, int flip, cnn_error *e) {
    return boundary(e, [&] {cc::emd::EnsembleOptions o;o.sift=options(p);o.nensembles=count;o.ensemble_noise=scale;o.noise_mode=flip?cc::emd::NoiseMode::flip:cc::emd::NoiseMode::single;
        return pack(cc::emd::ensemble_sift(span(x),span(noise),o)); });
}
cnn_result *CNN_CALL cnn_complete_ensemble_sift(cnn_span x, cnn_span noise, const cnn_emd_options *p, int count, double scale, cnn_error *e) {
    return boundary(e, [&] {cc::emd::CompleteEnsembleOptions o;o.sift=options(p);o.nensembles=count;o.ensemble_noise=scale;return pack(cc::emd::complete_ensemble_sift(span(x),span(noise),o)); });
}
cnn_result *CNN_CALL cnn_next_imf_mask(cnn_span x, double frequency, double amplitude, int phases, const cnn_imf_options *imf, const cnn_envelope_options *env, cnn_error *e) {
    return boundary(e, [&] { return pack(cc::emd::get_next_imf_mask(span(x), frequency, amplitude, phases, options(imf), options(env))); });
}
cnn_result *CNN_CALL cnn_mask_frequency(cnn_span x, cnn_first_mask method, double frequency, const cnn_imf_options *imf, cnn_error *e) {
    return boundary(e, [&] { return scalar(cc::emd::get_mask_frequency(span(x), enumeration< cc::emd::FirstMask >(method, 2), frequency, options(imf)), "frequency"); });
}
cnn_result *CNN_CALL cnn_mask_sift(cnn_span x, const cnn_mask_options *p, cnn_error *e) {
    return boundary(e, [&] { return pack(cc::emd::mask_sift(span(x), options(p))); });
}
cnn_result *CNN_CALL cnn_iterated_mask_sift(cnn_span x, const cnn_iterated_mask_options *p, cnn_error *e) {
    return boundary(e, [&] {cc::emd::IteratedMaskOptions o;if(p){o.mask=options(&p->mask);o.max_iter=p->max_iterations;o.averages=p->averages;o.iter_thresh=p->threshold;o.sample_rate=p->sample_rate;o.weight_power=p->weight_power;o.weighted=p->weighted!=0;o.exclude_edges=p->exclude_edges!=0;}
        auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::emd::iterated_mask_sift(span(x),o));mask(*r,v.result);r->array("mask_variability",v.mask_variability);r->integer("mask_iterations",v.iterations);r->integer("converged",v.converged);return r; });
}
cnn_result *CNN_CALL cnn_sift_second_layer(const cnn_span *first, size_t count, const cnn_emd_options *p, cnn_error *e) {
    return boundary(e, [&] { return pack(cc::emd::sift_second_layer(layers(first, count), options(p))); });
}
cnn_result *CNN_CALL cnn_mask_sift_second_layer(const cnn_span *first, size_t count, cnn_span frequencies, const cnn_mask_options *p, cnn_error *e) {
    return boundary(e, [&] { return pack(cc::emd::mask_sift_second_layer(layers(first, count), span(frequencies), options(p))); });
}

cnn_result *CNN_CALL cnn_wavelet_decompose(cnn_span x, const char *wavelet, const char *mode, int level, int packet, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::wavelet::decompose(span(x),plan(wavelet,mode),level,packet!=0));r->coefficients=&v;
        for(size_t i=0;i<v.bands.size();++i)r->array("band."+std::to_string(i),v.bands[i]);
        r->field("lengths",CNN_SIZE,v.lengths.data(),v.lengths.size());r->integer("level",v.level);r->integer("packet",v.packet);return r; });
}
cnn_result *CNN_CALL cnn_wavelet_reconstruct(const cnn_result *c, const char *wavelet, const char *mode, cnn_error *e) {
    return boundary(e, [&] { return values(cc::wavelet::reconstruct(coefficients(c), plan(wavelet, mode))); });
}
cnn_result *CNN_CALL cnn_wavelet_components(const cnn_result *c, const char *wavelet, const char *mode, cnn_error *e) {
    return boundary(e, [&] {auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::wavelet::reconstruct_components(coefficients(c),plan(wavelet,mode)));
        for(size_t i=0;i<v.size();++i)r->array("component."+std::to_string(i),v[i]);return r; });
}
cnn_result *CNN_CALL cnn_wavelet_selected(const cnn_result *c, const char *wavelet, const char *mode, cnn_indices selected, cnn_error *e) {
    return boundary(e, [&] { return values(cc::wavelet::reconstruct_selected(coefficients(c), plan(wavelet, mode), span(selected))); });
}
cnn_result *CNN_CALL cnn_wavelet_denoise(cnn_span x, const char *wavelet, const char *mode, int level, const char *threshold, double scale, cnn_error *e) {
    return boundary(e, [&] { return values(cc::wavelet::denoise(span(x), plan(wavelet, mode), level, text(threshold, "soft"), scale)); });
}
cnn_vmd_options CNN_CALL cnn_vmd_defaults(void) {
    return { 5, 2000, 0, 1e-7, 200, 0, 51200, 1, 0 };
}
cnn_result *CNN_CALL cnn_vmd(cnn_span x, double fs, const cnn_vmd_options *p, cnn_error *e) {
    return boundary(e, [&] {cc::vmd::Parameters o;if(p)o={p->modes,p->alpha,p->tau,p->tolerance,p->max_iterations,p->dc!=0,p->max_samples,p->initialization,p->seed};
        auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::vmd::decompose(span(x),fs,o));
        r->array("modes",v.modes,v.valid_length?static_cast<size_t>(v.modes.size())/v.valid_length:0,v.valid_length);
        r->array("center_frequencies_hz",v.center_frequencies_hz);
        r->array("center_frequency_history_hz",v.center_frequency_history_hz,v.center_frequency_history_hz.size()?v.iterations:0,v.center_frequencies_hz.size());
        r->array("residual",v.residual);r->size("input_length",v.input_length);r->size("valid_length",v.valid_length);
        r->integer("iterations",v.iterations);r->integer("converged",v.converged);r->text("status",v.status);r->text("reason",v.reason);return r; });
}
cnn_deconvolution_options CNN_CALL cnn_deconvolution_defaults(void) {
    return { 64, 30, 1e-6, 1e-8 };
}
cnn_result *CNN_CALL cnn_med(cnn_span x, const cnn_deconvolution_options *p, cnn_error *e) {
    return boundary(e, [&] { return pack(cc::deconvolution::med(span(x), options(p))); });
}
cnn_result *CNN_CALL cnn_mckd(cnn_span x, int period, int shift, const cnn_deconvolution_options *p, cnn_error *e) {
    return boundary(e, [&] { return pack(cc::deconvolution::mckd(span(x), period, shift, options(p))); });
}
cnn_result *CNN_CALL cnn_normalized_kurtosis(cnn_span x, cnn_error *e) {
    return boundary(e, [&] { return scalar(cc::deconvolution::normalized_kurtosis(span(x))); });
}
cnn_result *CNN_CALL cnn_correlated_kurtosis(cnn_span x, int period, int shift, cnn_error *e) {
    return boundary(e, [&] { return scalar(cc::deconvolution::correlated_kurtosis(span(x), period, shift)); });
}
cnn_result *CNN_CALL cnn_mckd_update(cnn_span matrix, size_t rows, size_t columns, cnn_span filter, int period, int shift, double ridge, cnn_error *e) {
    return boundary(e, [&] { return values(cc::deconvolution::mckd_update(span(matrix), rows, columns, span(filter), period, shift, ridge)); });
}
cnn_ica_options CNN_CALL cnn_ica_defaults(void) {
    return { 0, 200, 1e-6, 0 };
}
cnn_result *CNN_CALL cnn_fast_ica(cnn_span observations, size_t samples, size_t channels, const cnn_ica_options *p, cnn_error *e) {
    return boundary(e, [&] {cc::ica::Options o;if(p)o={p->components,p->max_iterations,p->tolerance,p->seed};
        auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::ica::fast_ica(span(observations),samples,channels,o));
        r->array("components",v.components.values,v.components.rows,v.components.columns);r->array("mixing",v.mixing.values,v.mixing.rows,v.mixing.columns);r->array("unmixing",v.unmixing.values,v.unmixing.rows,v.unmixing.columns);
        r->array("mean",v.mean);r->integer("numerical_rank",v.numerical_rank);r->integer("iterations",v.iterations);r->integer("status",static_cast<int>(v.status));return r; });
}
cnn_adaptive_options CNN_CALL cnn_adaptive_defaults(void) {
    return { CNN_LMS, 32, 1, 0, .01, .97, 5e-5, 1e-6, .05 };
}
cnn_result *CNN_CALL cnn_adaptive_filter(cnn_span x, const cnn_adaptive_options *p, cnn_error *e) {
    return boundary(e, [&] {cc::adaptive::Options o;if(p)o={enumeration<cc::adaptive::Method>(p->method,2),p->filter_length,p->delay,p->max_updates,p->step_size,p->alpha,p->gamma,p->minimum_step,p->maximum_step};return values(cc::adaptive::filter(span(x),o)); });
}
