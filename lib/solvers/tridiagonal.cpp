#include <core/tridiagonal.hpp>
#include <solvers/api.hpp>
#include <solvers/execution.hpp>

// 单右端项的 partial-pivot 消元次序适配 LAPACK 3.12.1 DGTSV。
// 来源与 BSD 归属见 ../LICENSE.lapack；不依赖 Fortran 或 BLAS 运行时。
#include <cmath>
#include <stdexcept>
#include <utility>

namespace cnn_compute::solvers::execution {

void solve_tridiagonal(std::span<double> lower, std::span<double> diagonal,
                       std::span<double> upper, std::span<double> rhs) {
    const auto n = static_cast<std::ptrdiff_t>(diagonal.size());
    for (Eigen::Index i = 0; i < n - 2; ++i) {
        if (std::abs(diagonal[i]) >= std::abs(lower[i])) {
            if (diagonal[i] == 0.0) throw std::runtime_error("三对角矩阵奇异");
            const double factor = lower[i] / diagonal[i];
            diagonal[i + 1] = diagonal[i + 1] - factor * upper[i];
            rhs[i + 1] = rhs[i + 1] - factor * rhs[i];
            lower[i] = 0.0;
        } else {
            const double factor = diagonal[i] / lower[i];
            diagonal[i] = lower[i];
            double temporary = diagonal[i + 1];
            diagonal[i + 1] = upper[i] - factor * temporary;
            // 原 lower 缓冲区复用于消元填充的第二条上对角线，始终 O(N)。
            lower[i] = upper[i + 1];
            upper[i + 1] = -factor * lower[i];
            upper[i] = temporary;
            temporary = rhs[i];
            rhs[i] = rhs[i + 1];
            rhs[i + 1] = temporary - factor * rhs[i + 1];
        }
    }
    const auto i = n - 2;
    if (std::abs(diagonal[i]) >= std::abs(lower[i])) {
        if (diagonal[i] == 0.0) throw std::runtime_error("三对角矩阵奇异");
        const double factor = lower[i] / diagonal[i];
        diagonal[i + 1] = diagonal[i + 1] - factor * upper[i];
        rhs[i + 1] = rhs[i + 1] - factor * rhs[i];
    } else {
        const double factor = diagonal[i] / lower[i];
        diagonal[i] = lower[i];
        double temporary = diagonal[i + 1];
        diagonal[i + 1] = upper[i] - factor * temporary;
        upper[i] = temporary;
        temporary = rhs[i];
        rhs[i] = rhs[i + 1];
        rhs[i + 1] = temporary - factor * rhs[i + 1];
    }
    if (diagonal[n - 1] == 0.0) throw std::runtime_error("三对角矩阵奇异");
    rhs[n - 1] /= diagonal[n - 1];
    rhs[n - 2] = (rhs[n - 2] - upper[n - 2] * rhs[n - 1]) / diagonal[n - 2];
    for (Eigen::Index row = n - 3; row >= 0; --row)
        rhs[row] = (rhs[row] - upper[row] * rhs[row + 1] - lower[row] * rhs[row + 2]) / diagonal[row];
}

} // namespace cnn_compute::solvers::execution

namespace cnn_compute::solvers {
core::Array solve_tridiagonal(core::Array lower, core::Array diagonal,
                              core::Array upper, core::Array rhs) {
    const auto n = diagonal.size();
    if (n < 2 || lower.size() != n - 1 || upper.size() != n - 1 || rhs.size() != n)
        throw std::invalid_argument("三对角数组形状无效");
    execution::solve_tridiagonal({lower.data(), static_cast<std::size_t>(lower.size())},
        {diagonal.data(), static_cast<std::size_t>(diagonal.size())},
        {upper.data(), static_cast<std::size_t>(upper.size())},
        {rhs.data(), static_cast<std::size_t>(rhs.size())});
    return rhs;
}
}
namespace cnn_compute::core {
Array solve_tridiagonal(Array lower, Array diagonal, Array upper, Array rhs) {
    return solvers::solve_tridiagonal(std::move(lower), std::move(diagonal),
                                     std::move(upper), std::move(rhs));
}
}
