#include <core/cache.hpp>
#include <array>
#include <atomic>
#include <memory>
#include <stdexcept>
#include <thread>

namespace {
struct Table {
    explicit Table(std::size_t n) : samples(n) {
        ++builds;
    }
    std::size_t size( ) const {
        return samples;
    }
    std::size_t                      samples;
    static inline std::atomic< int > builds = 0;
};
void require(bool condition) {
    if (!condition) throw std::runtime_error("bounded precomputation cache contract");
}
}    // namespace

int main( ) {
    using cnn_compute::core::BoundedCache;
    BoundedCache< Table > cache(128000 + 25600 + 262144);
    const auto            full    = cache.obtain(128000);
    const auto            segment = cache.obtain(25600);
    const auto            padded  = cache.obtain(262144);
    const int             builds  = Table::builds;
    for (int i = 0; i < 3; ++i) {
        require(cache.obtain(128000) == full);
        require(cache.obtain(25600) == segment);
        require(cache.obtain(262144) == padded);
    }
    require(Table::builds == builds);
    // 超预算不逐出常用计划，owner 在缓存销毁/逐出后依然独立存活。
    require(cache.obtain(1000000)->size( ) == 1000000);
    require(cache.obtain(128000) == full);
    BoundedCache< Table, 2 >     small(10);
    std::weak_ptr< const Table > evicted = small.obtain(3);
    auto                         held    = small.obtain(4);
    small.obtain(5);
    require(evicted.expired( ));
    require(held->size( ) == 4);
    auto newer = small.obtain(6);
    require(held->size( ) == 4 && newer->size( ) == 6);
    // 两个活跃调用共享只读表；每个返回 owner 都须可读。
    std::array< std::thread, 2 > workers;
    for (auto &worker : workers) worker = std::thread([&] {
                                     for (int i = 0; i < 32; ++i) require(cache.obtain(25600) == segment);
                                 });
    for (auto &worker : workers) worker.join( );
}
