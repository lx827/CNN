#include "arrays.hpp"
#include "modules.hpp"
#include <core/build_info.hpp>
#include <core/interpolation.hpp>
#include <core/tridiagonal.hpp>
#include <pybind11/typing.h>

namespace cnn_compute::bind {

void bind_core(py::module_ &module) {
    module.def("pchip", [](const ArrayInput &x, const ArrayInput &y, const ArrayInput &query) {
        const auto nodes = input(x, 2), values = input(y, 2), coordinates = input(query, 1);
        if (nodes.size() != values.size()) throw py::value_error("节点与值必须等长");
        for (std::size_t i = 1; i < nodes.size(); ++i)
            if (nodes[i] <= nodes[i - 1]) throw py::value_error("节点必须严格递增");
        core::Array result;
        {
            py::gil_scoped_release release;
            result = core::pchip(nodes, values, coordinates);
        }
        return output(std::move(result)); }, py::arg("x").noconvert( ), py::arg("y").noconvert( ), py::arg("query").noconvert( ));
    module.def("cubic", [](const ArrayInput &x, const ArrayInput &y, const ArrayInput &query) {
        const auto nodes = input(x, 2), values = input(y, 2), coordinates = input(query, 1);
        if (nodes.size() != values.size()) throw py::value_error("节点与值必须等长");
        for (std::size_t i = 1; i < nodes.size(); ++i)
            if (nodes[i] <= nodes[i - 1]) throw py::value_error("节点必须严格递增");
        core::Array result;
        {
            py::gil_scoped_release release;
            result = core::cubic(nodes, values, coordinates);
        }
        return output(std::move(result)); }, py::arg("x").noconvert( ), py::arg("y").noconvert( ), py::arg("query").noconvert( ));
    module.def("solve_tridiagonal", [](const ArrayInput &lower, const ArrayInput &diagonal, const ArrayInput &upper, const ArrayInput &rhs) {
        const auto d = input(diagonal, 4), l = input(lower, 3);
        const auto u = input(upper, 3), b = input(rhs, 4);
        if (l.size() + 1 != d.size() || u.size() + 1 != d.size() || b.size() != d.size())
            throw py::value_error("对角线和右端项长度必须匹配");
        core::Array result;
        {
            py::gil_scoped_release release;
            // 求解器就地消元，边界各复制一次以保留调用方输入。
            result = core::solve_tridiagonal(core::Map(l.data(), l.size()),
                core::Map(d.data(), d.size()), core::Map(u.data(), u.size()),
                core::Map(b.data(), b.size()));
        }
        return output(std::move(result)); }, py::arg("lower").noconvert( ), py::arg("diagonal").noconvert( ), py::arg("upper").noconvert( ), py::arg("rhs").noconvert( ));
    module.def("build_info", [] {
        const auto                              info = core::build_info( );
        py::typing::Dict< py::str, py::object > result;
        result["schema"]           = core::build_info_schema;
        result["compiler_id"]      = info.compiler_id;
        result["compiler_version"] = info.compiler_version;
        result["target_arch"]      = info.target_arch;
        result["arch_policy"]      = info.arch_policy;
        result["compile_options"]  = info.compile_options;
        result["simd"]             = info.simd;
        result["eigen_version"]    = py::make_tuple(info.eigen_major, info.eigen_minor, info.eigen_patch);
        return result;
    });
}

}    // namespace cnn_compute::bind
