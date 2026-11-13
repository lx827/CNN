#include "api.hpp"
#include <core/slot.hpp>
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
    // pocketfft 计划构后只读、exec 为 const 且无共享可变状态，允许跨线程共享；
    // 每方向一个进程级单槽：同尺寸零重建，尺寸变化才重建，内存有界。
    struct RealPlan {
        std::size_t                              samples;
        pocketfft::detail::pocketfft_r< double > plan;
        explicit RealPlan(std::size_t n) : samples(n), plan(n) {}
        std::size_t size( ) const {
            return samples;
        }
    };
    struct ComplexPlan {
        std::size_t                              samples;
        pocketfft::detail::pocketfft_c< double > plan;
        explicit ComplexPlan(std::size_t n) : samples(n), plan(n) {}
        std::size_t size( ) const {
            return samples;
        }
    };
    std::shared_ptr< const RealPlan > real_plan(std::size_t n) {
        static core::SingleSlot< RealPlan > slot;
        return slot.obtain(n);
    }
    std::shared_ptr< const ComplexPlan > complex_plan(std::size_t n) {
        static core::SingleSlot< ComplexPlan > slot;
        return slot.obtain(n);
    }
}    // namespace
struct Plan::Impl {
    std::size_t                                       samples = 0;
    std::shared_ptr< const RealPlan >                 real;       // 惰性：首次 real 方向 exec 时获取
    std::shared_ptr< const ComplexPlan >              complex;    // 惰性：首次 complex 方向 exec 时获取
    std::vector< pocketfft::detail::cmplx< double > > buffer;     // complex 方向可写缓冲
    std::vector< double >                             packed;     // real 方向可写缓冲
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
    impl_->samples = n;
    // 计划与缓冲随首次对应方向 exec 惰性获取/扩容，prepare 本身不分配。
}
std::size_t Plan::size( ) const {
    return impl_->samples;
}
void Plan::forward(std::span< const double > x, std::span< Complex > out) {
    forward_half_padded(x.data( ), size( ), out.first(size( ) / 2 + 1));
    for (std::size_t i = size( ) / 2 + 1; i < size( ); ++i) out[i] = std::conj(out[size( ) - i]);
}
void Plan::forward_half(std::span< const double > x, std::span< Complex > out) {
    forward_half_padded(x.data( ), size( ), out);
}
void Plan::forward_half_padded(const double *input, std::size_t valid, std::span< Complex > out) {
    const std::size_t n = size( );
    if (!impl_->real || impl_->real->samples != n) impl_->real = real_plan(n);
    if (impl_->packed.size( ) != n) impl_->packed.resize(n);
    std::copy_n(input, valid, impl_->packed.begin( ));
    std::fill(impl_->packed.begin( ) + static_cast< std::ptrdiff_t >(valid), impl_->packed.end( ), 0.0);
    auto &buffer = impl_->packed;
    impl_->real->plan.exec(buffer.data( ), 1.0, true);
    out[0]        = { buffer[0], 0 };
    std::size_t i = 1, k = 1;
    for (; i < n - 1; i += 2, ++k) out[k] = { buffer[i], buffer[i + 1] };
    if (i < n) out[k] = { buffer[i], 0 };
}
void Plan::inverse_half(std::span< const Complex > x, std::span< double > out) {
    const std::size_t n = size( );
    if (!impl_->real || impl_->real->samples != n) impl_->real = real_plan(n);
    out[0]        = x[0].real( );
    std::size_t i = 1, k = 1;
    for (; i < n - 1; i += 2, ++k) {
        out[i]     = x[k].real( );
        out[i + 1] = x[k].imag( );
    }
    if (i < n) out[i] = x[k].real( );
    impl_->real->plan.exec(out.data( ), 1.0 / static_cast< double >(n), false);
}
void Plan::forward(std::span< const Complex > x, std::span< Complex > out) {
    const std::size_t n = size( );
    if (!impl_->complex || impl_->complex->samples != n) impl_->complex = complex_plan(n);
    if (impl_->buffer.size( ) != n) impl_->buffer.resize(n);
    for (std::size_t i = 0; i < n; ++i) impl_->buffer[i].Set(x[i].real( ), x[i].imag( ));
    impl_->complex->plan.exec(impl_->buffer.data( ), 1.0, true);
    for (std::size_t i = 0; i < n; ++i) out[i] = { impl_->buffer[i].r, impl_->buffer[i].i };
}
void Plan::inverse(std::span< const Complex > x, std::span< Complex > out) {
    const std::size_t n = size( );
    if (!impl_->complex || impl_->complex->samples != n) impl_->complex = complex_plan(n);
    if (impl_->buffer.size( ) != n) impl_->buffer.resize(n);
    for (std::size_t i = 0; i < n; ++i) impl_->buffer[i].Set(x[i].real( ), x[i].imag( ));
    impl_->complex->plan.exec(impl_->buffer.data( ), 1.0 / static_cast< double >(n), false);
    for (std::size_t i = 0; i < n; ++i) out[i] = { impl_->buffer[i].r, impl_->buffer[i].i };
}
void Plan::inverse_real(std::span< const Complex > x, std::span< double > out) {
    const std::size_t n = size( );
    if (!impl_->complex || impl_->complex->samples != n) impl_->complex = complex_plan(n);
    if (impl_->buffer.size( ) != n) impl_->buffer.resize(n);
    for (std::size_t i = 0; i < n; ++i) impl_->buffer[i].Set(x[i].real( ), x[i].imag( ));
    impl_->complex->plan.exec(impl_->buffer.data( ), 1.0 / static_cast< double >(n), false);
    for (std::size_t i = 0; i < n; ++i) out[i] = impl_->buffer[i].r;
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
    Plan                   plan(n);
    std::vector< Complex > ax(n / 2 + 1), bx(n / 2 + 1);
    plan.forward_half_padded(a.data( ), a.size( ), ax);
    plan.forward_half_padded(b.data( ), b.size( ), bx);
    for (std::size_t i = 0; i < ax.size( ); ++i) ax[i] *= bx[i];
    std::vector< double > out(n);
    plan.inverse_half(ax, out);
    out.resize(length);
    return out;
}
}    // namespace cnn_compute::fourier
