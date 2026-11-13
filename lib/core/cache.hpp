#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <memory>
#include <mutex>

namespace cnn_compute::core {

// 共享只读预计算表的小型 LRU；T(size) 构造且 size() 返回容量计量单位。
// 同时限制条目数与 size() 总量，超预算的表只交给调用者，不驻留缓存。
// obtain 的锁只保护索引；构造在锁外，竞争者可重复构造但只保留一份。
// 返回 owner 独立持有表；逐出不使在用表失效，活跃调用内存另计。
// 表必须构后只读；缓存自身不保存可写执行缓冲，不创建线程。
template < class T, std::size_t Capacity = 4 >
class BoundedCache {
public:
    explicit BoundedCache(std::size_t budget) : budget_(budget) {}

    std::shared_ptr< const T > obtain(std::size_t size) {
        {
            std::lock_guard lock(mutex_);
            if (auto current = find(size)) return current;
        }
        auto fresh = std::make_shared< T >(size);
        if (size > budget_) return fresh;
        std::lock_guard lock(mutex_);
        if (auto current = find(size)) return current;
        while (count_ == Capacity || used_ + size > budget_) {
            used_ -= entries_[count_ - 1]->size( );
            entries_[--count_].reset( );
        }
        std::move_backward(entries_.begin( ), entries_.begin( ) + count_, entries_.begin( ) + count_ + 1);
        entries_[0] = fresh;
        ++count_;
        used_ += size;
        return fresh;
    }

private:
    std::shared_ptr< const T > find(std::size_t size) {
        for (std::size_t i = 0; i < count_; ++i) {
            if (entries_[i]->size( ) != size) continue;
            auto current = entries_[i];
            std::move_backward(entries_.begin( ), entries_.begin( ) + i, entries_.begin( ) + i + 1);
            entries_[0] = current;
            return current;
        }
        return {};
    }

    std::array< std::shared_ptr< const T >, Capacity > entries_;
    std::size_t                                        count_ = 0, used_ = 0;
    const std::size_t                                  budget_;
    std::mutex                                         mutex_;
};
}    // namespace cnn_compute::core
