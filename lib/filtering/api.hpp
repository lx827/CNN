#pragma once
#include <array>
#include <cstddef>
#include <memory>
#include <span>
#include <vector>

namespace cnn_compute::filtering {
using Sos = std::array< double, 6 >;
// Butterworth SOS：low<=0 为低通，high>=fs/2 为高通，否则带通。
// 参数为 Hz；返回的系数独立拥有，a0=1。设计时分配，执行可重复使用。
std::vector< Sos > butterworth(int order, double low_hz, double high_hz, double fs);
struct Workspace {
    std::vector< double > padded;
    void                  prepare(std::size_t samples, std::size_t sections, int padlen = -1);
};
namespace execution {
    // 输出等长；input/output 不重叠。先 prepare 或允许执行在规模增长时扩容。
    // odd 延拓，padlen=-1 采用 SciPy SOS 默认长度；工作区不并发共享。
    void sosfiltfilt(std::span< const double > input, std::span< const Sos > sos,
                     std::span< double > output, Workspace &workspace, int padlen = -1);
}    // namespace execution
std::vector< double > sosfiltfilt(std::span< const double > input,
                                  std::span< const Sos > sos, int padlen = -1);
// 周期 Hann，N=1 时为 1；输出由返回值拥有。
std::vector< double > hann(std::size_t samples);
// 进程级单槽缓存的周期 Hann 表（与 hann 同一公式）：同尺寸重复调用零重建零分配；
// 尺寸变化时原子置换槽，旧表由在用调用方持有至调用结束。表构建后只读，可跨线程共享。
// 面向频谱/倒谱等全长窗复用；窗长很短的调用方直接 hann 即可，不占槽。
struct HannTable {
    std::size_t           samples;
    std::vector< double > values;
    explicit HannTable(std::size_t n);
    std::size_t size( ) const {
        return samples;
    }
};
std::shared_ptr< const HannTable > hann_table(std::size_t samples);
std::vector< double >              detrend(std::span< const double > input, bool linear = false);
// Savitzky-Golay：奇数窗口，interp 端点，delta 为导数间隔；系数预计算后复用。
std::vector< double > savgol(std::span< const double > input, int window, int order,
                             int derivative = 0, double delta = 1.0);
}    // namespace cnn_compute::filtering
