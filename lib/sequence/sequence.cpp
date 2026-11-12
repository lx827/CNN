#include "api.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace cnn_compute::sequence {
namespace {
std::span<double> view(core::Array& a) { return {a.data(),static_cast<std::size_t>(a.size())}; }
double mean(std::span<const double> x) { return core::Map(x.data(),x.size()).mean(); }
void validate(std::span<const double> x) {
    if(x.empty()) throw std::invalid_argument("sequence must not be empty");
    for(double v:x) if(!std::isfinite(v)) throw std::invalid_argument("sequence must be finite");
}
}
std::pair<double,double> regression(std::span<const double> x,std::span<const double> y) {
    validate(y);
    if(x.size()!=y.size()) throw std::invalid_argument("regression axes must have equal lengths");
    double mx=mean(x),my=mean(y),var=0,cov=0;
    for(std::size_t i=0;i<x.size();++i) { double d=x[i]-mx;var+=d*d;cov+=d*(y[i]-my); }
    double slope=var==0?0:cov/var;
    return {slope,my-slope*mx};
}
namespace execution {
void holt(std::span<const double> y,std::span<double> l,std::span<double> b,
          std::span<double> s,std::span<double> fitted,std::span<double> forecast,
          double alpha,double beta,double gamma,int period,double initial_trend) {
    std::fill(s.begin(),s.end(),0.);
    std::size_t n=y.size(), init=std::min(n,static_cast<std::size_t>(period>0?period:4));
    l[0]=mean(y.first(init));b[0]=initial_trend;
    bool seasonal=period>=2;
    if(seasonal && n>=static_cast<std::size_t>(2*period)) {
        double a=mean(y.first(period)),c=mean(y.subspan(period,period)),sm=0.;
        for(int j=0;j<period;++j) {s[j]=(y[j]-a+y[period+j]-c)*.5;sm+=s[j];}
        sm/=period;for(int j=0;j<period;++j)s[j]-=sm;
    }
    fitted[0]=l[0]+b[0]+(seasonal?s[0]:0.);
    for(std::size_t i=1;i<n;++i) {
        double offset=seasonal?s[i>=static_cast<std::size_t>(period)?i-period:i%period]:0.;
        l[i]=alpha*(y[i]-offset)+(1-alpha)*(l[i-1]+b[i-1]);
        b[i]=beta*(l[i]-l[i-1])+(1-beta)*b[i-1];
        if(seasonal) s[i]=gamma*(y[i]-l[i])+(1-gamma)*s[i>=static_cast<std::size_t>(period)?i-period:i];
        fitted[i]=l[i-1]+b[i-1]+offset;
    }
    for(std::size_t h=1;h<=forecast.size();++h) {
        double offset=0.;
        if(seasonal&&n>=static_cast<std::size_t>(period)) {
            std::size_t j=(n-period+h)%period;offset=s[n-period+j];
        }
        forecast[h-1]=l[n-1]+h*b[n-1]+offset;
    }
}
void kalman(std::span<const double> y,std::span<double> score,std::span<double> rate,
            double process,double measurement,double& variance) {
    Eigen::Vector2d x(y[0],0.);
    Eigen::Matrix2d P=Eigen::Matrix2d::Zero();P(0,0)=measurement*measurement;P(1,1)=10.;
    Eigen::Matrix2d F;F<<1.,1.,0.,1.;
    Eigen::Matrix2d Q=Eigen::Matrix2d::Zero();Q(0,0)=process*process;Q(1,1)=2*process*process;
    double R=measurement*measurement;
    for(std::size_t i=0;i<y.size();++i) {
        if(i) {x=F*x;P=(F*P*F.transpose()+Q).eval();}
        double S=P(0,0)+R;
        if(!(S>0)) throw std::runtime_error("singular Kalman innovation covariance");
        Eigen::Vector2d K=P.col(0)/S;x+=K*(y[i]-x[0]);
        Eigen::Matrix2d A=Eigen::Matrix2d::Identity();A.col(0)-=K;
        P=(A*P*A.transpose()+R*K*K.transpose()).eval();
        score[i]=x[0];rate[i]=x[1];
    }
    variance=P(0,0);
}
}
HoltResult holt(std::span<const double> y,int steps,double a,double b,double g,int period,double initial) {
    validate(y);
    if(steps<0||a<0||a>1||b<0||b>1||g<0||g>1||period<0||!std::isfinite(initial))
        throw std::invalid_argument("invalid Holt parameters");
    HoltResult r{core::Array(y.size()),core::Array(y.size()),core::Array(y.size()),core::Array(y.size()),core::Array(steps)};
    execution::holt(y,view(r.level),view(r.trend),view(r.season),view(r.fitted),view(r.forecast),a,b,g,period,initial);return r;
}
KalmanResult kalman(std::span<const double> y,double q,double r) {
    validate(y);if(!std::isfinite(q)||!std::isfinite(r)||q<0||r<=0)throw std::invalid_argument("invalid Kalman noise");
    KalmanResult out{core::Array(y.size()),core::Array(y.size()),0};
    execution::kalman(y,view(out.score),view(out.rate),q,r,out.variance);return out;
}
CusumResult cusum(std::span<const double> values,double allowance,double alpha) {
    if(allowance<0||alpha<0||alpha>1)throw std::invalid_argument("invalid CUSUM parameters");
    CusumResult r{};
    for(double v:values) {r.final_positive=std::max(0.,r.final_positive+v-allowance);
        r.final_negative=std::max(0.,r.final_negative-v-allowance);
        r.positive=std::max(r.positive,r.final_positive);r.negative=std::max(r.negative,r.final_negative);
        r.ewma=alpha*v+(1-alpha)*r.ewma;}
    return r;
}
core::Array mann_whitney_z(std::span<const double> values,std::span<const double> ref,int window) {
    if(window<1||ref.empty())throw std::invalid_argument("Mann-Whitney windows must be nonempty");
    int hop=std::max(1,window/4);std::size_t count=values.size()<static_cast<std::size_t>(2*window)?0:1+(values.size()-2*window)/hop;
    core::Array out(count);double n1=ref.size(),n2=window,expected=n1*n2*.5,sigma=std::sqrt(n1*n2*(n1+n2+1)/12.);
    for(std::size_t k=0;k<count;++k) {
        auto current=values.subspan(window+k*hop,window);double u=0;
        for(double x:ref) for(double y:current) u+=x>y?1.:(x==y?.5:0.);
        out[k]=(std::min(u,n1*n2-u)-expected)/sigma;
    }return out;
}
std::pair<double,double> central_moment(std::span<const double> x,int degree,bool scaled) {
    validate(x);if(degree<1)throw std::invalid_argument("moment degree must be positive");
    double m=mean(x),scale=1.;
    if(scaled) {scale=0.;for(double v:x)scale=std::max(scale,std::abs(v-m));if(scale==0)return {0,0};}
    double moment=0,variance=0;for(double v:x){double d=(v-m)/scale;moment+=std::pow(d,degree);variance+=d*d;}
    return {moment/x.size(),variance/x.size()};
}
std::pair<core::Array,core::Array> window_moments(std::span<const double> values,int window) {
    if(window<1)throw std::invalid_argument("window must be positive");
    std::size_t n=values.size()/window;core::Array rms(n),kurt(n);
    for(std::size_t i=0;i<n;++i) {auto x=values.subspan(i*window,window);
        rms[i]=std::sqrt(core::Map(x.data(),x.size()).square().mean());
        auto [m,v]=central_moment(x,4);kurt[i]=v==0?std::numeric_limits<double>::quiet_NaN():m/(v*v);}
    return {std::move(rms),std::move(kurt)};
}
}
