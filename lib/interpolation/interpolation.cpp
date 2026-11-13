#include <interpolation/execution.hpp>
#include <solvers/execution.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace cnn_compute::interpolation {
namespace {
    using core::Array;
    // Eigen packet 中间层：求值循环按 lane 并行，逐元素运算次序与标量一致。
    namespace ei         = Eigen::internal;
    using Packet         = ei::packet_traits< double >::type;
    constexpr auto lanes = ei::unpacket_traits< Packet >::size;

    double endpoint(double h0, double h1, double m0, double m1) {
        double d    = ((2.0 * h0 + h1) * m0 - h0 * m1) / (h0 + h1);
        auto   sign = [](double v) { return (v > 0.0) - (v < 0.0); };
        if (sign(d) != sign(m0)) return 0.0;
        if (sign(m0) != sign(m1) && std::abs(d) > 3.0 * std::abs(m0)) return 3.0 * m0;
        return d;
    }

    // 三次 B 样条在单个查询点只有四个非零基函数；固定栈空间。
    std::array< double, 4 > basis(const double *knots, std::ptrdiff_t span, double x) {
        std::array< double, 4 > values{ 1.0, 0.0, 0.0, 0.0 }, left{}, right{};
        for (int degree = 1; degree <= 3; ++degree) {
            left[degree]  = x - knots[span + 1 - degree];
            right[degree] = knots[span + degree] - x;
            double saved  = 0.0;
            for (int r = 0; r < degree; ++r) {
                const double temp = values[r] / (right[r + 1] + left[degree - r]);
                values[r]         = saved + right[r + 1] * temp;
                saved             = left[degree - r] * temp;
            }
            values[degree] = saved;
        }
        return values;
    }

    void fit_spline(std::span< const double > x, std::span< const double > y, Workspace &w) {
        const std::size_t n = x.size( );
        for (int j = 0; j < 4; ++j) {
            w.knots[j]     = x.front( );
            w.knots[n + j] = x.back( );
        }
        for (std::size_t j = 2; j + 2 < n; ++j) w.knots[j + 2] = x[j];
        w.band.head(static_cast< Eigen::Index >(n * 7)).setZero( );
        auto band = [&](std::ptrdiff_t row, std::ptrdiff_t column) -> double & {
            return w.band[row * 7 + column - row + 3];
        };
        // 节点严格递增：span 单调推进，与逐点 interval() 二分结果一致；
        // 基函数按 lane 并行递推后散布进带内，每 lane 运算序列与标量
        // basis() 相同；span 不变时节点零重复装载。
        const auto     limit  = static_cast< std::ptrdiff_t >(n);
        const double  *kn     = w.knots.data( );
        std::ptrdiff_t span   = 2;
        auto           locate = [&](double q) {
            while (span < limit && kn[span + 1] <= q) ++span;
            return std::clamp< std::ptrdiff_t >(span, 3, limit - 1);
        };
        double         ks[6][lanes], vs[4][lanes];
        std::ptrdiff_t span_of[lanes] = {};
        bool           fresh          = true;
        Packet         knot[6];
        for (auto &k : knot) k = ei::pset1< Packet >(0.0);
        const auto full = n / lanes * lanes;
        for (std::size_t row = 0; row < full; row += lanes) {
            bool changed = false;
            for (int lane = 0; lane < lanes; ++lane) {
                const auto s = locate(x[row + lane]);
                if (fresh || s != span_of[lane]) {
                    span_of[lane] = s;
                    for (int k = 0; k < 6; ++k) ks[k][lane] = kn[s - 2 + k];
                    changed = true;
                }
            }
            if (changed) {
                for (int k = 0; k < 6; ++k) knot[k] = ei::ploadu< Packet >(ks[k]);
                fresh = false;
            }
            Packet values[4], left[4], right[4];
            values[0] = ei::pset1< Packet >(1.0);
            values[1] = values[2] = values[3] = ei::pset1< Packet >(0.0);
            const Packet qp                   = ei::ploadu< Packet >(x.data( ) + row);
            left[1]                           = ei::psub(qp, knot[2]);
            right[1]                          = ei::psub(knot[3], qp);
            left[2]                           = ei::psub(qp, knot[1]);
            right[2]                          = ei::psub(knot[4], qp);
            left[3]                           = ei::psub(qp, knot[0]);
            right[3]                          = ei::psub(knot[5], qp);
            for (int degree = 1; degree <= 3; ++degree) {
                Packet saved = ei::pset1< Packet >(0.0);
                for (int r = 0; r < degree; ++r) {
                    const Packet temp = ei::pdiv(values[r], ei::padd(right[r + 1], left[degree - r]));
                    values[r]         = ei::padd(saved, ei::pmul(right[r + 1], temp));
                    saved             = ei::pmul(left[degree - r], temp);
                }
                values[degree] = saved;
            }
            for (int j = 0; j < 4; ++j) {
                ei::pstoreu(vs[j], values[j]);
                for (int lane = 0; lane < lanes; ++lane)
                    band(static_cast< std::ptrdiff_t >(row + lane), span_of[lane] - 3 + j) = vs[j][lane];
            }
            for (int lane = 0; lane < lanes; ++lane) w.fit_rhs[row + lane] = y[row + lane];
        }
        for (std::size_t row = full; row < n; ++row) {
            const auto span   = locate(x[row]);
            const auto values = basis(w.knots.data( ), span, x[row]);
            for (int j = 0; j < 4; ++j) band(static_cast< std::ptrdiff_t >(row), span - 3 + j) = values[j];
            w.fit_rhs[row] = y[row];
        }
        // 有序节点的 B 样条配置矩阵全正，带宽固定；无需通用稠密求解。
        for (std::ptrdiff_t pivot = 0; pivot < static_cast< std::ptrdiff_t >(n); ++pivot) {
            const auto stop = std::min< std::ptrdiff_t >(n - 1, pivot + 3);
            for (auto row = pivot + 1; row <= stop; ++row) {
                const double factor = band(row, pivot) / band(pivot, pivot);
                for (auto column = pivot + 1; column <= stop; ++column)
                    band(row, column) -= factor * band(pivot, column);
                w.fit_rhs[row] -= factor * w.fit_rhs[pivot];
            }
        }
        for (auto row = static_cast< std::ptrdiff_t >(n) - 1; row >= 0; --row) {
            double rhs = w.fit_rhs[row];
            for (auto column = row + 1; column <= std::min< std::ptrdiff_t >(n - 1, row + 3); ++column)
                rhs -= band(row, column) * w.coefficients[column];
            w.coefficients[row] = rhs / band(row, row);
        }
    }

    // PCHIP/cubic 导数、分段系数与求值兼容 SciPy 1.18.1；BSD 见 ../LICENSE.scipy。
    void derivatives(std::span< const double > x, std::span< const double > y, Method method,
                     Workspace &w) {
        const std::size_t n = x.size( );
        for (std::size_t i = 0; i + 1 < n; ++i) {
            w.h[i]     = x[i + 1] - x[i];
            w.slope[i] = (y[i + 1] - y[i]) / w.h[i];
        }
        if (n == 2) {
            w.derivative.head(2).setConstant(w.slope[0]);
            return;
        }
        if (method == Method::pchip) {
            w.derivative[0]     = endpoint(w.h[0], w.h[1], w.slope[0], w.slope[1]);
            w.derivative[n - 1] = endpoint(w.h[n - 2], w.h[n - 3], w.slope[n - 2], w.slope[n - 3]);
            for (std::size_t i = 1; i + 1 < n; ++i) {
                const double before = w.slope[i - 1], after = w.slope[i];
                if (before == 0.0 || after == 0.0 || (before > 0.0) != (after > 0.0)) {
                    w.derivative[i] = 0.0;
                } else {
                    const double w1 = 2.0 * w.h[i] + w.h[i - 1];
                    const double w2 = w.h[i] + 2.0 * w.h[i - 1];
                    w.derivative[i] = 1.0 / ((w1 / before + w2 / after) / (w1 + w2));
                }
            }
            return;
        }
        // cubic 与 splrep 的 not-a-knot 边界一致，但此路径输出 PPoly，
        // splrep 走上面的 B 样条拟合/求值，分别进行数值差分。
        if (n == 3) {
            const double curvature = (w.slope[1] - w.slope[0]) / (w.h[0] + w.h[1]);
            w.derivative[0]        = w.slope[0] - curvature * w.h[0];
            w.derivative[1]        = w.slope[0] + curvature * w.h[0];
            w.derivative[2]        = w.slope[1] + curvature * w.h[1];
            return;
        }
        for (std::size_t i = 1; i + 1 < n; ++i) {
            w.diagonal[i]  = 2.0 * (w.h[i - 1] + w.h[i]);
            w.upper[i]     = w.h[i - 1];
            w.lower[i - 1] = w.h[i];
            w.rhs[i]       = 3.0 * (w.h[i] * w.slope[i - 1] + w.h[i - 1] * w.slope[i]);
        }
        w.diagonal[0]     = w.h[1];
        w.upper[0]        = x[2] - x[0];
        double length     = x[2] - x[0];
        w.rhs[0]          = ((w.h[0] + 2.0 * length) * w.h[1] * w.slope[0]
                             + w.h[0] * w.h[0] * w.slope[1])
                            / length;
        w.diagonal[n - 1] = w.h[n - 3];
        w.lower[n - 2]    = x[n - 1] - x[n - 3];
        length            = x[n - 1] - x[n - 3];
        w.rhs[n - 1]      = (w.h[n - 2] * w.h[n - 2] * w.slope[n - 3]
                             + (2.0 * length + w.h[n - 2]) * w.h[n - 3] * w.slope[n - 2])
                            / length;
        solvers::execution::solve_tridiagonal({ w.lower.data( ), n - 1 }, { w.diagonal.data( ), n },
                                              { w.upper.data( ), n - 1 }, { w.rhs.data( ), n });
        w.derivative.head(n) = w.rhs.head(n);
    }
}    // namespace

void Workspace::prepare(std::size_t nodes, std::size_t) {
    if (static_cast< std::size_t >(derivative.size( )) < nodes) {
        for (auto *item : { &h, &slope, &derivative, &diagonal, &lower, &upper, &rhs,
                            &coefficients, &fit_rhs }) item->resize(nodes);
        knots.resize(nodes + 4);
        band.resize(nodes * 7);
    }
}

namespace execution {
    void interpolate(std::span< const double > x, std::span< const double > y,
                     std::span< const double > query, std::span< double > output,
                     Method method, Workspace &w) {
        const auto n = x.size( );
        w.prepare(n, query.size( ));
        if (method == Method::splrep) {
            fit_spline(x, y, w);
            // 区间选择：查询不降时推进指针摊还 O(1)，回退则二分；两者均与
            // interval() 的逐点 upper_bound 完全一致。基函数递推按 lane
            // 并行，每 lane 的除/乘/加序列与标量 basis() 一致；节点与
            // 系数只随 span 变化，span 不变的查询零重复装载。
            const double  *kn       = w.knots.data( );
            const auto     limit    = static_cast< std::ptrdiff_t >(n);
            std::ptrdiff_t span     = 2;
            double         previous = -std::numeric_limits< double >::infinity( );
            auto           locate   = [&](double q) {
                if (q < previous)
                    span = std::upper_bound(kn + 3, kn + limit + 1, q) - kn - 1;
                else
                    while (span < limit && kn[span + 1] <= q) ++span;
                previous = q;
                return std::clamp< std::ptrdiff_t >(span, 3, limit - 1);
            };
            const auto     count = query.size( );
            double         ks[6][lanes], cs[4][lanes], qs[lanes];
            std::ptrdiff_t span_of[lanes] = {};
            bool           fresh          = true;
            Packet         knot[6], coefficient[4];
            for (auto &k : knot) k = ei::pset1< Packet >(0.0);
            for (auto &c : coefficient) c = ei::pset1< Packet >(0.0);
            std::size_t i = 0;
            for (; i + lanes <= count; i += lanes) {
                bool changed = false;
                for (int lane = 0; lane < lanes; ++lane) {
                    const auto s = locate(query[i + lane]);
                    qs[lane]     = query[i + lane];
                    if (fresh || s != span_of[lane]) {
                        span_of[lane] = s;
                        for (int k = 0; k < 6; ++k) ks[k][lane] = kn[s - 2 + k];
                        for (int j = 0; j < 4; ++j) cs[j][lane] = w.coefficients[s - 3 + j];
                        changed = true;
                    }
                }
                if (changed) {
                    for (int k = 0; k < 6; ++k) knot[k] = ei::ploadu< Packet >(ks[k]);
                    for (int j = 0; j < 4; ++j) coefficient[j] = ei::ploadu< Packet >(cs[j]);
                    fresh = false;
                }
                const Packet qp = ei::ploadu< Packet >(qs);
                // left[d]=x-knots[span+1-d]，right[d]=knots[span+d]-x。
                Packet values[4], left[4], right[4];
                values[0] = ei::pset1< Packet >(1.0);
                values[1] = values[2] = values[3] = ei::pset1< Packet >(0.0);
                left[1]                           = ei::psub(qp, knot[2]);
                right[1]                          = ei::psub(knot[3], qp);
                left[2]                           = ei::psub(qp, knot[1]);
                right[2]                          = ei::psub(knot[4], qp);
                left[3]                           = ei::psub(qp, knot[0]);
                right[3]                          = ei::psub(knot[5], qp);
                for (int degree = 1; degree <= 3; ++degree) {
                    Packet saved = ei::pset1< Packet >(0.0);
                    for (int r = 0; r < degree; ++r) {
                        const Packet temp = ei::pdiv(values[r], ei::padd(right[r + 1], left[degree - r]));
                        values[r]         = ei::padd(saved, ei::pmul(right[r + 1], temp));
                        saved             = ei::pmul(left[degree - r], temp);
                    }
                    values[degree] = saved;
                }
                Packet value = ei::pset1< Packet >(0.0);
                for (int j = 0; j < 4; ++j)
                    value = ei::padd(value, ei::pmul(coefficient[j], values[j]));
                ei::pstoreu(output.data( ) + i, value);
            }
            for (; i < count; ++i) {
                const auto span   = locate(query[i]);
                const auto values = basis(w.knots.data( ), span, query[i]);
                double     value  = 0.0;
                for (int j = 0; j < 4; ++j) value += w.coefficients[span - 3 + j] * values[j];
                output[i] = value;
            }
        } else {
            derivatives(x, y, method, w);
            // 分段求值沿用 SciPy PPoly 常数到三次项的累加次序，不重排表达式。
            // 区间选择同 splrep 路径：单调推进 + 乱序回退二分，与逐点
            // upper_bound 一致。Horner 的区间不变量（t/c0/c1 等）只随
            // j 变化重算——纯函数同输入同位级结果；每个查询的求值序列
            // 保持 y+d0·dx+c1·dx²+c0·dx³ 不变。
            const double  *nodes    = x.data( );
            const auto     limit    = static_cast< std::ptrdiff_t >(n);
            std::ptrdiff_t found    = -1;
            double         previous = -std::numeric_limits< double >::infinity( );
            auto           locate   = [&](double q) {
                if (q < previous)
                    found = std::upper_bound(nodes, nodes + limit, q) - nodes - 1;
                else
                    while (found + 1 < limit && nodes[found + 1] <= q) ++found;
                previous = q;
                return std::clamp< std::ptrdiff_t >(found, 0, limit - 2);
            };
            const auto     count = query.size( );
            double         hs[lanes], ss[lanes], d0s[lanes], d1s[lanes], xs[lanes], ys[lanes];
            std::ptrdiff_t interval_of[lanes] = {};
            bool           fresh              = true;
            Packet         hp = ei::pset1< Packet >(0.0), sp = hp, d0 = hp, xp = hp, yp = hp, t = hp,
                           c0 = hp, c1 = hp;
            std::size_t    i = 0;
            for (; i + lanes <= count; i += lanes) {
                bool changed = false;
                for (int lane = 0; lane < lanes; ++lane) {
                    const auto j = locate(query[i + lane]);
                    if (fresh || j != interval_of[lane]) {
                        interval_of[lane] = j;
                        hs[lane]          = w.h[j];
                        ss[lane]          = w.slope[j];
                        d0s[lane]         = w.derivative[j];
                        d1s[lane]         = w.derivative[j + 1];
                        xs[lane]          = nodes[j];
                        ys[lane]          = y[j];
                        changed           = true;
                    }
                }
                if (changed) {
                    hp    = ei::ploadu< Packet >(hs);
                    sp    = ei::ploadu< Packet >(ss);
                    d0    = ei::ploadu< Packet >(d0s);
                    xp    = ei::ploadu< Packet >(xs);
                    yp    = ei::ploadu< Packet >(ys);
                    t     = ei::pdiv(ei::psub(ei::padd(d0, ei::ploadu< Packet >(d1s)), ei::pmul(ei::pset1< Packet >(2.0), sp)), hp);
                    c0    = ei::pdiv(t, hp);
                    c1    = ei::psub(ei::pdiv(ei::psub(sp, d0), hp), t);
                    fresh = false;
                }
                const Packet dx    = ei::psub(ei::ploadu< Packet >(query.data( ) + i), xp);
                Packet       value = ei::padd(yp, ei::pmul(d0, dx));
                Packet       power = ei::pmul(dx, dx);
                value              = ei::padd(value, ei::pmul(c1, power));
                power              = ei::pmul(power, dx);
                value              = ei::padd(value, ei::pmul(c0, power));
                ei::pstoreu(output.data( ) + i, value);
            }
            for (; i < count; ++i) {
                const auto   j = locate(query[i]);
                const double h = w.h[j], slope = w.slope[j];
                const double t  = (w.derivative[j] + w.derivative[j + 1] - 2.0 * slope) / h;
                const double dx = query[i] - nodes[j];
                const double c0 = t / h, c1 = (slope - w.derivative[j]) / h - t;
                double       value = y[j];
                value += w.derivative[j] * dx;
                double power = dx * dx;
                value += c1 * power;
                power *= dx;
                value += c0 * power;
                output[i] = value;
            }
        }
    }
}    // namespace execution

core::Array interpolate(std::span< const double > x, std::span< const double > y,
                        std::span< const double > query, Method method) {
    const std::size_t minimum = method == Method::splrep ? 4 : 2;
    if (x.size( ) < minimum || x.size( ) != y.size( )) throw std::invalid_argument("插值节点数量无效");
    for (std::size_t i = 0; i < x.size( ); ++i)
        if (!std::isfinite(x[i]) || !std::isfinite(y[i]) || (i && x[i] <= x[i - 1]))
            throw std::invalid_argument("插值节点必须有限且严格递增");
    for (double value : query)
        if (!std::isfinite(value)) throw std::invalid_argument("查询必须有限");
    Array     result(query.size( ));
    Workspace workspace;
    execution::interpolate(x, y, query, { result.data( ), query.size( ) }, method, workspace);
    return result;
}
}    // namespace cnn_compute::interpolation
