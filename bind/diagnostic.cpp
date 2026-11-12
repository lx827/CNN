#include "arrays.hpp"
#include <adaptive/api.hpp>
#include <deconvolution/api.hpp>
#include <diagnostic/api.hpp>
#include <ica/api.hpp>
#include <pybind11/complex.h>
#include <pybind11/stl.h>

namespace cnn_compute::bind {
namespace {
template<class T> py::array_t<T> owned(std::vector<T>&& values,std::size_t rows=0,std::size_t columns=0) {
    auto storage=std::make_unique<std::vector<T>>(std::move(values));auto* pointer=storage.get();
    py::capsule capsule(pointer,[](void* p){delete static_cast<std::vector<T>*>(p);});storage.release();
    if(columns) return py::array_t<T>({static_cast<py::ssize_t>(rows),static_cast<py::ssize_t>(columns)},
        {static_cast<py::ssize_t>(sizeof(T)*columns),static_cast<py::ssize_t>(sizeof(T))},pointer->data(),capsule);
    return py::array_t<T>({static_cast<py::ssize_t>(pointer->size())},{sizeof(T)},pointer->data(),capsule);
}
std::span<const double> vector(const ArrayInput& a) {
    if(a.ndim()!=1) throw py::value_error("输入必须一维");return {a.data(),static_cast<std::size_t>(a.size())};
}
py::array_t<double> matrix(ica::Matrix&& a) {return owned(std::move(a.values),a.rows,a.columns);}
}
void bind_diagnostic(py::module_& module) {
    module.def("deconvolve",[](const ArrayInput& input,int length,int iterations,double tolerance,double ridge,int period,int shift) {
        deconvolution::Result r;auto x=vector(input);deconvolution::Options o{length,iterations,tolerance,ridge};
        {py::gil_scoped_release release;r=period?deconvolution::mckd(x,period,shift,o):deconvolution::med(x,o);}
        return py::make_tuple(output(std::move(r.signal)),output(std::move(r.filter)),owned(std::move(r.objective_history)),r.info.iterations,r.info.converged);
    },py::arg("input").noconvert(),py::arg("filter_length"),py::arg("max_iterations"),py::arg("tolerance"),py::arg("ridge"),py::arg("period")=0,py::arg("shift_order")=1);
    module.def("normalized_kurtosis",[](const ArrayInput& input) {auto x=vector(input);py::gil_scoped_release release;return deconvolution::normalized_kurtosis(x);},py::arg("input").noconvert());
    module.def("mckd_update",[](const ArrayInput& matrix,const ArrayInput& filter,int period,int order,double ridge) {
        if(matrix.ndim()!=2) throw py::value_error("MCKD设计矩阵必须二维");auto coefficients=vector(filter);core::Array r;
        {py::gil_scoped_release release;r=deconvolution::mckd_update({matrix.data(),static_cast<std::size_t>(matrix.size())},matrix.shape(0),matrix.shape(1),coefficients,period,order,ridge);}return output(std::move(r));
    },py::arg("matrix").noconvert(),py::arg("filter").noconvert(),py::arg("period"),py::arg("shift_order"),py::arg("ridge"));
    module.def("correlated_kurtosis",[](const ArrayInput& input,int period,int order) {auto x=vector(input);py::gil_scoped_release release;return deconvolution::correlated_kurtosis(x,period,order);},py::arg("input").noconvert(),py::arg("period"),py::arg("shift_order")=1);
    module.def("adaptive_filter",[](const ArrayInput& input,int method,int length,double step,int delay,std::size_t max_updates,
                                   double alpha,double gamma,double minimum,double maximum) {
        if(method<0||method>2) throw py::value_error("未知自适应滤波方法");
        adaptive::Options o{static_cast<adaptive::Method>(method),length,delay,max_updates,step,alpha,gamma,minimum,maximum};
        core::Array result;auto x=vector(input);{py::gil_scoped_release release;result=adaptive::filter(x,o);}return output(std::move(result));
    },py::arg("input").noconvert(),py::arg("method"),py::arg("filter_length"),py::arg("step_size"),py::arg("delay"),py::arg("max_updates"),
      py::arg("alpha"),py::arg("gamma"),py::arg("minimum_step"),py::arg("maximum_step"));
    module.def("fast_ica",[](const ArrayInput& input,int count,int iterations,double tolerance,std::uint64_t seed) {
        if(input.ndim()!=2) throw py::value_error("ICA输入必须samples×channels");ica::Result r;
        {py::gil_scoped_release release;r=ica::fast_ica({input.data(),static_cast<std::size_t>(input.size())},input.shape(0),input.shape(1),{count,iterations,tolerance,seed});}
        return py::make_tuple(matrix(std::move(r.components)),matrix(std::move(r.mixing)),matrix(std::move(r.unmixing)),output(std::move(r.mean)),r.numerical_rank,r.iterations,static_cast<int>(r.status));
    },py::arg("input").noconvert(),py::arg("components"),py::arg("max_iterations"),py::arg("tolerance"),py::arg("seed"));
    module.def("teager",[](const ArrayInput& input) {core::Array r;auto x=vector(input);{py::gil_scoped_release release;r=diagnostic::teager(x);}return output(std::move(r));},py::arg("input").noconvert());
    module.def("complex_spectral_kurtosis",[](const py::array_t<std::complex<double>,py::array::c_style>& input) {
        if(input.ndim()!=1) throw py::value_error("谱峭度输入必须一维");py::gil_scoped_release release;
        return diagnostic::complex_spectral_kurtosis({input.data(),static_cast<std::size_t>(input.size())});
    },py::arg("input").noconvert());
    module.def("cepstral_prewhiten",[](const ArrayInput& input,double fs,const ArrayInput& comb,double width) {
        core::Array r;auto x=vector(input),frequencies=vector(comb);{py::gil_scoped_release release;r=diagnostic::cepstral_prewhiten(x,fs,frequencies,width);}return output(std::move(r));
    },py::arg("input").noconvert(),py::arg("sample_rate"),py::arg("comb").noconvert(),py::arg("width"));
    module.def("sc_scoh",[](const ArrayInput& input,double fs,const ArrayInput& alpha,std::size_t length,std::size_t step) {
        diagnostic::CyclicResult r;auto x=vector(input),frequencies=vector(alpha);
        {py::gil_scoped_release release;r=diagnostic::sc_scoh(x,fs,frequencies,length,step);}
        return py::make_tuple(owned(std::move(r.correlation),r.rows,r.columns),owned(std::move(r.coherence),r.rows,r.columns),r.segments,r.input_scale);
    },py::arg("input").noconvert(),py::arg("sample_rate"),py::arg("alpha").noconvert(),py::arg("segment_length"),py::arg("step"));
    module.def("modulation_bispectrum",[](const ArrayInput& input,double fs,const ArrayInput& carrier,const ArrayInput& modulation,
                                          std::size_t length,std::size_t step,std::size_t minimum) {
        diagnostic::MSBResult r;auto x=vector(input),c=vector(carrier),m=vector(modulation);
        {py::gil_scoped_release release;r=diagnostic::modulation_bispectrum(x,fs,c,m,length,step,minimum);}
        return py::make_tuple(owned(std::move(r.mean),r.rows,r.columns),owned(std::move(r.coherence),r.rows,r.columns),owned(std::move(r.valid),r.rows,r.columns),r.segments);
    },py::arg("input").noconvert(),py::arg("sample_rate"),py::arg("carriers").noconvert(),py::arg("modulation").noconvert(),py::arg("segment_length"),py::arg("step"),py::arg("minimum_segments"));
    module.def("filter_bank_kurtogram",[](const ArrayInput& input,double fs,int level,double minimum,int order) {
        std::vector<diagnostic::BandStatistics> result;auto x=vector(input);
        {py::gil_scoped_release release;result=diagnostic::filter_bank_kurtogram(x,fs,level,minimum,order);}
        py::list rows;for(const auto& r:result) rows.append(py::make_tuple(r.low_hz,r.high_hz,r.level,r.spectral_kurtosis,r.impulsiveness,r.signal_to_background));return rows;
    },py::arg("input").noconvert(),py::arg("sample_rate"),py::arg("max_level"),py::arg("min_frequency"),py::arg("filter_order"));
}
}
