#include "api.hpp"
extern "C" {
#include "vendor/pywt/wt.h"
#include "vendor/pywt/convolution.h"
}
#include <algorithm>
#include <charconv>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace cnn_compute::wavelet {
namespace {
    std::span< double > view(core::Array &a) {
        return { a.data( ), static_cast< std::size_t >(a.size( )) };
    }
    std::span< const double > view(const core::Array &a) {
        return { a.data( ), static_cast< std::size_t >(a.size( )) };
    }
    void valid_input(std::span< const double > input) {
        if (input.size( ) < 2) throw std::invalid_argument("小波输入至少为两个采样点");
        if (!Eigen::Map< const core::Array >(input.data( ), input.size( )).isFinite( ).all( ))
            throw std::invalid_argument("小波输入必须有限");
    }
    MODE extension(const std::string &mode) {
        if (mode == "zero" || mode == "zpd") return MODE_ZEROPAD;
        if (mode == "symmetric" || mode == "sym") return MODE_SYMMETRIC;
        if (mode == "constant" || mode == "cpd") return MODE_CONSTANT_EDGE;
        if (mode == "smooth" || mode == "sp1") return MODE_SMOOTH;
        if (mode == "periodic" || mode == "ppd") return MODE_PERIODIC;
        if (mode == "periodization" || mode == "per") return MODE_PERIODIZATION;
        if (mode == "reflect") return MODE_REFLECT;
        if (mode == "antisymmetric") return MODE_ANTISYMMETRIC;
        if (mode == "antireflect") return MODE_ANTIREFLECT;
        throw std::invalid_argument("未知小波边界延拓模式");
    }
    unsigned integer(const std::string &text) {
        unsigned value          = 0;
        const auto [end, error] = std::from_chars(text.data( ), text.data( ) + text.size( ), value);
        if (error != std::errc{} || end != text.data( ) + text.size( ))
            throw std::invalid_argument("未知离散小波名称");
        return value;
    }
    DiscreteWavelet *filter(const std::string &name) {
        WAVELET_NAME family;
        unsigned     order = 0;
        if (name == "haar")
            family = HAAR;
        else if (name == "dmey")
            family = DMEY;
        else if (name.starts_with("db")) {
            family = DB;
            order  = integer(name.substr(2));
        } else if (name.starts_with("sym")) {
            family = SYM;
            order  = integer(name.substr(3));
        } else if (name.starts_with("coif")) {
            family = COIF;
            order  = integer(name.substr(4));
        } else if (name.starts_with("bior") || name.starts_with("rbio")) {
            family         = name.starts_with("bior") ? BIOR : RBIO;
            const auto dot = name.find('.', 4);
            if (dot == std::string::npos) throw std::invalid_argument("双正交小波名称必须包含阶数");
            const auto first  = integer(name.substr(4, dot - 4));
            const auto second = integer(name.substr(dot + 1));
            if (first > 9 || second > 9) throw std::invalid_argument("不支持的双正交小波阶数");
            order = first * 10 + second;
        } else
            throw std::invalid_argument("不支持的离散小波族");
        auto *result = discrete_wavelet(family, order);
        if (!result) throw std::invalid_argument("不支持的离散小波阶数");
        return result;
    }
    std::vector< std::size_t > lengths(const Plan &plan, std::size_t samples, int level) {
        if (samples < 2 || level < 1 || level > plan.max_level(samples))
            throw std::invalid_argument("小波层数超过当前记录与滤波器允许的范围");
        std::vector< std::size_t > result(static_cast< std::size_t >(level) + 1);
        result[0] = samples;
        for (int j = 1; j <= level; ++j) result[j] = plan.coefficient_size(result[j - 1]);
        return result;
    }
    std::size_t node_index(int level, std::size_t index) {
        return (std::size_t{ 1 } << level) - 2 + index;
    }
    void validate_coefficients(const Coefficients &c, const Plan &plan) {
        if (c.lengths.empty( )) throw std::invalid_argument("小波系数缺少长度信息");
        const auto expected = lengths(plan, c.lengths[0], c.level);
        if (c.lengths != expected || c.bands.size( ) != (c.packet ? (std::size_t{ 1 } << c.level) : c.level + 1))
            throw std::invalid_argument("小波系数形状与分解层数不匹配");
        for (std::size_t k = 0; k < c.bands.size( ); ++k) {
            const auto size = c.packet || k == 0 ? expected.back( ) : expected[c.level - k + 1];
            if (static_cast< std::size_t >(c.bands[k].size( )) != size)
                throw std::invalid_argument("小波系数长度不匹配");
        }
    }
    // IDWT 在奇数原长时多返回一点；只裁尾，不补零，不改变时间轴。
    void synthesize_crop(const Plan &plan, std::span< const double > a, std::span< const double > d,
                         std::span< double > target, Workspace &ws) {
        const auto full = plan.reconstruction_size(a.empty( ) ? d.size( ) : a.size( ));
        if (full == target.size( ))
            plan.synthesize(a, d, target, ws);
        else {
            auto temporary = view(ws.first).first(full);
            plan.synthesize(a, d, temporary, ws);
            std::copy_n(temporary.begin( ), target.size( ), target.begin( ));
        }
    }
    double median(std::span< double > values) {
        const auto middle = values.size( ) / 2;
        std::nth_element(values.begin( ), values.begin( ) + middle, values.end( ));
        const double upper = values[middle];
        return values.size( ) % 2 ? upper : (upper + *std::max_element(values.begin( ), values.begin( ) + middle)) / 2.0;
    }
}    // namespace

struct Plan::Impl {
    std::unique_ptr< DiscreteWavelet, decltype(&free_discrete_wavelet) > wavelet;
    MODE                                                                 mode;
    // 滤波器奇偶相位（fe[m] = filter[2m]、fo[m] = filter[2m+1]），构造期拆分一次。
    std::vector< double > dec_lo_even, dec_lo_odd, dec_hi_even, dec_hi_odd;
    std::vector< double > rec_lo_even, rec_lo_odd, rec_hi_even, rec_hi_odd;
    static void           split(const double *source, std::size_t length,
                                std::vector< double > &even, std::vector< double > &odd) {
        even.resize(length / 2);
        odd.resize(length / 2);
        for (std::size_t m = 0; m < length / 2; ++m) {
            even[m] = source[2 * m];
            odd[m]  = source[2 * m + 1];
        }
    }
    Impl(const std::string &name, const std::string &extension_mode)
        : wavelet(filter(name), free_discrete_wavelet), mode(extension(extension_mode)) {
        split(wavelet->dec_lo_double, wavelet->dec_len, dec_lo_even, dec_lo_odd);
        split(wavelet->dec_hi_double, wavelet->dec_len, dec_hi_even, dec_hi_odd);
        split(wavelet->rec_lo_double, wavelet->rec_len, rec_lo_even, rec_lo_odd);
        split(wavelet->rec_hi_double, wavelet->rec_len, rec_hi_even, rec_hi_odd);
    }
};
Plan::Plan(const std::string &wavelet, const std::string &mode) : impl_(std::make_unique< Impl >(wavelet, mode)) {}
Plan::~Plan( )                                = default;
Plan::Plan(Plan &&) noexcept                  = default;
Plan       &Plan::operator=(Plan &&) noexcept = default;
std::size_t Plan::coefficient_size(std::size_t input) const {
    return dwt_buffer_length(input, impl_->wavelet->dec_len, impl_->mode);
}
std::size_t Plan::reconstruction_size(std::size_t coefficients) const {
    return idwt_buffer_length(coefficients, impl_->wavelet->rec_len, impl_->mode);
}
int Plan::max_level(std::size_t samples) const {
    return dwt_max_level(samples, impl_->wavelet->dec_len);
}
std::size_t Plan::filter_length( ) const {
    return impl_->wavelet->dec_len;
}
void Plan::analyze(std::span< const double > input, std::span< double > a, std::span< double > d,
                   Workspace &ws) const {
    if (impl_->mode == MODE_PERIODIZATION) {
        // 周期化的 padding 位置与自回绕次序 vendor 专有，整段保留其标量内核。
        if (double_dec_a(input.data( ), input.size( ), impl_->wavelet.get( ), a.data( ), a.size( ), impl_->mode)
            || double_dec_d(input.data( ), input.size( ), impl_->wavelet.get( ), d.data( ), d.size( ), impl_->mode))
            throw std::runtime_error("小波分解失败");
        return;
    }
    const auto n     = input.size( );
    const auto flen  = impl_->wavelet->dec_len;
    const auto half  = flen / 2;
    const auto o_lo  = half;     // 左边界输出数 = F/2（i = 1,3,..,F-1）
    const auto o_hi  = n / 2;    // 中心段右端（i < N 的奇数计数）
    const auto count = o_hi - o_lo;
    // 偶/奇相位拆分，两个滤波器共用一趟。
    for (std::size_t t = 0; t < n / 2; ++t) {
        ws.even[t] = input[2 * t];
        ws.odd[t]  = input[2 * t + 1];
    }
    if (n % 2) ws.even[n / 2] = input[n - 1];
    // 边界窗口 = 输入前缀 F + 与 N 同奇偶的输入后缀：vendor 对窗口两端的延拓
    // 算术与对全长输入一致（N>=F 时 k<N 界不触发），一次调用同时覆盖左右边界。
    const auto window  = 2 * flen + (n & 1);
    const auto trailer = window - flen;
    std::copy_n(input.data( ), flen, ws.fake.data( ));
    std::copy_n(input.data( ) + (n - trailer), trailer, ws.fake.data( ) + flen);
    auto convolve = [&](const double *filter, const double *fe, const double *fo, std::span< double > out) {
        double_downsampling_convolution(ws.fake.data( ), window, filter, flen, ws.edge.data( ), 2,
                                        impl_->mode);
        std::copy_n(ws.edge.data( ), o_lo, out.data( ));
        std::copy_n(ws.edge.data( ) + flen, out.size( ) - o_hi, out.data( ) + o_hi);
        if (count == 0) return;
        // 中心段多相卷积：output[o] = Σ fe[m]·odd[o-m] + Σ fo[m]·even[o-m]。
        // 逐包输出的累加器驻留寄存器（Eigen packet 中间层，宽度随目标 ISA），
        // 逐 tap 乘加免掉目的地重放；每个元素的加法序列严格保持 j = 0,1,2,…
        // 升序，与 vendor 中心循环逐位一致；尾部逐元素同序标量。
        using Packet         = Eigen::internal::packet_traits< double >::type;
        constexpr auto lanes = Eigen::internal::unpacket_traits< Packet >::size;
        const auto     full  = count / lanes * lanes;
        for (std::size_t offset = 0; offset < full; offset += lanes) {
            const double *odd_p  = ws.odd.data( ) + o_lo + offset;
            const double *even_p = ws.even.data( ) + o_lo + offset;
            Packet        acc    = Eigen::internal::pset1< Packet >(0.0);
            for (std::size_t m = 0; m < half; ++m) {
                acc = Eigen::internal::padd(
                    acc, Eigen::internal::pmul(Eigen::internal::pset1< Packet >(fe[m]),
                                               Eigen::internal::ploadu< Packet >(odd_p - m)));
                acc = Eigen::internal::padd(
                    acc, Eigen::internal::pmul(Eigen::internal::pset1< Packet >(fo[m]),
                                               Eigen::internal::ploadu< Packet >(even_p - m)));
            }
            Eigen::internal::pstoreu(out.data( ) + o_lo + offset, acc);
        }
        for (std::size_t o = o_lo + full; o < o_hi; ++o) {
            double sum = 0;
            for (std::size_t m = 0; m < half; ++m) {
                sum += fe[m] * ws.odd[o - m];
                sum += fo[m] * ws.even[o - m];
            }
            out[o] = sum;
        }
    };
    convolve(impl_->wavelet->dec_lo_double, impl_->dec_lo_even.data( ), impl_->dec_lo_odd.data( ), a);
    convolve(impl_->wavelet->dec_hi_double, impl_->dec_hi_even.data( ), impl_->dec_hi_odd.data( ), d);
}
void Plan::synthesize(std::span< const double > a, std::span< const double > d, std::span< double > output,
                      Workspace &ws) const {
    // vendor 上采样卷积向输出累加，先整体清零一次（契约要求）。
    std::fill(output.begin( ), output.end( ), 0.0);
    if (impl_->mode == MODE_PERIODIZATION) {
        if (double_idwt(a.empty( ) ? nullptr : a.data( ), a.size( ), d.empty( ) ? nullptr : d.data( ), d.size( ),
                        output.data( ), output.size( ), impl_->wavelet.get( ), impl_->mode))
            throw std::runtime_error("小波重构失败");
        return;
    }
    // 非周期化的上采样有效段卷积覆盖全部输出，无边界特判。sum_even/sum_odd
    // 链在寄存器包内按 m 升序聚合完毕后，一次累进输出——直接 tap-major 累进
    // 输出会改变 (0+SE_lo)+SE_hi 的加法分组。
    const auto coeffs   = a.empty( ) ? d.size( ) : a.size( );
    const auto half     = impl_->wavelet->rec_len / 2;
    const auto pairs    = coeffs - half + 1;
    auto       upsample = [&](const double *fe, const double *fo, std::span< const double > source) {
        using Packet         = Eigen::internal::packet_traits< double >::type;
        constexpr auto lanes = Eigen::internal::unpacket_traits< Packet >::size;
        const auto     full  = pairs / lanes * lanes;
        double         block[lanes];
        for (std::size_t offset = 0; offset < full; offset += lanes) {
            const double *taps_p   = source.data( ) + half - 1 + offset;
            Packet        sum_even = Eigen::internal::pset1< Packet >(0.0);
            Packet        sum_odd  = Eigen::internal::pset1< Packet >(0.0);
            for (std::size_t m = 0; m < half; ++m) {
                const Packet taps = Eigen::internal::ploadu< Packet >(taps_p - m);
                sum_even          = Eigen::internal::padd(
                    sum_even, Eigen::internal::pmul(Eigen::internal::pset1< Packet >(fe[m]), taps));
                sum_odd = Eigen::internal::padd(
                    sum_odd, Eigen::internal::pmul(Eigen::internal::pset1< Packet >(fo[m]), taps));
            }
            Eigen::internal::pstoreu(block, sum_even);
            for (std::size_t k = 0; k < lanes; ++k) output[2 * (offset + k)] += block[k];
            Eigen::internal::pstoreu(block, sum_odd);
            for (std::size_t k = 0; k < lanes; ++k) output[2 * (offset + k) + 1] += block[k];
        }
        for (std::size_t t = full; t < pairs; ++t) {
            double sum_even = 0, sum_odd = 0;
            for (std::size_t m = 0; m < half; ++m) {
                const double taps = source[half - 1 - m + t];
                sum_even += fe[m] * taps;
                sum_odd += fo[m] * taps;
            }
            output[2 * t] += sum_even;
            output[2 * t + 1] += sum_odd;
        }
    };
    if (!a.empty( )) upsample(impl_->rec_lo_even.data( ), impl_->rec_lo_odd.data( ), a);
    if (!d.empty( )) upsample(impl_->rec_hi_even.data( ), impl_->rec_hi_odd.data( ), d);
}
void Workspace::prepare(const Plan &plan, std::size_t samples, int level, bool packet) {
    const auto sizes = lengths(plan, samples, level);
    nodes.resize(packet ? (std::size_t{ 1 } << level) - 2 : level - 1);
    if (packet) {
        for (int j = 1; j < level; ++j)
            for (std::size_t k = 0; k < (std::size_t{ 1 } << j); ++k)
                nodes[node_index(j, k)].resize(sizes[j]);
    } else
        for (int j = 1; j < level; ++j) nodes[j - 1].resize(sizes[j]);
    first.resize(samples + 1);
    second.resize(samples + 1);
    median.resize(sizes[1]);
    // 多相支撑缓冲：相位拆分按最长一级输入（原始长度）取半；边界窗口与边界
    // 卷积输出只依赖滤波器长度；IDWT 的 sum_even/sum_odd 聚合在寄存器完成。
    const auto flen = plan.filter_length( );
    even.resize(samples / 2 + 1);
    odd.resize(samples / 2 + 1);
    fake.resize(2 * flen + 1);
    edge.resize(3 * flen / 2 + 1);
}
void prepare_coefficients(Coefficients &output, const Plan &plan, std::size_t samples, int level, bool packet) {
    output.lengths = lengths(plan, samples, level);
    output.level   = level;
    output.packet  = packet;
    output.bands.resize(packet ? (std::size_t{ 1 } << level) : level + 1);
    for (std::size_t k = 0; k < output.bands.size( ); ++k)
        output.bands[k].resize(packet || k == 0 ? output.lengths.back( ) : output.lengths[level - k + 1]);
}
void decompose_into(std::span< const double > input, const Plan &plan, Coefficients &output, Workspace &ws) {
    if (output.packet) {
        for (int j = 1; j <= output.level; ++j) {
            for (std::size_t k = 0; k < (std::size_t{ 1 } << (j - 1)); ++k) {
                const auto source = j == 1 ? input : view(ws.nodes[node_index(j - 1, k)]);
                auto      &a      = j == output.level ? output.bands[k * 2] : ws.nodes[node_index(j, k * 2)];
                auto      &d      = j == output.level ? output.bands[k * 2 + 1] : ws.nodes[node_index(j, k * 2 + 1)];
                plan.analyze(source, view(a), view(d), ws);
            }
        }
    } else {
        auto source = input;
        for (int j = 1; j <= output.level; ++j) {
            auto &a = j == output.level ? output.bands[0] : ws.nodes[j - 1];
            auto &d = output.bands[output.level - j + 1];
            plan.analyze(source, view(a), view(d), ws);
            source = view(a);
        }
    }
}
void reconstruct_into(const Coefficients &c, const Plan &plan, std::span< double > output, Workspace &ws) {
    if (c.packet) {
        for (int j = c.level; j >= 1; --j) {
            for (std::size_t k = 0; k < (std::size_t{ 1 } << (j - 1)); ++k) {
                const auto &a      = j == c.level ? c.bands[k * 2] : ws.nodes[node_index(j, k * 2)];
                const auto &d      = j == c.level ? c.bands[k * 2 + 1] : ws.nodes[node_index(j, k * 2 + 1)];
                auto        target = j == 1 ? output : view(ws.nodes[node_index(j - 1, k)]);
                synthesize_crop(plan, view(a), view(d), target, ws);
            }
        }
    } else {
        auto a = view(c.bands[0]);
        for (int j = c.level; j >= 1; --j) {
            auto target = j == 1 ? output : view(ws.nodes[j - 2]);
            synthesize_crop(plan, a, view(c.bands[c.level - j + 1]), target, ws);
            a = target;
        }
    }
}
Coefficients decompose(std::span< const double > input, const Plan &plan, int level, bool packet) {
    valid_input(input);
    Coefficients result;
    prepare_coefficients(result, plan, input.size( ), level, packet);
    Workspace ws;
    ws.prepare(plan, input.size( ), level, packet);
    decompose_into(input, plan, result, ws);
    return result;
}
core::Array reconstruct(const Coefficients &c, const Plan &plan) {
    validate_coefficients(c, plan);
    core::Array result(c.lengths[0]);
    Workspace   ws;
    ws.prepare(plan, c.lengths[0], c.level, c.packet);
    reconstruct_into(c, plan, view(result), ws);
    return result;
}
void reconstruct_component_into(const Coefficients &c, std::size_t k, const Plan &plan,
                                std::span< double > output, Workspace &ws) {
    auto      source = view(c.bands[k]);
    const int start  = c.packet || k == 0 ? c.level : c.level - static_cast< int >(k) + 1;
    bool      first  = true;
    for (int j = start; j >= 1; --j) {
        const bool detail = c.packet ? ((k >> (c.level - j)) & 1) : (k > 0 && first);
        auto      &buffer = first || source.data( ) != ws.first.data( ) ? ws.first : ws.second;
        const auto full   = plan.reconstruction_size(source.size( ));
        auto       target = j == 1 && full == c.lengths[0] ? output : view(buffer).first(full);
        plan.synthesize(detail ? std::span< const double >{} : source,
                        detail ? source : std::span< const double >{}, target, ws);
        source = target.first(c.lengths[j - 1]);
        first  = false;
    }
    if (source.data( ) != output.data( )) std::copy(source.begin( ), source.end( ), output.data( ));
}
std::vector< core::Array > reconstruct_components(const Coefficients &c, const Plan &plan) {
    validate_coefficients(c, plan);
    Workspace ws;
    ws.prepare(plan, c.lengths[0], c.level, c.packet);
    std::vector< core::Array > result(c.bands.size( ));
    for (std::size_t k = 0; k < c.bands.size( ); ++k) {
        result[k].resize(c.lengths[0]);
        reconstruct_component_into(c, k, plan, view(result[k]), ws);
    }
    return result;
}
core::Array reconstruct_selected(const Coefficients &c, const Plan &plan, std::span< const std::size_t > selected) {
    validate_coefficients(c, plan);
    for (std::size_t i = 0; i < selected.size( ); ++i) {
        if (selected[i] >= c.bands.size( )) throw std::invalid_argument("选择的小波分量不存在");
        if (std::find(selected.begin( ), selected.begin( ) + i, selected[i]) != selected.begin( ) + i)
            throw std::invalid_argument("选择的小波分量不能重复");
    }
    Workspace ws;
    ws.prepare(plan, c.lengths[0], c.level, c.packet);
    core::Array result = core::Array::Zero(c.lengths[0]), component(c.lengths[0]);
    for (auto k : selected) {
        reconstruct_component_into(c, k, plan, view(component), ws);
        result += component;
    }
    return result;
}
core::Array denoise(std::span< const double > input, const Plan &plan, int level,
                    const std::string &threshold_mode, double threshold_scale) {
    valid_input(input);
    if (threshold_mode != "soft" && threshold_mode != "hard" && threshold_mode != "improved")
        throw std::invalid_argument("未知小波阈值模式");
    if (!std::isfinite(threshold_scale) || threshold_scale < 0) throw std::invalid_argument("阈值倍率必须为有限非负数");
    if (level == 0) level = plan.max_level(input.size( ));
    Coefficients coefficients;
    prepare_coefficients(coefficients, plan, input.size( ), level, false);
    Workspace ws;
    ws.prepare(plan, input.size( ), level, false);
    double      amplitude = Eigen::Map< const core::Array >(input.data( ), input.size( )).cwiseAbs( ).maxCoeff( );
    core::Array normalized(input.size( ));
    core::Array result(input.size( ));
    if (amplitude == 0) {
        result.setZero( );
        return result;
    }
    normalized = Eigen::Map< const core::Array >(input.data( ), input.size( )) / amplitude;
    decompose_into(view(normalized), plan, coefficients, ws);
    const auto &finest = coefficients.bands.back( );
    std::copy_n(finest.data( ), finest.size( ), ws.median.data( ));
    const double center    = median(view(ws.median).first(finest.size( )));
    ws.median              = (finest - center).abs( );
    const double sigma     = median(view(ws.median)) / 0.6744897501960817;
    const double threshold = threshold_scale * sigma * std::sqrt(2 * std::log(static_cast< double >(input.size( ))));
    // 模式循环外解析一次；hard/soft 用向量化表达式，improved 保留逐元素 exp。
    // sign(band)*max(|band|-t,0) 与 copysign(max(|band|-shrink,0),band) 在有限
    // 输入下逐位等价（x=0 时两侧同为该符号的零）。
    enum class Shrink { hard,
                        soft,
                        improved };
    const Shrink shrink = threshold_mode == "hard"   ? Shrink::hard
                          : threshold_mode == "soft" ? Shrink::soft
                                                     : Shrink::improved;
    for (std::size_t k = 1; k < coefficients.bands.size( ); ++k) {
        auto                     &band = coefficients.bands[k];
        Eigen::Map< core::Array > values(band.data( ), band.size( ));
        switch (shrink) {
            case Shrink::hard:
                values = (values.cwiseAbs( ) > threshold).select(values, 0.0);
                break;
            case Shrink::soft:
                values = values.sign( ) * (values.cwiseAbs( ) - threshold).max(0.0);
                break;
            case Shrink::improved:
                for (Eigen::Index i = 0; i < values.size( ); ++i) {
                    const double absolute = std::abs(values[i]);
                    const double factor   = threshold / (1 + std::exp(2 * (absolute - threshold)));
                    values[i]             = std::copysign(std::max(absolute - factor, 0.0), values[i]);
                }
                break;
        }
    }
    reconstruct_into(coefficients, plan, view(result), ws);
    result *= amplitude;
    return result;
}
}    // namespace cnn_compute::wavelet
