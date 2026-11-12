#include <core/build_info.hpp>

#include <Eigen/Core>

#include "build_config.hpp"

namespace cnn_compute::core {

BuildInfo build_info() {
    return {
        CNN_COMPUTE_COMPILER_ID,
        CNN_COMPUTE_COMPILER_VERSION,
        CNN_COMPUTE_TARGET_ARCH,
        CNN_COMPUTE_ARCH_POLICY,
        CNN_COMPUTE_COMPILE_OPTIONS,
        Eigen::SimdInstructionSetsInUse(),
        EIGEN_WORLD_VERSION,
        EIGEN_MAJOR_VERSION,
        EIGEN_MINOR_VERSION,
    };
}

}  // namespace cnn_compute::core
