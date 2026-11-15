#include <ica/api.hpp>
#include <Eigen/SVD>
#include <algorithm>
#include <cmath>
#include <limits>
#include <random>
#include <stdexcept>

namespace cnn_compute::ica {
using Dense     = Eigen::MatrixXd;
using RowMatrix = Eigen::Matrix< double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor >;
struct Workspace::Impl {
    Dense                     centered, whitening, z, w, projection, g, update, updated, comparison;
    Eigen::VectorXd           derivative;
    Eigen::JacobiSVD< Dense > svd;
};
Workspace::Workspace( ) : impl(std::make_unique< Impl >( )) {}
Workspace::~Workspace( )                               = default;
Workspace::Workspace(Workspace &&) noexcept            = default;
Workspace &Workspace::operator=(Workspace &&) noexcept = default;
void       Workspace::prepare(std::size_t n, std::size_t c, std::size_t k) {
    auto &w = *impl;
    w.centered.resize(n, c);
    w.whitening.resize(c, k);
    w.z.resize(n, k);
    w.w.resize(k, k);
    w.projection.resize(n, k);
    w.g.resize(n, k);
    w.update.resize(k, k);
    w.updated.resize(k, k);
    w.comparison.resize(k, k);
    w.derivative.resize(k);
}
namespace {
    Matrix owned(const Dense &x) {
        Matrix r{ static_cast< std::size_t >(x.rows( )), static_cast< std::size_t >(x.cols( )), std::vector< double >(x.size( )) };
        Eigen::Map< RowMatrix >(r.values.data( ), x.rows( ), x.cols( )) = x;
        return r;
    }
}    // namespace
namespace execution {
    Result fast_ica(std::span< const double > x, std::size_t n, std::size_t channels,
                    const Options &o, Workspace &workspace) {
        auto                         &w = *workspace.impl;
        Result                        result;
        const auto                    count = o.components ? o.components : static_cast< int >(channels);
        Eigen::Map< const RowMatrix > values(x.data( ), n, channels);
        result.mean = values.colwise( ).mean( ).transpose( ).array( );
        w.centered  = values.rowwise( ) - result.mean.matrix( ).transpose( );
        w.svd.compute(w.centered, Eigen::ComputeThinV);
        if (w.svd.info( ) != Eigen::Success) throw std::runtime_error("ICA白化SVD失败");
        auto         singular = w.svd.singularValues( );
        const double cutoff   = std::numeric_limits< double >::epsilon( ) * std::max(n, channels) * singular[0];
        result.numerical_rank = (singular.array( ) > cutoff).count( );
        if (count > result.numerical_rank) {
            result.status = Status::rank_deficient;
            return result;
        }
        w.whitening = w.svd.matrixV( ).leftCols(count);
        for (int j = 0; j < count; ++j) w.whitening.col(j) *= std::sqrt(static_cast< double >(n)) / singular[j];
        w.z.noalias( ) = w.centered * w.whitening;
        std::mt19937_64                    rng(o.seed);
        std::normal_distribution< double > normal;
        for (Eigen::Index i = 0; i < w.w.size( ); ++i) w.w.data( )[i] = normal(rng);
        w.svd.compute(w.w, Eigen::ComputeFullU | Eigen::ComputeFullV);
        w.w.noalias( ) = w.svd.matrixU( ) * w.svd.matrixV( ).transpose( );
        for (int it = 0; it < o.max_iterations; ++it) {
            result.iterations       = it + 1;
            w.projection.noalias( ) = w.z * w.w.transpose( );
            w.g                     = w.projection.array( ).tanh( ).matrix( );
            w.derivative            = (1 - w.g.array( ).square( )).colwise( ).mean( );
            w.update.noalias( )     = w.g.transpose( ) * w.z / static_cast< double >(n);
            for (int j = 0; j < count; ++j) w.update.row(j) -= w.derivative[j] * w.w.row(j);
            w.svd.compute(w.update, Eigen::ComputeFullU | Eigen::ComputeFullV);
            const auto &s = w.svd.singularValues( );
            if (w.svd.info( ) != Eigen::Success || !s.allFinite( ) || s[count - 1] <= std::numeric_limits< double >::epsilon( ) * count * s[0]) {
                result.status = Status::singular_update;
                return result;
            }
            w.updated.noalias( )    = w.svd.matrixU( ) * w.svd.matrixV( ).transpose( );
            w.comparison.noalias( ) = w.updated * w.w.transpose( );
            double change           = (w.comparison.diagonal( ).array( ).abs( ) - 1).abs( ).maxCoeff( );
            w.w.swap(w.updated);
            if (change < o.tolerance) {
                result.status = Status::converged;
                break;
            }
        }
        w.update.noalias( ) = w.w * w.whitening.transpose( );
        // unmixing可为矩形；以SVD伪逆恢复物理通道尺度。
        result.unmixing         = owned(w.update);
        w.projection.noalias( ) = w.centered * w.update.transpose( );
        result.components       = owned(w.projection);
        w.svd.compute(w.update, Eigen::ComputeThinU | Eigen::ComputeThinV);
        auto         inverse   = w.svd.singularValues( );
        const double threshold = 1e-15 * inverse[0];
        for (Eigen::Index j = 0; j < inverse.size( ); ++j) inverse[j] = inverse[j] > threshold ? 1 / inverse[j] : 0;
        Dense mixing  = w.svd.matrixV( ) * inverse.asDiagonal( ) * w.svd.matrixU( ).transpose( );
        result.mixing = owned(mixing);
        return result;
    }
}    // namespace execution
Result fast_ica(std::span< const double > x, std::size_t n, std::size_t c, const Options &o) {
    if (n < 2 || c < 2 || c > 32 || x.size( ) != n * c || o.components < 0
        || o.max_iterations < 1 || !std::isfinite(o.tolerance) || o.tolerance <= 0)
        throw std::invalid_argument("ICA输入形状或参数无效");
    for (double v : x)
        if (!std::isfinite(v)) throw std::invalid_argument("ICA输入必须有限");
    Workspace w;
    w.prepare(n, c, o.components ? std::min< std::size_t >(o.components, c) : c);
    return execution::fast_ica(x, n, c, o, w);
}
}    // namespace cnn_compute::ica
