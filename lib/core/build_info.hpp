#pragma once

#include <string_view>

namespace cnn_compute::core {

// 返回信息结构的版本，与数值算法版本分开。
inline constexpr int build_info_schema = 1;

struct BuildInfo {
    std::string_view compiler_id;
    std::string_view compiler_version;
    std::string_view target_arch;
    std::string_view arch_policy;
    std::string_view compile_options;
    std::string_view simd;
    int eigen_major;
    int eigen_minor;
    int eigen_patch;
};

BuildInfo build_info();

}  // namespace cnn_compute::core
