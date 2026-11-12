#include "modules.hpp"

namespace py = pybind11;

PYBIND11_MODULE(_native, module) {
    module.doc() = "诊断计算库原生内核与构建信息";
    auto core = module.def_submodule("core", "公共数组数值计算与构建信息");
    auto emd = module.def_submodule("emd", "EMD 包络与完整单 IMF 筛分");
    cnn_compute::bind::bind_core(core);
    cnn_compute::bind::bind_emd(emd);

    // 保留既有包入口与局部差分入口；别名复用同一导出函数。
    module.attr("build_info") = core.attr("build_info");
    module.attr("_pchip") = core.attr("pchip");
    module.attr("_cubic") = core.attr("cubic");
    for (const auto* name : {"sift_pchip_sd", "sift_imf", "_envelopes_pchip",
                             "_envelopes", "_rilling_stop"})
        module.attr(name) = emd.attr(name);
}
