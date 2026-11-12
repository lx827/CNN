#include "arrays.hpp"

#include <cmath>
#include <memory>

namespace cnn_compute::bind {

std::span< const double > input(const ArrayInput &array, py::ssize_t minimum) {
    if (array.ndim( ) != 1 || array.size( ) < minimum)
        throw py::value_error("输入必须是一维且满足最小长度");
    const auto values = std::span< const double >(array.data( ), array.size( ));
    for (const double value : values)
        if (!std::isfinite(value)) throw py::value_error("输入必须全部有限");
    return values;
}
py::array_t< double > output(core::Array &&values) {
    auto        owner = std::make_unique< core::Array >(std::move(values));
    auto       *ptr   = owner.get( );
    py::capsule capsule(ptr, [](void *value) {
        delete static_cast< core::Array * >(value);
    });
    owner.release( );
    return py::array_t< double >({ ptr->size( ) }, { sizeof(double) }, ptr->data( ), capsule);
}
}    // namespace cnn_compute::bind
