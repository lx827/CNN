#include "api.hpp"
extern "C" {
#include "vendor/pywt/wt.h"
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
        for (double x : input)
            if (!std::isfinite(x)) throw std::invalid_argument("小波输入必须有限");
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
                         std::span< double > target, core::Array &scratch) {
        const auto full = plan.reconstruction_size(a.empty( ) ? d.size( ) : a.size( ));
        if (full == target.size( ))
            plan.synthesize(a, d, target);
        else {
            auto temporary = view(scratch).first(full);
            plan.synthesize(a, d, temporary);
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
    Impl(const std::string &name, const std::string &extension_mode)
        : wavelet(filter(name), free_discrete_wavelet), mode(extension(extension_mode)) {}
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
void Plan::analyze(std::span< const double > input, std::span< double > a, std::span< double > d) const {
    if (double_dec_a(input.data( ), input.size( ), impl_->wavelet.get( ), a.data( ), a.size( ), impl_->mode)
        || double_dec_d(input.data( ), input.size( ), impl_->wavelet.get( ), d.data( ), d.size( ), impl_->mode))
        throw std::runtime_error("小波分解失败");
}
void Plan::synthesize(std::span< const double > a, std::span< const double > d, std::span< double > output) const {
    std::fill(output.begin( ), output.end( ), 0.0);
    if (double_idwt(a.empty( ) ? nullptr : a.data( ), a.size( ), d.empty( ) ? nullptr : d.data( ), d.size( ),
                    output.data( ), output.size( ), impl_->wavelet.get( ), impl_->mode))
        throw std::runtime_error("小波重构失败");
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
                plan.analyze(source, view(a), view(d));
            }
        }
    } else {
        auto source = input;
        for (int j = 1; j <= output.level; ++j) {
            auto &a = j == output.level ? output.bands[0] : ws.nodes[j - 1];
            auto &d = output.bands[output.level - j + 1];
            plan.analyze(source, view(a), view(d));
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
                synthesize_crop(plan, view(a), view(d), target, ws.first);
            }
        }
    } else {
        auto a = view(c.bands[0]);
        for (int j = c.level; j >= 1; --j) {
            auto target = j == 1 ? output : view(ws.nodes[j - 2]);
            synthesize_crop(plan, a, view(c.bands[c.level - j + 1]), target, ws.first);
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
                        detail ? source : std::span< const double >{}, target);
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
    double amplitude = 0;
    for (double x : input) amplitude = std::max(amplitude, std::abs(x));
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
    for (std::size_t k = 1; k < coefficients.bands.size( ); ++k) {
        auto &band = coefficients.bands[k];
        for (Eigen::Index i = 0; i < band.size( ); ++i) {
            const double absolute = std::abs(band[i]);
            if (threshold_mode == "hard") {
                if (absolute <= threshold) band[i] = 0;
            } else {
                const double shrink = threshold_mode == "soft" ? threshold : threshold / (1 + std::exp(2 * (absolute - threshold)));
                band[i]             = std::copysign(std::max(absolute - shrink, 0.0), band[i]);
            }
        }
    }
    reconstruct_into(coefficients, plan, view(result), ws);
    result *= amplitude;
    return result;
}
}    // namespace cnn_compute::wavelet
