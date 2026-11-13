#include <deconvolution/api.hpp>
#include <Eigen/SVD>
#include <Eigen/QR>
#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>
#include <stdexcept>

namespace cnn_compute::deconvolution {
using core::Array;
namespace {
    void valid(std::span< const double > x) {
        if (x.size( ) < 2) throw std::invalid_argument("峭度输入至少两个样本");
        for (double v : x)
            if (!std::isfinite(v)) throw std::invalid_argument("输入必须有限");
    }
    double magnitude(std::span< const double > x) {
        double m = 0;
        for (double v : x) m = std::max(m, std::abs(v));
        return m;
    }
    std::span< double > writable(Array &x) {
        return { x.data( ), static_cast< std::size_t >(x.size( )) };
    }
    // 无校验内部核：有限性由公开入口或调用方（迭代内 y 由本模块产出）保证；
    // 零能量是算法自身状态，保留抛出。
    double kurtosis_kernel(std::span< const double > x) {
        const double scale = magnitude(x);
        if (scale == 0) throw std::domain_error("零能量输出无法计算峭度");
        double p = 0, q = 0;
        for (double v : x) {
            double z = v / scale, z2 = z * z;
            p += z2;
            q += z2 * z2;
        }
        return x.size( ) * q / (p * p);
    }
    // 前提：period >= 1、order >= 1、period*order < x.size()（run 入口已保证）。
    double correlated_kurtosis_kernel(std::span< const double > x, int period, int order) {
        double scale = magnitude(x);
        if (scale == 0) throw std::domain_error("零能量输出无法计算相关峭度");
        double energy = 0, numerator = 0;
        for (double v : x) {
            double z = v / scale;
            energy += z * z;
        }
        for (std::size_t i = static_cast< std::size_t >(period) * order; i < x.size( ); ++i) {
            double product = 1;
            for (int m = 0; m <= order; ++m) product *= x[i - m * period] / scale;
            numerator += product * product;
        }
        return numerator / std::pow(energy, order + 1);
    }
}    // namespace
double normalized_kurtosis(std::span< const double > x) {
    valid(x);
    return kurtosis_kernel(x);
}
double correlated_kurtosis(std::span< const double > x, int period, int order) {
    valid(x);
    if (period <= 0 || order < 1 || static_cast< std::size_t >(period) * order >= x.size( ))
        throw std::invalid_argument("相关峭度周期或移位阶数无效");
    return correlated_kurtosis_kernel(x, period, order);
}
using QRInPlace = Eigen::HouseholderQR< Eigen::Ref< Eigen::MatrixXd > >;
struct Workspace::Impl {
    // 唯一的 N×L 存储：prepare 先按滑窗填入设计矩阵，随后被 QR 原地分解覆盖
    // （下区为 Householder 反射、上三角为 R），全程不存在第二份矩阵拷贝。
    Eigen::MatrixXd                  qr_storage;
    Eigen::VectorXd                  scaled;    // 去均值信号/最大幅值：迭代内 FIR 与设计矩阵列的公共源
    std::optional< QRInPlace >       qr;        // 借用 qr_storage
    Eigen::BDCSVD< Eigen::MatrixXd > decomposition;
    Eigen::VectorXd                  factors, coefficients, best, y, target, transformed, projected, updated;
    Array                            centered;
    Eigen::Index                     rows    = 0;    // 设计矩阵行数（矩阵转QR存储后仍需）
    int                              columns = 0;    // 滤波器长度 L
};
namespace {
    // QR 已由调用方在 qr_storage 上原地完成（w.qr 有效）；此处提取小 R 的 SVD
    // 并准备全部迭代向量容量。
    void factorize(Workspace::Impl &w, double ridge) {
        const auto rows = w.qr_storage.rows( ), l = w.qr_storage.cols( );
        w.rows    = rows;
        w.columns = static_cast< int >(l);
        // X=QR，SVD只作用于L×L的R。Q以Householder反射存储，不物化N×L的U；
        // 奇异值仍来自X的正交等价变换，不形成会平方条件数的XᵀX。
        Eigen::MatrixXd triangular = w.qr->matrixQR( ).topLeftCorner(l, l).template triangularView< Eigen::Upper >( );
        w.decomposition.compute(triangular, Eigen::ComputeFullU | Eigen::ComputeFullV);
        const auto &s = w.decomposition.singularValues( );
        if (w.decomposition.info( ) != Eigen::Success || !s.allFinite( ) || s[0] == 0)
            throw std::runtime_error("解卷积矩阵 SVD 数值退化");
        const double cutoff = std::numeric_limits< double >::epsilon( ) * std::max(rows, l) * s[0];
        if (ridge == 0 && (s.array( ) > cutoff).count( ) != l) throw std::runtime_error("无正则化解卷积矩阵数值秩亏");
        w.factors.resize(l);
        for (Eigen::Index j = 0; j < l; ++j) w.factors[j] = ridge == 0 ? 1 / s[j] : s[j] / (s[j] * s[j] + ridge);
        w.coefficients.resize(l);
        w.best.resize(l);
        w.projected.resize(l);
        w.updated.resize(l);
        w.y.resize(rows);
        w.target.resize(rows);
        w.transformed.resize(rows);
    }
    // energy 为调用方对 w.y 已算好的 squaredNorm（同一确定性归约，复用不重扫）。
    void mckd_target(Workspace::Impl &w, int period, int order, double energy) {
        const auto rows  = w.rows;
        const auto start = static_cast< Eigen::Index >(period) * order;
        w.target.setZero( );
        double beta_energy = 0;
        for (Eigen::Index i = start; i < rows; ++i) {
            double beta = 1;
            for (int m = 0; m <= order; ++m) beta *= w.y[i - m * period];
            beta_energy += beta * beta;
            for (int m = 0; m <= order; ++m) {
                double leave = 1;
                for (int k = 0; k <= order; ++k)
                    if (k != m) leave *= w.y[i - k * period];
                w.target[i - m * period] += beta * leave;
            }
        }
        if (!std::isfinite(beta_energy) || beta_energy == 0) throw std::runtime_error("MCKD周期乘积数值退化");
        w.target *= energy / (2 * beta_energy);
    }
    // target 发散最终由 updated 的 norm 检查兜底，迭代内不做全数组有限性扫描。
    void solve(Workspace::Impl &w) {
        // Qᵀ 的表达式只借用 QR 存储和实系数，不物化系数副本；直接应用于
        // 已准备的 transformed，避免乘积表达式另建目标向量。
        w.transformed = w.target;
        w.qr->householderQ( ).adjoint( ).applyThisOnTheLeft(w.transformed);
        w.projected.noalias( ) = w.decomposition.matrixU( ).transpose( ) * w.transformed.head(w.columns);
        w.projected.array( ) *= w.factors.array( );
        w.updated.noalias( ) = w.decomposition.matrixV( ) * w.projected;
    }
}    // namespace
Workspace::Workspace( ) : impl(std::make_unique< Impl >( )) {}
Workspace::~Workspace( )                               = default;
Workspace::Workspace(Workspace &&) noexcept            = default;
Workspace &Workspace::operator=(Workspace &&) noexcept = default;
void       Workspace::prepare(std::span< const double > signal, const Options &o) {
    valid(signal);
    if (signal.size( ) < 64 || o.filter_length < 2 || static_cast< std::size_t >(o.filter_length) >= signal.size( ) / 2
        || o.max_iterations < 1 || !std::isfinite(o.tolerance) || o.tolerance <= 0
        || !std::isfinite(o.ridge) || o.ridge < 0) throw std::invalid_argument("解卷积参数无效");
    auto      &w = *impl;
    const auto n = static_cast< Eigen::Index >(signal.size( ));
    const int  l = o.filter_length;
    w.centered   = core::Map(signal.data( ), n);
    w.centered -= w.centered.mean( );
    const double scale = w.centered.abs( ).maxCoeff( );
    if (scale == 0) throw std::domain_error("零能量信号无法解卷积");
    w.scaled        = (w.centered / scale).matrix( );
    const auto rows = n - l + 1;
    w.qr.reset( );    // 旧 Ref 借用的缓冲即将重建
    w.qr_storage.resize(rows, l);
    for (int j = 0; j < l; ++j) w.qr_storage.col(j) = w.scaled.segment(j, rows);
    // 固定设计矩阵只分解一次；保持基于X的SVD秩判定，不形成XᵀX。
    // 全程仅此一份 N×L：QR 经 Ref 在存储上原地分解，无 compute() 的整体拷贝。
    w.qr.emplace(w.qr_storage);
    factorize(w, o.ridge);
}
namespace execution {
    Info run(int period, int order, const Options &o, std::span< double > output,
             std::span< double > filter, std::span< double > history, Workspace &workspace) {
        auto      &w    = *workspace.impl;
        const auto rows = w.rows;
        const int  l    = o.filter_length;
        if (period && (period < 0 || order < 1 || static_cast< std::size_t >(period) * order + 1 >= static_cast< std::size_t >(rows)))
            throw std::invalid_argument("输入长度不足以覆盖MCKD周期和移位阶数");
        w.coefficients.setZero( );
        w.coefficients[l / 2] = 1;
        double best           = -std::numeric_limits< double >::infinity( );
        Info   info;
        for (int it = 0; it < o.max_iterations; ++it) {
            // y=X·f 的流式 FIR：设计矩阵第 j 列即 scaled 的滑窗段，j 升序逐列
            // AXPY，输入常驻缓存，替代每迭代流经整份 N×L 矩阵的 GEMV。
            w.y = w.scaled.segment(0, rows) * w.coefficients[0];
            for (int j = 1; j < l; ++j) w.y += w.scaled.segment(j, rows) * w.coefficients[j];
            const std::span< const double > y(w.y.data( ), rows);
            double                          objective = period ? correlated_kurtosis_kernel(y, period, order) : kurtosis_kernel(y);
            history[it]                               = objective;
            info.iterations                           = it + 1;
            if (objective > best) {
                best   = objective;
                w.best = w.coefficients;
            }
            if (it && std::abs(objective - history[it - 1]) <= o.tolerance * std::max(1.0, std::abs(history[it - 1]))) {
                info.converged = true;
                break;
            }
            const double energy = w.y.squaredNorm( );
            if (!period) {
                const double fourth = w.y.array( ).square( ).square( ).sum( );
                if (!std::isfinite(fourth) || fourth == 0) throw std::runtime_error("MED四阶矩数值退化");
                w.target.array( ) = energy / fourth * w.y.array( ).cube( );
            } else
                mckd_target(w, period, order, energy);
            solve(w);
            const double norm = w.updated.norm( );
            if (!std::isfinite(norm) || norm == 0) throw std::runtime_error("解卷积滤波器更新数值退化");
            w.coefficients = w.updated / norm;
        }
        std::copy(w.best.data( ), w.best.data( ) + l, filter.begin( ));
        // 与反转FIR的same卷积等价，短FIR直接计算避免FFT额外缓冲。
        // 首/尾边界段只覆盖有效下标，主体段无分支；j 升序求和次序不变。
        const auto         n        = w.centered.size( );
        const int          offset   = (l - 1) / 2;
        const Eigen::Index head_end = l - offset, body_end = n - offset;
        for (Eigen::Index i = 0; i < head_end; ++i) {
            double    sum = 0;
            const int jhi = static_cast< int >(i) + offset;
            for (int j = 0; j <= jhi; ++j) sum += w.centered[i + offset - j] * w.best[l - 1 - j];
            output[i] = sum;
        }
        for (Eigen::Index i = head_end; i < body_end; ++i) {
            double sum = 0;
            for (int j = 0; j < l; ++j) sum += w.centered[i + offset - j] * w.best[l - 1 - j];
            output[i] = sum;
        }
        for (Eigen::Index i = body_end; i < n; ++i) {
            double    sum = 0;
            const int jlo = static_cast< int >(i + offset - n + 1);
            for (int j = jlo; j < l; ++j) sum += w.centered[i + offset - j] * w.best[l - 1 - j];
            output[i] = sum;
        }
        return info;
    }
    Info med(const Options &o, std::span< double > out, std::span< double > f, std::span< double > h, Workspace &w) {
        return run(0, 0, o, out, f, h, w);
    }
    Info mckd(int p, int m, const Options &o, std::span< double > out, std::span< double > f, std::span< double > h, Workspace &w) {
        if (p <= 0) throw std::invalid_argument("MCKD周期必须为正整数");
        return run(p, m, o, out, f, h, w);
    }
}    // namespace execution
Result med(std::span< const double > x, const Options &o) {
    Workspace w;
    w.prepare(x, o);
    Result r{ Array(x.size( )), Array(o.filter_length), std::vector< double >(o.max_iterations), {} };
    r.info = execution::med(o, writable(r.signal), writable(r.filter), r.objective_history, w);
    r.objective_history.resize(r.info.iterations);
    return r;
}
Result mckd(std::span< const double > x, int p, int m, const Options &o) {
    Workspace w;
    w.prepare(x, o);
    Result r{ Array(x.size( )), Array(o.filter_length), std::vector< double >(o.max_iterations), {} };
    r.info = execution::mckd(p, m, o, writable(r.signal), writable(r.filter), r.objective_history, w);
    r.objective_history.resize(r.info.iterations);
    return r;
}
core::Array mckd_update(std::span< const double > matrix, std::size_t rows, std::size_t columns,
                        std::span< const double > filter, int period, int order, double ridge) {
    if (rows < columns || columns < 1 || matrix.size( ) != rows * columns || filter.size( ) != columns
        || period <= 0 || order < 1 || static_cast< std::size_t >(period) * order >= rows
        || !std::isfinite(ridge) || ridge < 0) throw std::invalid_argument("MCKD更新形状或参数无效");
    valid(matrix);
    valid(filter);
    Workspace workspace;
    auto     &w        = *workspace.impl;
    using Row          = Eigen::Matrix< double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor >;
    w.qr_storage       = Eigen::Map< const Row >(matrix.data( ), rows, columns);
    const double scale = w.qr_storage.cwiseAbs( ).maxCoeff( );
    if (scale == 0) throw std::runtime_error("MCKD输入矩阵零能量");
    w.qr_storage /= scale;
    w.coefficients = Eigen::Map< const Eigen::VectorXd >(filter.data( ), columns);
    // X 为任意行优先矩阵而非滑窗信号，此处保留通用 GEMV；
    // 须在 QR 原地覆盖 qr_storage 之前完成。
    w.y.noalias( )      = w.qr_storage * w.coefficients;
    const double energy = w.y.squaredNorm( );
    w.qr.emplace(w.qr_storage);
    factorize(w, ridge);
    mckd_target(w, period, order, energy);
    solve(w);
    return w.updated.array( );
}
}    // namespace cnn_compute::deconvolution
