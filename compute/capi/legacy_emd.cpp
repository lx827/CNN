#include "result.hpp"
#include <emd/emd.hpp>
#include <cmath>

using namespace cnn_capi;
namespace cc = cnn_compute;
namespace {
std::span< const double > finite(cnn_span x, size_t minimum) {
    auto input = span(x);
    if (input.size( ) < minimum) throw std::invalid_argument("legacy EMD input is too short");
    if (!Eigen::Map< const cc::core::Array >(input.data( ), input.size( )).isFinite( ).all( )) throw std::invalid_argument("legacy EMD input must be finite");
    return input;
}
cc::core::Interpolation method(cnn_interpolation value) {
    if (value == CNN_PCHIP) return cc::core::Interpolation::pchip;
    if (value == CNN_CUBIC) return cc::core::Interpolation::cubic;
    throw std::invalid_argument("legacy EMD interpolation requires PCHIP or cubic");
}
std::array< double, 3 > thresholds(const double *values) {
    std::array< double, 3 > result{ values[0], values[1], values[2] };
    if (!std::isfinite(result[0]) || !std::isfinite(result[1]) || !std::isfinite(result[2]) || result[0] <= 0 || result[1] < result[0] || result[2] < 0 || result[2] > 1)
        throw std::invalid_argument("Rilling thresholds require 0<sd1<=sd2 and 0<=fraction<=1");
    return result;
}
}    // namespace
cnn_legacy_sift_options CNN_CALL cnn_legacy_sift_defaults(void) {
    return { 1000, 2, .1, CNN_PCHIP, CNN_STOP_SD, { .05, .5, .05 } };
}
cnn_result *CNN_CALL cnn_legacy_sift(cnn_span x, const cnn_legacy_sift_options *p, cnn_error *e) {
    return boundary(e, [&] {auto o=p?*p:cnn_legacy_sift_defaults();auto input=finite(x,8);
        if(o.max_sifts<=0 || o.mirror_extrema<=0 || !std::isfinite(o.sd_threshold) || o.sd_threshold<=0)
            throw std::invalid_argument("legacy sift parameters must be positive and finite");
        auto rule=enumeration<cc::emd::StoppingRule>(o.stopping_rule,1);
        cc::emd::SiftParameters parameters{o.max_sifts,o.mirror_extrema,o.sd_threshold,method(o.interpolation),rule,thresholds(o.rilling_threshold)};
        auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::emd::sift(input,parameters));r->text("status",v?"valid":"insufficient_extrema");
        if(v){r->array("imf",v->imf);r->integer("iterations",v->iterations);r->integer("converged",v->converged);}return r; });
}
cnn_result *CNN_CALL cnn_legacy_envelopes(cnn_span x, int mirror, cnn_interpolation interpolation, cnn_error *e) {
    return boundary(e, [&] {if(mirror<=0)throw std::invalid_argument("mirror extrema must be positive");
        auto r=std::make_unique<cnn_result>();auto& v=r->keep(cc::emd::envelopes(finite(x,8),mirror,method(interpolation)));r->text("status",v?"valid":"insufficient_extrema");
        if(v){r->array("upper",v->upper);r->array("lower",v->lower);}return r; });
}
cnn_result *CNN_CALL cnn_rilling_stop(cnn_span upper, cnn_span lower, cnn_span threshold, cnn_error *e) {
    return boundary(e, [&] {auto high=finite(upper,1),low=finite(lower,1),t=span(threshold);
        if(high.size()!=low.size() || t.size()!=3)throw std::invalid_argument("Rilling requires equal envelope lengths and three thresholds");
        auto r=std::make_unique<cnn_result>();r->integer("stop",cc::emd::rilling_stop(high,low,thresholds(t.data())));return r; });
}
