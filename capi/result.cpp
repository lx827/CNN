#include "result.hpp"
#include <core/build_info.hpp>

void CNN_CALL cnn_result_free(cnn_result *result) {
    delete result;
}
size_t CNN_CALL cnn_result_count(const cnn_result *result) {
    return result->fields.size( );
}
cnn_field CNN_CALL cnn_result_field(const cnn_result *result, size_t index) {
    return result->fields[index];
}
int CNN_CALL cnn_result_find(const cnn_result *result, const char *name, cnn_field *output) {
    for (const auto &field : result->fields)
        if (std::strcmp(field.name, name) == 0) {
            *output = field;
            return 1;
        }
    return 0;
}
const char *CNN_CALL cnn_version(void) {
    return "0.1.0";
}
cnn_result *CNN_CALL cnn_build_info(cnn_error *error) {
    return cnn_capi::boundary(error, [] {
        const auto info = cnn_compute::core::build_info( );
        auto       r    = std::make_unique< cnn_result >( );
        r->text("compiler", std::string(info.compiler_id));
        r->text("compiler_version", std::string(info.compiler_version));
        r->text("target_arch", std::string(info.target_arch));
        r->text("arch_policy", std::string(info.arch_policy));
        r->text("compile_options", std::string(info.compile_options));
        r->text("simd", std::string(info.simd));
        r->integer("eigen_major", info.eigen_major);
        r->integer("eigen_minor", info.eigen_minor);
        r->integer("eigen_patch", info.eigen_patch);
        return r;
    });
}
