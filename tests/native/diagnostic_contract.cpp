#include <adaptive/api.hpp>
#include <deconvolution/api.hpp>
#include <diagnostic/api.hpp>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>

int main() {
    using namespace cnn_compute;
    adaptive::Workspace aw;
    for(std::size_t n:{256,384,128}) {
        std::vector<double> x(n),out(n);
        for(std::size_t i=0;i<n;++i) x[i]=std::sin(0.3*i)+0.2*std::cos(0.7*i);
        adaptive::Options options;options.method=adaptive::Method::nlms;
        aw.prepare(n,options.filter_length);adaptive::execution::filter(x,out,options,aw);
        auto public_result=adaptive::filter(x,options);
        for(std::size_t i=0;i<n;++i) if(std::abs(out[i]-public_result[i])>1e-13) throw std::runtime_error("adaptive execution mismatch");
    }
    deconvolution::Workspace dw;deconvolution::Options options{8,4,1e-6,1e-8};
    for(std::size_t n:{256,384,128}) {
        std::vector<double> x(n),out(n),filter(8),history(4);
        for(std::size_t i=0;i<n;++i) x[i]=std::sin(0.3*i)+0.1*std::cos(0.71*i)+(i%31==0?2:0);
        dw.prepare(x,options);auto info=deconvolution::execution::med(options,out,filter,history,dw);
        auto public_result=deconvolution::med(x,options);auto snapshot=public_result.signal;
        if(info.iterations!=public_result.info.iterations) throw std::runtime_error("deconvolution status mismatch");
        for(std::size_t i=0;i<n;++i) if(std::abs(out[i]-public_result.signal[i])>1e-12) throw std::runtime_error("deconvolution execution mismatch");
        dw.prepare(x,options);
        if((snapshot!=public_result.signal).any()) throw std::runtime_error("result borrowed workspace");
    }
    std::cout<<"diagnostic workspaces and public paths passed\n";
}
