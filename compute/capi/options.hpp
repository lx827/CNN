#pragma once
#include "result.hpp"
#include <emd/ensemble.hpp>
#include <emd/mask.hpp>

namespace cnn_capi {
inline cnn_compute::envelope::Options options(const cnn_envelope_options *p) {
    if (!p) return {};
    return { enumeration< cnn_compute::interpolation::Method >(p->interpolation, 2),
             enumeration< cnn_compute::envelope::Padding >(p->padding, 1), p->pad_width, p->parabolic != 0 };
}
inline cnn_compute::emd::IMFOptions options(const cnn_imf_options *p) {
    if (!p) return {};
    return { p->env_step_size, p->max_iterations, p->energy_threshold, enumeration< cnn_compute::emd::StopMethod >(p->stop_method, 3), p->sd_threshold, { p->rilling_threshold[0], p->rilling_threshold[1], p->rilling_threshold[2] } };
}
inline cnn_compute::emd::Options options(const cnn_emd_options *p) {
    cnn_compute::emd::Options o;
    if (!p) return o;
    o.imf           = options(&p->imf);
    o.envelope      = options(&p->envelope);
    o.max_imfs      = p->max_imfs;
    o.sift_thresh   = p->use_sift_threshold ? std::optional< double >(p->sift_threshold) : std::nullopt;
    o.energy_thresh = p->use_energy_threshold ? std::optional< double >(p->energy_threshold) : std::nullopt;
    if (p->use_rilling_threshold) o.rilling_thresh = std::array< double, 3 >{ p->rilling_threshold[0], p->rilling_threshold[1], p->rilling_threshold[2] };
    return o;
}
inline cnn_compute::emd::MaskOptions options(const cnn_mask_options *p) {
    cnn_compute::emd::MaskOptions o;
    if (!p) return o;
    o.imf            = options(&p->imf);
    o.envelope       = options(&p->envelope);
    auto frequencies = span(p->frequencies), amplitudes = span(p->amplitudes);
    o.mask_freqs.assign(frequencies.begin( ), frequencies.end( ));
    if (!amplitudes.empty( )) o.mask_amp.assign(amplitudes.begin( ), amplitudes.end( ));
    o.first_mask       = enumeration< cnn_compute::emd::FirstMask >(p->first_mask, 2);
    o.first_frequency  = p->first_frequency;
    o.amp_mode         = enumeration< cnn_compute::emd::AmplitudeMode >(p->amplitude_mode, 2);
    o.mask_step_factor = p->step_factor;
    o.max_imfs         = p->max_imfs;
    o.nphases          = p->phases;
    o.sift_thresh      = p->sift_threshold;
    return o;
}
}    // namespace cnn_capi
