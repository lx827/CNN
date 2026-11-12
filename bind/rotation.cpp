#include "arrays.hpp"
#include <rotation/api.hpp>
#include <sequence/api.hpp>
#include <pybind11/stl.h>

namespace cnn_compute::bind {
namespace {
namespace r=cnn_compute::rotation;
namespace s=cnn_compute::sequence;
template<class F> auto compute(F&& f){py::gil_scoped_release release;return f();}
auto pair_output(std::pair<core::Array,core::Array>&& p){return py::make_tuple(output(std::move(p.first)),output(std::move(p.second)));}
auto speed_output(const r::SpeedResult& r){return py::make_tuple(r.frequency,r.source,r.reason);}
}
void bind_rotation(py::module_& root){
    auto module=root.def_submodule("rotation","转速、相位、阶次与齿轮数值表示");
    auto sequence=root.def_submodule("sequence","趋势与非参数序列统计");
    module.def("integrate",[](const ArrayInput& t,const ArrayInput& f){auto a=input(t,1),b=input(f,1);return output(compute([&]{return r::integrate(a,b);}));});
    module.def("interpolate",[](const ArrayInput& x,const ArrayInput& y,const ArrayInput& target,bool zero){auto a=input(x,1),b=input(y,1),c=input(target,1);return output(compute([&]{return r::interpolate(a,b,c,zero);}));});
    module.def("angle_resample",[](const ArrayInput& x,const ArrayInput& phase,int spr){auto a=input(x,1),b=input(phase,1);return output(compute([&]{return r::angle_resample(a,b,spr);}));});
    module.def("amplitude_spectrum",[](const ArrayInput& x,bool center){auto a=input(x,2);return output(compute([&]{return r::amplitude_spectrum(a,center);}));});
    module.def("periodic_components",[](const ArrayInput& x,const ArrayInput& orders){auto a=input(x,2),b=input(orders,0);return output(compute([&]{return r::periodic_components(a,b);}));});
    module.def("tsa",[](const ArrayInput& x,int spr,int minimum){auto a=input(x,1);return pair_output(compute([&]{return r::tsa(a,spr,minimum);}));});
    module.def("tsa_components",[](const ArrayInput& cycle,const ArrayInput& mesh,const ArrayInput& regular,int revolutions){auto a=input(cycle,2),b=input(mesh,0),c=input(regular,0);
        auto out=compute([&]{return r::tsa_components(a,b,c,revolutions);});return py::make_tuple(output(std::move(out.mesh)),output(std::move(out.regular)),output(std::move(out.residual)),output(std::move(out.differential)),output(std::move(out.amplitude)));});
    module.def("zoom_spectrum",[](const ArrayInput& x,double fs,double low,double high,int points){auto a=input(x,64);return output(compute([&]{return r::zoom_spectrum(a,fs,low,high,points);}));});
    module.def("real_cepstrum",[](const ArrayInput& x){auto a=input(x,64);return output(compute([&]{return r::real_cepstrum(a);}));});
    module.def("amfm",[](const ArrayInput& x,double fs){auto a=input(x,64);auto out=compute([&]{return r::amfm(a,fs);});return py::make_tuple(output(std::move(out.envelope)),output(std::move(out.frequency)));});
    module.def("band_envelope",[](const ArrayInput& x,double fs,double low,double high){auto a=input(x,32);return output(compute([&]{return r::band_envelope(a,fs,low,high);}));});
    module.def("window_peaks",[](const ArrayInput& axis,const ArrayInput& values,const ArrayInput& centers,double width,bool disjoint){auto a=input(axis,1),b=input(values,1),c=input(centers,0);return output(compute([&]{return r::window_peaks(a,b,c,width,disjoint);}));});
    module.def("band_sum",[](const ArrayInput& axis,const ArrayInput& values,double center,double width){auto a=input(axis,1),b=input(values,1);return compute([&]{return r::band_sum(a,b,center,width);});});
    module.def("local_peak",[](const ArrayInput& axis,const ArrayInput& values,double center,double width,double inner,double outer,const ArrayInput& exclusions,bool median){auto a=input(axis,1),b=input(values,1),c=input(exclusions,0);
        auto out=compute([&]{return r::local_peak(a,b,center,width,inner,outer,c,median);});return py::make_tuple(out.coordinate,out.amplitude,out.background,out.background_count,out.found);});
    module.def("car_features",[](const ArrayInput& axis,const ArrayInput& values,const ArrayInput& targets,double width){auto a=input(axis,1),b=input(values,1),c=input(targets,1);auto out=compute([&]{return r::car_features(a,b,c,width);});
        return py::make_tuple(output(std::move(out.coordinate)),output(std::move(out.amplitude)),out.background,out.background_count);});
    module.def("order_statistics",[](const ArrayInput& x){auto a=input(x,1);return compute([&]{return r::order_statistics(a);});});
    module.def("spectrum_speed",[](const ArrayInput& x,double fs,double low,double high,int harmonics,double bandwidth,double smoothing){auto a=input(x,1);return speed_output(compute([&]{return r::spectrum_speed(a,fs,low,high,harmonics,bandwidth,smoothing);}));});
    module.def("autocorrelation_speed",[](const ArrayInput& x,double fs,double low,double high){auto a=input(x,1);return speed_output(compute([&]{return r::autocorrelation_speed(a,fs,low,high);}));});
    module.def("envelope_speed",[](const ArrayInput& x,double fs,double carrier,double low,double high,double bandwidth){auto a=input(x,1);return speed_output(compute([&]{return r::envelope_speed(a,fs,carrier,low,high,bandwidth);}));});
    module.def("speed_ridge",[](const ArrayInput& x,double fs,double low,double high,int window,int hop,double peak,double energy,double reliable,int boundaries,double fraction){
        auto a=input(x,64);r::RidgeParameters p{peak,energy,reliable,fraction,boundaries};auto out=compute([&]{return r::speed_ridge(a,fs,low,high,window,hop,p);});
        return py::make_tuple(output(std::move(out.frequency)),out.reliable,out.total,out.reason);
    });
    module.def("cvs",[](const ArrayInput& x,const ArrayInput& carrier,const ArrayInput& planet,double azimuth,double sensor,double half,int spr){auto a=input(x,64),b=input(carrier,64),c=input(planet,64);
        auto out=compute([&]{return r::cvs(a,b,c,azimuth,sensor,half,spr);});return py::make_tuple(output(std::move(out.signal)),out.intervals,out.cycles,out.coverage,out.completed_intervals);
    });
    sequence.def("holt",[](const ArrayInput& x,int steps,double alpha,double beta,double gamma,int period,double initial){auto a=input(x,1);auto out=compute([&]{return s::holt(a,steps,alpha,beta,gamma,period,initial);});
        return py::make_tuple(output(std::move(out.level)),output(std::move(out.trend)),output(std::move(out.season)),output(std::move(out.fitted)),output(std::move(out.forecast)));
    });
    sequence.def("kalman",[](const ArrayInput& x,double q,double noise){auto a=input(x,1);auto out=compute([&]{return s::kalman(a,q,noise);});return py::make_tuple(output(std::move(out.score)),output(std::move(out.rate)),out.variance);});
    sequence.def("cusum",[](const ArrayInput& x,double allowance,double alpha){auto a=input(x,0);auto out=compute([&]{return s::cusum(a,allowance,alpha);});return py::make_tuple(out.positive,out.negative,out.final_positive,out.final_negative,out.ewma);});
    sequence.def("mann_whitney_z",[](const ArrayInput& x,const ArrayInput& ref,int window){auto a=input(x,1),b=input(ref,1);return output(compute([&]{return s::mann_whitney_z(a,b,window);}));});
    sequence.def("regression",[](const ArrayInput& x,const ArrayInput& y){auto a=input(x,1),b=input(y,1);return compute([&]{return s::regression(a,b);});});
    sequence.def("central_moment",[](const ArrayInput& x,int degree,bool scaled){auto a=input(x,1);return compute([&]{return s::central_moment(a,degree,scaled);});});
    sequence.def("window_moments",[](const ArrayInput& x,int window){auto a=input(x,1);return pair_output(compute([&]{return s::window_moments(a,window);}));});
    sequence.def("robust_standardize",[](const ArrayInput& x){auto a=input(x,1);return output(compute([&]{return s::robust_standardize(a);}));});
    sequence.def("sign_cusum",[](const ArrayInput& x,double reference,bool use_median){auto a=input(x,1);auto out=compute([&]{return s::sign_cusum(a,reference,use_median);});return py::make_tuple(out.first.positive,out.first.negative,out.second);});
}
}
