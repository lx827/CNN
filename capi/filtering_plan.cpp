#include "result.hpp"
#include <filtering/api.hpp>
#include <algorithm>

using namespace cnn_capi;
namespace cc = cnn_compute;
struct cnn_sos_plan {
    std::vector< cc::filtering::Sos > sections;
    cc::filtering::Workspace          workspace;
    int                               padlen;
    cnn_sos_plan(cnn_span coefficients, int padding) : padlen(padding) {
        auto input = span(coefficients);
        if (input.empty( ) || input.size( ) % 6) throw std::invalid_argument("SOS requires nonempty six-coefficient sections");
        sections.resize(input.size( ) / 6);
        for (size_t i = 0; i < sections.size( ); ++i) std::copy_n(input.data( ) + i * 6, 6, sections[i].begin( ));
    }
};
cnn_sos_plan *CNN_CALL cnn_sos_plan_create(cnn_span coefficients, int padlen, cnn_error *e) {
    return boundary(e, [&] { return std::make_unique< cnn_sos_plan >(coefficients, padlen); });
}
void CNN_CALL cnn_sos_plan_free(cnn_sos_plan *plan) {
    delete plan;
}
cnn_result *CNN_CALL cnn_sos_plan_apply(cnn_sos_plan *plan, cnn_span x, cnn_error *e) {
    return boundary(e, [&] {if(!plan)throw std::invalid_argument("SOS plan is required");
        auto input=span(x);std::vector<double> output(input.size());
        cc::filtering::execution::sosfiltfilt(input,plan->sections,output,plan->workspace,plan->padlen);return values(std::move(output)); });
}
