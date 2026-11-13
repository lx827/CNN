#pragma once

#include <atomic>
#include <cstddef>
#include <memory>

namespace cnn_compute::core {

// 进程级不可变单槽缓存：持有构好后只读的预计算数据（FFT twiddle 表、Hann 窗等）。
// T 以 T(std::size_t) 构建并暴露 size()；构建必须确定性——同尺寸产生逐位相同的表，
// 因此并发未命中时重复构建再置换槽不改变结果，只是多付一次构建。
// obtain 命中同尺寸槽时只做一次原子读；尺寸变化时构建新表并原子置换槽指针，
// 旧表由在用调用方持有的 shared_ptr 存活至其调用结束，随后自动释放。
// 每个实例只有一个槽：交替尺寸每次重建、内存有界；不得改成按任意尺寸的无界 map。
// 实例放函数级 magic static 等进程级位置；表跨线程共享只读，不含可变状态。
template < class T >
class SingleSlot {
public:
    std::shared_ptr< const T > obtain(std::size_t size) {
#if defined(__cpp_lib_atomic_shared_ptr)
        auto current = slot_.load(std::memory_order_acquire);
        if (current && current->size( ) == size) return current;
        auto fresh = std::make_shared< T >(size);
        slot_.store(fresh, std::memory_order_release);
        return fresh;
#else
        auto current = std::atomic_load_explicit(&slot_, std::memory_order_acquire);
        if (current && current->size( ) == size) return current;
        auto fresh = std::make_shared< T >(size);
        std::atomic_store_explicit(&slot_, std::shared_ptr< const T >(fresh), std::memory_order_release);
        return fresh;
#endif
    }

private:
#if defined(__cpp_lib_atomic_shared_ptr)
    std::atomic< std::shared_ptr< const T > > slot_;
#else
    std::shared_ptr< const T > slot_;    // 仅经 atomic_load/atomic_store 访问
#endif
};
}    // namespace cnn_compute::core
