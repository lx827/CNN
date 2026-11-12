#include "api.hpp"
#include <pocketfft_hdronly.h>
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace cnn_compute::fourier {
struct Plan::Impl {
    std::size_t samples = 0;
    std::unique_ptr<pocketfft::detail::pocketfft_c<double>> plan;
    std::vector<pocketfft::detail::cmplx<double>> buffer;
};
Plan::Plan(std::size_t samples) : impl_(std::make_unique<Impl>()) { if (samples) prepare(samples); }
Plan::~Plan() = default;
Plan::Plan(Plan&&) noexcept = default;
Plan& Plan::operator=(Plan&&) noexcept = default;
void Plan::prepare(std::size_t n) {
    if (!n) throw std::invalid_argument("FFT length must be positive");
    if (n == impl_->samples) return;
    impl_->plan = std::make_unique<pocketfft::detail::pocketfft_c<double>>(n);
    impl_->buffer.resize(n);
    impl_->samples = n;
}
std::size_t Plan::size() const { return impl_->samples; }
void Plan::forward(std::span<const double> x, std::span<Complex> out) {
    for (std::size_t i=0;i<size();++i) impl_->buffer[i].Set(x[i],0.0);
    impl_->plan->exec(impl_->buffer.data(),1.0,true);
    for (std::size_t i=0;i<size();++i) out[i]={impl_->buffer[i].r,impl_->buffer[i].i};
}
void Plan::forward(std::span<const Complex> x, std::span<Complex> out) {
    for (std::size_t i=0;i<size();++i) impl_->buffer[i].Set(x[i].real(),x[i].imag());
    impl_->plan->exec(impl_->buffer.data(),1.0,true);
    for (std::size_t i=0;i<size();++i) out[i]={impl_->buffer[i].r,impl_->buffer[i].i};
}
void Plan::inverse(std::span<const Complex> x, std::span<Complex> out) {
    for (std::size_t i=0;i<size();++i) impl_->buffer[i].Set(x[i].real(),x[i].imag());
    impl_->plan->exec(impl_->buffer.data(),1.0/static_cast<double>(size()),false);
    for (std::size_t i=0;i<size();++i) out[i]={impl_->buffer[i].r,impl_->buffer[i].i};
}
void Plan::inverse_real(std::span<const Complex> x, std::span<double> out) {
    for (std::size_t i=0;i<size();++i) impl_->buffer[i].Set(x[i].real(),x[i].imag());
    impl_->plan->exec(impl_->buffer.data(),1.0/static_cast<double>(size()),false);
    for (std::size_t i=0;i<size();++i) out[i]=impl_->buffer[i].r;
}
std::vector<Complex> fft(std::span<const double> x) { Plan p(x.size()); std::vector<Complex> y(x.size()); p.forward(x,y); return y; }
std::vector<Complex> fft(std::span<const Complex> x) { Plan p(x.size()); std::vector<Complex> y(x.size()); p.forward(x,y); return y; }
std::vector<Complex> ifft(std::span<const Complex> x) { Plan p(x.size()); std::vector<Complex> y(x.size()); p.inverse(x,y); return y; }
std::vector<double> convolve(std::span<const double> a, std::span<const double> b) {
    if (a.empty() || b.empty()) return {};
    const std::size_t length=a.size()+b.size()-1;
    std::size_t n=1; while(n<length) n*=2;
    Plan plan(n); std::vector<double> x(n,0.0),y(n,0.0),out(n);
    std::copy(a.begin(),a.end(),x.begin());std::copy(b.begin(),b.end(),y.begin());
    std::vector<Complex> ax(n),bx(n);plan.forward(x,ax);plan.forward(y,bx);
    for(std::size_t i=0;i<n;++i) ax[i]*=bx[i];
    plan.inverse_real(ax,out);out.resize(length);return out;
}
}
