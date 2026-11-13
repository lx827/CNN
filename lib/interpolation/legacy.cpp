#include <core/interpolation.hpp>
#include <interpolation/execution.hpp>

#include <span>
#include <stdexcept>

// 旧 core 插值入口的兼容转发；PCHIP/cubic 导数、系数与分段求值的唯一实现在
// interpolation.cpp（SciPy 1.18.1 语义适配，BSD 归属见 ../LICENSE.scipy）。
// 输入前置条件由调用方保证，见 core/interpolation.hpp。
namespace cnn_compute::core {
namespace {

    interpolation::Method select(Interpolation method) {
        return method == Interpolation::pchip ? interpolation::Method::pchip
                                              : interpolation::Method::cubic;
    }

    Array run(std::span< const double > x, std::span< const double > y,
              std::span< const double > query, Interpolation method) {
        Array                    result(static_cast< Eigen::Index >(query.size( )));
        interpolation::Workspace workspace;
        interpolation::execution::interpolate(x, y, query, { result.data( ), query.size( ) },
                                              select(method), workspace);
        if (!result.isFinite( ).all( )) throw std::runtime_error("插值产生非有限值");
        return result;
    }
}    // namespace

Array interpolate(const Knots &points, const Array &query, Interpolation method) {
    return run({ points.locations.data( ), static_cast< std::size_t >(points.locations.size( )) },
               { points.values.data( ), static_cast< std::size_t >(points.values.size( )) },
               { query.data( ), static_cast< std::size_t >(query.size( )) }, method);
}

Array pchip(std::span< const double > x, std::span< const double > y, std::span< const double > query) {
    return run(x, y, query, Interpolation::pchip);
}

Array cubic(std::span< const double > x, std::span< const double > y, std::span< const double > query) {
    return run(x, y, query, Interpolation::cubic);
}

}    // namespace cnn_compute::core
