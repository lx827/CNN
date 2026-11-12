#include <envelope/execution.hpp>

// emd 0.8.1 _sift_core.py 的极值延拓语义适配；来源及 GPL 归属见 ../LICENSE.emd。
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace cnn_compute::envelope {
namespace {
using Index = std::ptrdiff_t;
using Indices = std::vector<Index>;

void locate(std::span<const double> x, Indices& maxima, Indices& minima) {
    maxima.clear(); minima.clear();
    for (std::size_t i = 1; i + 1 < x.size(); ++i) {
        if (x[i] > x[i - 1] && x[i] > x[i + 1]) maxima.push_back(i);
        if (x[i] < x[i - 1] && x[i] < x[i + 1]) minima.push_back(i);
    }
}
// Python 正向切片后 flip，支持参考源码使用的负索引。
void reversed_slice(const Indices& source, Index start, Index end, Indices& dest) {
    const auto n = static_cast<Index>(source.size());
    start = std::clamp(start, Index{0}, n);
    end = std::clamp(end, Index{0}, n);
    dest.clear();
    for (Index i = end; i > start;) dest.push_back(source[--i]);
}
void append_reflected(std::span<const double> signal, const Indices& left,
                      const Indices& middle, const Indices& right, Index lsym, Index rsym,
                      std::vector<double>& x, std::vector<double>& y) {
    x.clear(); y.clear();
    for (auto i : left) { x.push_back(2.0 * lsym - i); y.push_back(signal[i]); }
    for (auto i : middle) { x.push_back(i); y.push_back(signal[i]); }
    for (auto i : right) { x.push_back(2.0 * rsym - i); y.push_back(signal[i]); }
}

void rilling(std::span<const double> x, int width, Workspace& w) {
    const auto& max = w.maxima; const auto& min = w.minima;
    auto& lm = w.left_max; auto& ln = w.left_min;
    auto& rm = w.right_max; auto& rn = w.right_min;
    const Index last = x.size() - 1, nmax = max.size(), nmin = min.size();
    Index lsym, rsym;
    if (max.front() < min.front()) {
        if (x.front() > x[min.front()]) {
            reversed_slice(max, 1, width + 1, lm); reversed_slice(min, 0, width, ln); lsym = max.front();
        } else {
            reversed_slice(max, 0, width, lm); reversed_slice(min, 0, width - 1, ln); ln.push_back(0); lsym = 0;
        }
    } else {
        if (x.front() > x[max.front()]) {
            reversed_slice(max, 0, width, lm); reversed_slice(min, 1, width + 1, ln); lsym = min.front();
        } else {
            reversed_slice(min, 0, width, ln); reversed_slice(max, 0, width - 1, lm); lm.push_back(0); lsym = 0;
        }
    }
    if (max.back() < min.back()) {
        if (x.back() < x[max.back()]) {
            reversed_slice(max, nmax - width, nmax, rm);
            reversed_slice(min, nmin - width - 1, nmin - 1, rn); rsym = min.back();
        } else {
            // -(width-2) 为 0 时，Python [-0:] 选择完整数组。
            reversed_slice(max, width <= 2 ? 2 - width : nmax - (width - 2), nmax, rm);
            rm.insert(rm.begin(), last);
            reversed_slice(min, width == 1 ? 0 : nmin - (width - 1), nmin, rn); rsym = last;
        }
    } else {
        if (x.back() > x[min.back()]) {
            reversed_slice(max, nmax - width - 1, nmax - 1, rm);
            reversed_slice(min, nmin - width, nmin, rn); rsym = max.back();
        } else {
            reversed_slice(max, width == 1 ? 0 : nmax - (width - 1), nmax, rm);
            reversed_slice(min, width <= 2 ? 2 - width : nmin - (width - 2), nmin, rn);
            rn.insert(rn.begin(), last); rsym = last;
        }
    }
    if (2 * lsym - ln.front() >= 0 || 2 * lsym - lm.front() >= 0) {
        if (lsym == max.front()) reversed_slice(max, 0, width, lm);
        else reversed_slice(min, 0, width, ln);
        lsym = 0;
    }
    if (2 * rsym - rn.back() <= last || 2 * rsym - rm.back() <= last) {
        if (rsym == max.back()) reversed_slice(max, nmax - width - 1, nmax - 1, rm);
        else reversed_slice(min, nmin - width - 1, nmin - 1, rn);
        rsym = x.size();
    }
    if (2 * lsym - ln.front() >= 0 || 2 * lsym - lm.front() >= 0
        || 2 * rsym - rn.back() <= last || 2 * rsym - rm.back() <= last)
        throw std::runtime_error("Rilling 极值延拓未覆盖输入");
    append_reflected(x, lm, max, rm, lsym, rsym, w.max_x, w.max_y);
    append_reflected(x, ln, min, rn, lsym, rsym, w.min_x, w.min_y);
}

void values(std::span<const double> input, const Indices& indices, bool parabolic,
            std::vector<double>& x, std::vector<double>& y) {
    x.clear(); y.clear();
    for (auto i : indices) {
        if (parabolic) {
            const double a = .5 * input[i - 1] - input[i] + .5 * input[i + 1];
            const double b = -2.5 * input[i - 1] + 4.0 * input[i] - 1.5 * input[i + 1];
            const double c = 3.0 * input[i - 1] - 3.0 * input[i] + input[i + 1];
            const double tp = -b / (2.0 * a);
            x.push_back(tp - 2.0 + i); y.push_back(tp * b / 2.0 + c);
        } else { x.push_back(i); y.push_back(input[i]); }
    }
}

// np.pad reflect/odd 的位置延拓与 median(stat_length=1) 幅值延拓。
void numpy_pad(std::vector<double>& x, std::vector<double>& y, std::size_t len, int width,
               Workspace& workspace) {
    width = std::min<int>(width, x.size());
    if (!width) return;
    do {
        const std::size_t n = x.size();
        auto& left = workspace.pad_left; auto& right = workspace.pad_right;
        left.resize(width); right.resize(width);
        // 参考默认 pad_width<=nextrema，极限 width==n 需重复反射一项。
        auto odd = [&](Index index) {
            double offset = 0.0;
            double sign = 1.0;
            while (index < 0 || index >= static_cast<Index>(n)) {
                if (index < 0) { offset += sign * 2.0 * x.front(); sign = -sign; index = -index; }
                if (index >= static_cast<Index>(n)) {
                    offset += sign * 2.0 * x.back(); sign = -sign; index = 2 * (n - 1) - index;
                }
            }
            return offset + sign * x[index];
        };
        for (int j = 0; j < width; ++j) { left[j] = odd(j - width); right[j] = odd(n + j); }
        const double first = y.front(), last = y.back();
        x.insert(x.begin(), left.begin(), left.end()); x.insert(x.end(), right.begin(), right.end());
        y.insert(y.begin(), width, first); y.insert(y.end(), width, last);
    } while (x.back() < static_cast<double>(len) || x.front() >= 0.0);
}

void queries(Workspace& w, double start, double end, std::size_t n) {
    // 上游先 arange(padded_first,padded_last)，再按 [0,N) 裁剪。
    const double first = start + std::max(0.0, std::ceil(-start));
    if (first >= 1.0 || first + n - 1 >= end)
        throw std::runtime_error("包络裁剪长度与输入不符");
    for (std::size_t i = 0; i < n; ++i) w.query[i] = first + i;
}

void interpolate(const std::vector<double>& x, const std::vector<double>& y,
                 std::span<double> out, const Options& options, Workspace& w) {
    const auto minimum = options.interpolation == interpolation::Method::splrep ? 4u : 2u;
    if (x.size() < minimum) throw std::runtime_error("包络插值节点不足");
    queries(w, x.front(), x.back(), out.size());
    interpolation::execution::interpolate(x, y, {w.query.data(), out.size()}, out,
                                          options.interpolation, w.interpolation);
    for (double value : out)
        if (!std::isfinite(value)) throw std::runtime_error("包络产生非有限值");
}

void validate(std::span<const double> signal, const Options& options) {
    if (signal.size() < 3) throw std::invalid_argument("包络输入至少三个采样点");
    for (double v : signal) if (!std::isfinite(v)) throw std::invalid_argument("包络输入必须有限");
    if (options.pad_width < 0) throw std::invalid_argument("延拓宽度不能为负");
    if (options.padding == Padding::rilling && options.parabolic_extrema)
        throw std::invalid_argument("参考实现不支持 Rilling 与抛物线极值组合");
}

bool prepare_extrema(std::span<const double> signal, const Options& options,
                     Workspace& w, bool both) {
    w.prepare(signal.size(), options.pad_width);
    locate(signal, w.maxima, w.minima);
    const bool rilling_padding = options.padding == Padding::rilling && options.pad_width > 0;
    if (w.maxima.size() < 2 || ((both || rilling_padding) && w.minima.size() < 2)) return false;
    if (rilling_padding) rilling(signal, options.pad_width, w);
    else {
        values(signal, w.maxima, options.parabolic_extrema, w.max_x, w.max_y);
        numpy_pad(w.max_x, w.max_y, signal.size(), options.pad_width, w);
        if (both) {
            values(signal, w.minima, options.parabolic_extrema, w.min_x, w.min_y);
            numpy_pad(w.min_x, w.min_y, signal.size(), options.pad_width, w);
        }
    }
    return true;
}
}

void Workspace::prepare(std::size_t samples, std::size_t padding) {
    const std::size_t nodes = samples + 2 * padding + 4;
    for (auto* item : {&maxima, &minima, &left_max, &left_min, &right_max, &right_min}) item->reserve(nodes);
    for (auto* item : {&max_x, &max_y, &min_x, &min_y}) item->reserve(nodes);
    pad_left.reserve(padding); pad_right.reserve(padding);
    if (static_cast<std::size_t>(query.size()) < samples) query.resize(samples);
    interpolation.prepare(nodes, samples);
}

namespace execution {
std::pair<std::size_t, std::size_t> count_extrema(std::span<const double> signal) {
    std::size_t maxima = 0, minima = 0;
    for (std::size_t i = 1; i + 1 < signal.size(); ++i) {
        maxima += signal[i] > signal[i - 1] && signal[i] > signal[i + 1];
        minima += signal[i] < signal[i - 1] && signal[i] < signal[i + 1];
    }
    return {maxima, minima};
}
bool extrema_envelopes(std::span<const double> signal, std::span<double> upper,
                       std::span<double> lower, const Options& options, Workspace& w) {
    if (!prepare_extrema(signal, options, w, true)) return false;
    interpolate(w.max_x, w.max_y, upper, options, w);
    interpolate(w.min_x, w.min_y, lower, options, w);
    return true;
}
bool upper_envelope(std::span<const double> signal, std::span<double> output,
                     const Options& options, Workspace& w) {
    if (!prepare_extrema(signal, options, w, false)) return false;
    interpolate(w.max_x, w.max_y, output, options, w);
    return true;
}
bool combined_envelope(std::span<const double> signal, std::span<double> out,
                       const Options& options, Workspace& w) {
    w.prepare(signal.size(), options.pad_width);
    w.maxima.clear();
    for (std::size_t i = 1; i + 1 < signal.size(); ++i)
        if (std::abs(signal[i]) > std::abs(signal[i - 1]) && std::abs(signal[i]) > std::abs(signal[i + 1]))
            w.maxima.push_back(i);
    if (w.maxima.size() < 2) return false;
    w.max_x.clear(); w.max_y.clear();
    for (auto i : w.maxima) {
        if (options.parabolic_extrema) {
            const double before = std::abs(signal[i - 1]), center = std::abs(signal[i]);
            const double after = std::abs(signal[i + 1]);
            const double a = .5 * before - center + .5 * after;
            const double b = -2.5 * before + 4.0 * center - 1.5 * after;
            const double c = 3.0 * before - 3.0 * center + after;
            const double tp = -b / (2.0 * a);
            w.max_x.push_back(tp - 2.0 + i); w.max_y.push_back(tp * b / 2.0 + c);
        } else { w.max_x.push_back(i); w.max_y.push_back(std::abs(signal[i])); }
    }
    numpy_pad(w.max_x, w.max_y, signal.size(), options.pad_width, w);
    interpolate(w.max_x, w.max_y, out, options, w);
    return true;
}
}

Extrema find_extrema(std::span<const double> signal, bool maxima, bool parabolic) {
    Indices positive, negative;
    locate(signal, positive, negative);
    std::vector<double> x, y;
    values(signal, maxima ? positive : negative, parabolic, x, y);
    Extrema result{core::Array(x.size()), core::Array(y.size())};
    std::copy(x.begin(), x.end(), result.locations.data()); std::copy(y.begin(), y.end(), result.values.data());
    return result;
}
std::optional<Envelopes> extrema_envelopes(std::span<const double> signal, const Options& options) {
    validate(signal, options);
    Envelopes result{core::Array(signal.size()), core::Array(signal.size())};
    Workspace w;
    if (!execution::extrema_envelopes(signal, {result.upper.data(), signal.size()},
                                     {result.lower.data(), signal.size()}, options, w)) return std::nullopt;
    return result;
}
std::optional<core::Array> combined_envelope(std::span<const double> signal, const Options& options) {
    validate(signal, options);
    if (options.padding != Padding::numpypad) throw std::invalid_argument("combined 包络需要 numpypad");
    core::Array result(signal.size()); Workspace w;
    if (!execution::combined_envelope(signal, {result.data(), signal.size()}, options, w)) return std::nullopt;
    return result;
}
std::optional<core::Array> upper_envelope(std::span<const double> signal, const Options& options) {
    validate(signal, options);
    core::Array result(signal.size()); Workspace workspace;
    if (!execution::upper_envelope(signal, {result.data(), signal.size()}, options, workspace))
        return std::nullopt;
    return result;
}
} // namespace cnn_compute::envelope
