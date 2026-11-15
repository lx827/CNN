#pragma once

#include <core/array.hpp>
#include <pybind11/numpy.h>
#include <span>

namespace cnn_compute::bind {

namespace py     = pybind11;
using ArrayInput = py::array_t< double, py::array::c_style >;

// 只在 Python 调用边界检查有限、连续的一维输入；内核只读借用。
std::span< const double > input(const ArrayInput &array, py::ssize_t minimum);
// 独立 Eigen 缓冲区通过 capsule 交给 NumPy，避免输出复制。
py::array_t< double > output(core::Array &&values);

}    // namespace cnn_compute::bind
