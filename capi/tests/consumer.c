#include <cnn_compute.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define CHECK(condition)                                            \
    do {                                                            \
        if (!(condition)) {                                         \
            fprintf(stderr, "line %d: %s\n", __LINE__, #condition); \
            return 1;                                               \
        }                                                           \
    } while (0)
static cnn_field field(cnn_result *r, const char *name) {
    cnn_field output = { 0 };
    if (!cnn_result_find(r, name, &output)) fprintf(stderr, "missing field %s\n", name);
    return output;
}
int main(void) {
    double        x[256], original[256];
    size_t        i;
    cnn_error     error;
    cnn_span      input = { x, 256 };
    cnn_result   *first, *second, *inverse, *coefficients, *reconstruction, *state;
    cnn_fft_plan *plan;
    cnn_field     f;
    cnn_complex   half_spectrum[129];
    for (i = 0; i < 256; ++i) x[i] = original[i] = sin(6.283185307179586 * 16 * i / 256) + .2 * cos(6.283185307179586 * 3 * i / 256);
    plan = cnn_fft_plan_create(256, &error);
    CHECK(plan && error.code == CNN_ERROR_NONE);
    first = cnn_fft_plan_forward(plan, input, 1, &error);
    CHECK(first);
    f = field(first, "values");
    CHECK(f.type == CNN_COMPLEX && f.rows == 129);
    CHECK(fabs(cnn_field_complex(f, 16).imag + 128) < 1e-10);
    for (i = 0; i < 129; ++i) half_spectrum[i] = cnn_field_complex(f, i);
    inverse = cnn_fft_plan_inverse_half(plan, (cnn_complex_span){ half_spectrum, f.rows }, &error);
    CHECK(inverse);
    for (i = 0; i < 256; ++i) CHECK(fabs(((const double *)field(inverse, "values").data)[i] - original[i]) < 1e-12);
    for (i = 0; i < 256; ++i) x[i] = 0;
    second = cnn_fft_plan_forward(plan, input, 1, &error);
    CHECK(second);
    cnn_result_free(second);
    cnn_fft_plan_free(plan);
    CHECK(fabs(cnn_field_complex(f, 16).imag + 128) < 1e-10);
    cnn_result_free(first);
    cnn_result_free(inverse);

    {
        double        identity[] = { 1, 0, 0, 1, 0, 0 };
        cnn_sos_plan *filter     = cnn_sos_plan_create((cnn_span){ identity, 6 }, 0, &error);
        CHECK(filter);
        first = cnn_sos_plan_apply(filter, (cnn_span){ original, 256 }, &error);
        CHECK(first);
        second = cnn_sos_plan_apply(filter, input, &error);
        CHECK(second);
        cnn_sos_plan_free(filter);
        cnn_result_free(second);
        f = field(first, "values");
        for (i = 0; i < 256; ++i) CHECK(((const double *)f.data)[i] == original[i]);
        cnn_result_free(first);
    }

    input.data   = original;
    coefficients = cnn_wavelet_decompose(input, "db4", "symmetric", 2, 0, &error);
    CHECK(coefficients);
    reconstruction = cnn_wavelet_reconstruct(coefficients, "db4", "symmetric", &error);
    CHECK(reconstruction);
    cnn_result_free(coefficients);
    f = field(reconstruction, "values");
    CHECK(f.rows == 256);
    for (i = 0; i < 256; ++i) CHECK(fabs(((const double *)f.data)[i] - original[i]) < 1e-11);
    cnn_result_free(reconstruction);

    state = cnn_extrema_envelopes((cnn_span){ x, 256 }, NULL, &error);
    CHECK(state);
    CHECK(strcmp(field(state, "status").data, "insufficient_extrema") == 0);
    cnn_result_free(state);
    {
        cnn_legacy_sift_options options = cnn_legacy_sift_defaults( );
        options.max_sifts               = 1;
        options.sd_threshold            = 1e-30;
        state                           = cnn_legacy_sift(input, &options, &error);
        CHECK(state);
        CHECK(*(const int32_t *)field(state, "iterations").data == 1);
        CHECK(*(const int32_t *)field(state, "converged").data == 0);
        cnn_result_free(state);
    }
    {
        cnn_imf_options options = cnn_imf_defaults( );
        options.max_iterations  = 1;
        state                   = cnn_next_imf(input, &options, NULL, &error);
        CHECK(state);
        CHECK(field(state, "status").type == CNN_I32);
        cnn_result_free(state);
    }
    {
        cnn_vmd_options options = cnn_vmd_defaults( );
        options.modes           = 2;
        options.max_iterations  = 3;
        options.max_samples     = 128;
        state                   = cnn_vmd(input, 256, &options, &error);
        CHECK(state);
        CHECK(*(const size_t *)field(state, "input_length").data == 256);
        CHECK(*(const size_t *)field(state, "valid_length").data == 128);
        CHECK(field(state, "center_frequency_history_hz").rows == (size_t)*(const int32_t *)field(state, "iterations").data);
        cnn_result_free(state);
    }
    {
        double rank_deficient[128];
        for (i = 0; i < 64; ++i) rank_deficient[2 * i] = rank_deficient[2 * i + 1] = original[i];
        state = cnn_fast_ica((cnn_span){ rank_deficient, 128 }, 64, 2, NULL, &error);
        CHECK(state);
        CHECK(*(const int32_t *)field(state, "status").data == CNN_ICA_RANK_DEFICIENT);
        cnn_result_free(state);
    }
    state = cnn_interpolate((cnn_span){ original, 2 }, (cnn_span){ original, 1 }, (cnn_span){ NULL, 0 }, CNN_PCHIP, &error);
    CHECK(!state && error.code == CNN_ERROR_ARGUMENT && error.message[0]);
    cnn_result_free(NULL);
    puts("C ABI: plan/owner lifetime, reconstruction, quality state and errors passed");
    return 0;
}
