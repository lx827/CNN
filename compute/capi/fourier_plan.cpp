#include "result.hpp"
#include <fourier/api.hpp>

using namespace cnn_capi;
namespace cc = cnn_compute;
struct cnn_fft_plan {
    cc::fourier::Plan                   plan;
    std::vector< cc::fourier::Complex > input;
    explicit cnn_fft_plan(size_t n) : plan(n), input(n) {
        if (!n) throw std::invalid_argument("FFT length must be positive");
    }
    void require(size_t size, bool half = false) const {
        if (size != (half ? plan.size( ) / 2 + 1 : plan.size( ))) throw std::invalid_argument("input length differs from FFT plan");
    }
    void unpack(cnn_complex_span x) {
        if (x.size && !x.data) throw std::invalid_argument("nonempty complex span requires data");
        for (size_t i = 0; i < x.size; ++i) input[i] = { x.data[i].real, x.data[i].imag };
    }
};
cnn_fft_plan *CNN_CALL cnn_fft_plan_create(size_t samples, cnn_error *e) {
    return boundary(e, [&] { return std::make_unique< cnn_fft_plan >(samples); });
}
void CNN_CALL cnn_fft_plan_free(cnn_fft_plan *plan) {
    delete plan;
}
cnn_result *CNN_CALL cnn_fft_plan_forward(cnn_fft_plan *p, cnn_span x, int half, cnn_error *e) {
    return boundary(e, [&] {if(!p)throw std::invalid_argument("FFT plan is required");p->require(x.size);auto input=span(x);
        size_t count=half?p->plan.size()/2+1:p->plan.size();std::vector<cc::fourier::Complex> output(count);
        if(half)p->plan.forward_half(input,output);else p->plan.forward(input,output);
        return complex_values(std::move(output)); });
}
cnn_result *CNN_CALL cnn_fft_plan_complex(cnn_fft_plan *p, cnn_complex_span x, int inverse, cnn_error *e) {
    return boundary(e, [&] {if(!p)throw std::invalid_argument("FFT plan is required");p->require(x.size);p->unpack(x);
        std::vector<cc::fourier::Complex> output(p->plan.size());
        if(inverse)p->plan.inverse(p->input,output);else p->plan.forward(p->input,output);
        return complex_values(std::move(output)); });
}
cnn_result *CNN_CALL cnn_fft_plan_inverse_half(cnn_fft_plan *p, cnn_complex_span x, cnn_error *e) {
    return boundary(e, [&] {if(!p)throw std::invalid_argument("FFT plan is required");p->require(x.size,true);p->unpack(x);
        std::vector<double> output(p->plan.size());p->plan.inverse_half(std::span(p->input).first(x.size),output);return values(std::move(output)); });
}
cnn_result *CNN_CALL cnn_rfft(cnn_span x, cnn_error *e) {
    return boundary(e, [&] { return complex_values(cc::fourier::rfft(span(x))); });
}
cnn_result *CNN_CALL cnn_irfft(cnn_complex_span x, size_t samples, cnn_error *e) {
    return boundary(e, [&] { return values(cc::fourier::irfft(unpack(x), samples)); });
}
