#include <adaptive/api.hpp>
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace cnn_compute::adaptive {
void Workspace::prepare(std::size_t n,int l) {reference.resize(n);weights.resize(l);}
namespace execution {
void filter(std::span<const double> x,std::span<double> out,const Options& o,Workspace& w) {
    const auto n=x.size();const int l=o.filter_length;w.reference.setZero();w.weights.setZero();
    for(std::size_t i=o.delay;i<n;++i) w.reference[i]=x[i-o.delay];
    std::copy(x.begin(),x.begin()+l,out.begin());double mu=o.step_size;
    for(std::size_t i=l;i<n;++i) {
        auto reference=w.reference.segment(i-l+1,l);
        const double error=x[i]-(w.weights*reference).sum();out[i]=error;
        if(!o.max_updates || i-l<o.max_updates) {
            double step=mu;
            if(o.method==Method::nlms) step/=reference.square().sum()+1e-6;
            else if(o.method==Method::variable_step) {mu=std::clamp(o.alpha*mu+o.gamma*error*error,o.minimum_step,o.maximum_step);step=mu;}
            w.weights+=step*error*reference;
        }
        if(!std::isfinite(error)) throw std::runtime_error("自适应滤波数值发散");
    }
    Eigen::Map<core::Array> y(out.data(),out.size());y-=y.mean();
}
}
core::Array filter(std::span<const double> x,const Options& o) {
    if(o.filter_length<1 || o.delay<0 || x.size()<=static_cast<std::size_t>(o.filter_length)+o.delay
       || !std::isfinite(o.step_size)||o.step_size<=0 || !std::isfinite(o.alpha)||o.alpha<0||o.alpha>1
       || !std::isfinite(o.gamma)||o.gamma<0 || !std::isfinite(o.minimum_step)||o.minimum_step<=0
       || !std::isfinite(o.maximum_step)||o.maximum_step<o.minimum_step)
        throw std::invalid_argument("自适应滤波输入或参数无效");
    for(double v:x) if(!std::isfinite(v)) throw std::invalid_argument("输入必须有限");
    Workspace w;w.prepare(x.size(),o.filter_length);core::Array out(x.size());
    execution::filter(x,{out.data(),static_cast<std::size_t>(out.size())},o,w);return out;
}
}
