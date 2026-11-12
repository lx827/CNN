#pragma once
#include "include/cnn_compute.h"
#include <core/array.hpp>
#include <wavelet/api.hpp>
#include <complex>
#include <cstring>
#include <deque>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

// 仅适配层可见；owner 保留原 C++ 返回对象，绝不借用工作区输出。
struct cnn_result {
    std::vector< std::shared_ptr< void > >    owners;
    std::deque< std::string >                 names, texts;
    std::deque< double >                      reals;
    std::deque< int32_t >                     integers;
    std::deque< size_t >                      sizes;
    std::vector< cnn_field >                  fields;
    const cnn_compute::wavelet::Coefficients *coefficients = nullptr;
    template < class T >
    T &keep(T value) {
        auto  owner     = std::make_shared< T >(std::move(value));
        auto &reference = *owner;
        owners.push_back(std::move(owner));
        return reference;
    }
    void field(std::string name, cnn_field_type type, const void *data, size_t rows, size_t columns = 1) {
        names.push_back(std::move(name));
        fields.push_back({ names.back( ).c_str( ), type, data, rows, columns });
    }
    template < class T >
    void array(std::string name, const T &x, size_t rows, size_t columns = 1) {
        field(std::move(name), CNN_F64, x.data( ), rows, columns);
    }
    template < class T >
    void array(std::string name, const T &x) {
        array(std::move(name), x, static_cast< size_t >(x.size( )));
    }
    void real(std::string name, double value) {
        reals.push_back(value);
        field(std::move(name), CNN_F64, &reals.back( ), 1);
    }
    void integer(std::string name, int value) {
        integers.push_back(value);
        field(std::move(name), CNN_I32, &integers.back( ), 1);
    }
    void size(std::string name, size_t value) {
        sizes.push_back(value);
        field(std::move(name), CNN_SIZE, &sizes.back( ), 1);
    }
    void text(std::string name, std::string value) {
        texts.push_back(std::move(value));
        field(std::move(name), CNN_TEXT, texts.back( ).c_str( ), texts.back( ).size( ), 1);
    }
    void complex(std::string name, std::span< const std::complex< double > > x, size_t rows, size_t columns = 1) {
        // std::complex<double> 的数组定向 double 访问由 C++ 标准保证。
        // C 调用方读取交错 double，不按自定义结构体别名访问对象。
        field(std::move(name), CNN_COMPLEX, reinterpret_cast< const double * >(x.data( )), rows, columns);
    }
};

namespace cnn_capi {
using Result = std::unique_ptr< cnn_result >;
inline std::span< const double > span(cnn_span x) {
    if (x.size && !x.data) throw std::invalid_argument("nonempty span requires data");
    return { x.data, x.size };
}
inline std::span< const size_t > span(cnn_indices x) {
    if (x.size && !x.data) throw std::invalid_argument("nonempty indices require data");
    return { x.data, x.size };
}
inline std::vector< std::complex< double > > unpack(cnn_complex_span x) {
    if (x.size && !x.data) throw std::invalid_argument("nonempty complex span requires data");
    std::vector< std::complex< double > > result;
    result.reserve(x.size);
    for (size_t i = 0; i < x.size; ++i) result.emplace_back(x.data[i].real, x.data[i].imag);
    return result;
}
inline cnn_compute::core::Array copy(cnn_span x) {
    auto view = span(x);
    return Eigen::Map< const cnn_compute::core::Array >(view.data( ), view.size( ));
}
template < class Enum, class C >
Enum enumeration(C value, int maximum) {
    if (static_cast< int >(value) < 0 || static_cast< int >(value) > maximum) throw std::invalid_argument("invalid enumeration");
    return static_cast< Enum >(value);
}
inline void error(cnn_error *output, cnn_error_code code, const char *message) noexcept {
    if (!output) return;
    output->code  = code;
    size_t length = std::strlen(message);
    if (length >= sizeof(output->message)) length = sizeof(output->message) - 1;
    std::memcpy(output->message, message, length);
    output->message[length] = '\0';
}
template < class Function >
auto boundary(cnn_error *output, Function &&function) noexcept -> decltype(function( ).release( )) {
    error(output, CNN_ERROR_NONE, "");
    try {
        return function( ).release( );
    } catch (const std::invalid_argument &ex) {
        error(output, CNN_ERROR_ARGUMENT, ex.what( ));
    } catch (const std::domain_error &ex) {
        error(output, CNN_ERROR_DOMAIN, ex.what( ));
    } catch (const std::out_of_range &ex) {
        error(output, CNN_ERROR_RANGE, ex.what( ));
    } catch (const std::bad_alloc &ex) {
        error(output, CNN_ERROR_MEMORY, ex.what( ));
    } catch (const std::exception &ex) {
        error(output, CNN_ERROR_COMPUTATION, ex.what( ));
    } catch (...) {
        error(output, CNN_ERROR_COMPUTATION, "unknown C++ exception");
    }
    return nullptr;
}
template < class T >
Result values(T value, const char *name = "values") {
    auto  result = std::make_unique< cnn_result >( );
    auto &data   = result->keep(std::move(value));
    result->array(name, data);
    return result;
}
inline Result complex_values(std::vector< std::complex< double > > value) {
    auto  result = std::make_unique< cnn_result >( );
    auto &owned  = result->keep(std::move(value));
    result->complex("values", owned, owned.size( ));
    return result;
}
inline Result scalar(double value, const char *name = "value") {
    auto result = std::make_unique< cnn_result >( );
    result->real(name, value);
    return result;
}
inline const char *text(const char *input, const char *fallback) {
    return input ? input : fallback;
}
}    // namespace cnn_capi
