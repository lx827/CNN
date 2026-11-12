#include "api.hpp"
#include <pocketfft_hdronly.h>
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace cnn_compute::fourier {
namespace {
    template < class T >
    void validate(std::span< const T > values) {
        if (values.empty( )) throw std::invalid_argument("FFT requires nonempty input");
        for (const auto &value : values) {
            if constexpr (std::is_same_v< T, double >) {
                if (!std::isfinite(value)) throw std::invalid_argument("FFT input must be finite");
            } else if (!std::isfinite(value.real( )) || !std::isfinite(value.imag( )))
                throw std::invalid_argument("FFT input must be finite");
        }
    }
}    // namespace
struct Plan::Impl {
    std::size_t                                                 samples = 0;
    std::unique_ptr< pocketfft::detail::pocketfft_c< double > > plan;
    std::vector< pocketfft::detail::cmplx< double > >           buffer;
    std::unique_ptr< pocketfft::detail::pocketfft_r< double > > real_plan;
    std::vector< double >                                       packed;
};
Plan::Plan(std::size_t samples) : impl_(std::make_unique< Impl >( )) {
    if (samples) prepare(samples);
}
Plan::~Plan( )                          = default;
Plan::Plan(Plan &&) noexcept            = default;
Plan &Plan::operator=(Plan &&) noexcept = default;
void  Plan::prepare(std::size_t n) {
    if (!n) throw std::invalid_argument("FFT length must be positive");
    if (n == impl_->samples) return;
    impl_->plan      = std::make_unique< pocketfft::detail::pocketfft_c< double > >(n);
    impl_->real_plan = std::make_unique< pocketfft::detail::pocketfft_r< double > >(n);
    impl_->buffer.resize(n);
    impl_->packed.resize(n);
    impl_->samples = n;
}
std::size_t Plan::size( ) const {
    return impl_->samples;
}
void Plan::forward(std::span< const double > x, std::span< Complex > out) {
    forward_half(x, out.first(size( ) / 2 + 1));
    for (std::size_t i = size( ) / 2 + 1; i < size( ); ++i) out[i] = std::conj(out[size( ) - i]);
}
void Plan::forward_half(std::span< const double > x, std::span< Complex > out) {
    std::copy_n(x.begin( ), size( ), impl_->packed.begin( ));
    auto &buffer = impl_->packed;
    impl_->real_plan->exec(buffer.data( ), 1.0, true);
    out[0]        = { buffer[0], 0 };
    std::size_t i = 1, k = 1;
    for (; i < size( ) - 1; i += 2, ++k) out[k] = { buffer[i], buffer[i + 1] };
    if (i < size( )) out[k] = { buffer[i], 0 };
}
void Plan::inverse_half(std::span< const Complex > x, std::span< double > out) {
    auto &buffer  = impl_->packed;
    buffer[0]     = x[0].real( );
    std::size_t i = 1, k = 1;
    for (; i < size( ) - 1; i += 2, ++k) {
        buffer[i]     = x[k].real( );
        buffer[i + 1] = x[k].imag( );
    }
    if (i < size( )) buffer[i] = x[k].real( );
    impl_->real_plan->exec(buffer.data( ), 1.0 / static_cast< double >(size( )), false);
    std::copy(buffer.begin( ), buffer.end( ), out.begin( ));
}
void Plan::forward(std::span< const Complex > x, std::span< Complex > out) {
    for (std::size_t i = 0; i < size( ); ++i) impl_->buffer[i].Set(x[i].real( ), x[i].imag( ));
    impl_->plan->exec(impl_->buffer.data( ), 1.0, true);
    for (std::size_t i = 0; i < size( ); ++i) out[i] = { impl_->buffer[i].r, impl_->buffer[i].i };
}
void Plan::inverse(std::span< const Complex > x, std::span< Complex > out) {
    for (std::size_t i = 0; i < size( ); ++i) impl_->buffer[i].Set(x[i].real( ), x[i].imag( ));
    impl_->plan->exec(impl_->buffer.data( ), 1.0 / static_cast< double >(size( )), false);
    for (std::size_t i = 0; i < size( ); ++i) out[i] = { impl_->buffer[i].r, impl_->buffer[i].i };
}
void Plan::inverse_real(std::span< const Complex > x, std::span< double > out) {
    for (std::size_t i = 0; i < size( ); ++i) impl_->buffer[i].Set(x[i].real( ), x[i].imag( ));
    impl_->plan->exec(impl_->buffer.data( ), 1.0 / static_cast< double >(size( )), false);
    for (std::size_t i = 0; i < size( ); ++i) out[i] = impl_->buffer[i].r;
}
std::vector< Complex > fft(std::span< const double > x) {
    validate(x);
    Plan                   p(x.size( ));
    std::vector< Complex > y(x.size( ));
    p.forward(x, y);
    return y;
}
std::vector< Complex > fft(std::span< const Complex > x) {
    validate(x);
    Plan                   p(x.size( ));
    std::vector< Complex > y(x.size( ));
    p.forward(x, y);
    return y;
}
std::vector< Complex > ifft(std::span< const Complex > x) {
    validate(x);
    Plan                   p(x.size( ));
    std::vector< Complex > y(x.size( ));
    p.inverse(x, y);
    return y;
}
std::vector< Complex > rfft(std::span< const double > x) {
    validate(x);
    Plan                   p(x.size( ));
    std::vector< Complex > y(x.size( ) / 2 + 1);
    p.forward_half(x, y);
    return y;
}
std::vector< double > irfft(std::span< const Complex > x, std::size_t samples) {
    validate(x);
    if (!samples || x.size( ) != samples / 2 + 1) throw std::invalid_argument("half spectrum length must be N/2+1");
    Plan                  p(samples);
    std::vector< double > y(samples);
    p.inverse_half(x, y);
    return y;
}
std::vector< double > convolve(std::span< const double > a, std::span< const double > b) {
    if (a.empty( ) || b.empty( )) return {};
    validate(a);
    validate(b);
    const std::size_t length = a.size( ) + b.size( ) - 1;
    std::size_t       n      = 1;
    while (n < length) n *= 2;
    Plan                  plan(n);
    std::vector< double > x(n, 0.0), y(n, 0.0), out(n);
    std::copy(a.begin( ), a.end( ), x.begin( ));
    std::copy(b.begin( ), b.end( ), y.begin( ));
    std::vector< Complex > ax(n / 2 + 1), bx(n / 2 + 1);
    plan.forward_half(x, ax);
    plan.forward_half(y, bx);
    for (std::size_t i = 0; i < ax.size( ); ++i) ax[i] *= bx[i];
    plan.inverse_half(ax, out);
    out.resize(length);
    return out;
}
}    // namespace cnn_compute::fourier
