// Header containing key F Prime Python binding utilities and type casters
#ifndef FPRIME_PYTHON_HPP_
#define FPRIME_PYTHON_HPP_
#include <pybind11/pybind11.h>
#include "Fw/Cmd/CmdString.hpp"
#include "Fw/Types/String.hpp"
#include "Fw/Types/StringBase.hpp"

// All strings in F Prime behave the same way: they inherit from StringBase, they store a fixed size buffer etc.
// Thus we can create a generic type caster for all derivatives of StringBase. Since the type_caster is already
// a template we cannot template it further, so we use a macro to generate specializations for each derived type.
//
// Usage: TYPE_CASTER_FW_STRING_BASE_CHILD(<string type>);
#define TYPE_CASTER_FW_STRING_BASE_CHILD(ChildType)                                                      \
    template <>                                                                                          \
    struct type_caster<ChildType> {                                                                      \
        static_assert(std::is_base_of<Fw::StringBase, ChildType>::value,                                 \
                      "TYPE_CASTER_FW_STRING_BASE_CHILD(T) requires T to derive from Fw::StringBase");   \
        PYBIND11_TYPE_CASTER(ChildType, io_name("str", "str"));                                          \
                                                                                                         \
        static handle cast(const ChildType& string, return_value_policy /*policy*/, handle /*parent*/) { \
            return pybind11::str(string.toChar()).release();                                             \
        }                                                                                                \
                                                                                                         \
        bool load(handle src, bool convert) {                                                            \
            if (pybind11::isinstance<pybind11::str>(src)) {                                              \
                std::string s = src.cast<std::string>();                                                 \
                value = s.c_str();                                                                       \
                return true;                                                                             \
            }                                                                                            \
            return false;                                                                                \
        }                                                                                                \
    }

//! \brief bind the deployment bindings into Python
//!
//! This function initializes the Python bindings for the deployment. It must bind all functions needed to start F Prime
//! from within Python. This includes the topology setup/teardown functions typically called: `setupTopology` and
//! `teardownTopology`, the rate group start/stop functions typically called: `startRateGroups` and `stopRateGroups`,
//! and the TopologyState type passed into the topology setup function.
//!
//! \warning This must be defined by the project using fprime-python as it is the hook to define project types.
//!
//! Since all these functions and types are project-malleable, this function must be defined by the project.
void setup_user_deployment(pybind11::module_& m);

namespace Fw {
//! \brief Bind F Prime types to Python for non-model types
//!
//! Several F Prime types that exist outside the FPP model. These types need to be bound into Python manually. This
//! function binds those types.
//!
//! \warning this function (currently) only operates on the fw_time module.
//!
//! \param fw_module The pybind11 module to bind the types into.
void bind_types(pybind11::module_& fw_module);
}  // namespace Fw

namespace Os {
//! \brief Bind F Prime functions to Python for non-model OSAL 
//!
//! The OSAL layer needs users to call Os::init(). This function binds that function into Python.
//!
//!
//! \param os_module The pybind11 module to bind Os::init into.
void bind_osal(pybind11::module_& os_module);
} // namespace Os

namespace pybind11 {
namespace detail {

TYPE_CASTER_FW_STRING_BASE_CHILD(Fw::String);
TYPE_CASTER_FW_STRING_BASE_CHILD(Fw::CmdStringArg);

// This will bind Fw::StringBase itself into the python layer. Since StringBase cannot be instantiated directly,
// Fw::String is used as the concrete type for the value member, which provides a backing store for the Python string
// to be copied into and then passed out as a StringBase reference.
template <>
struct type_caster<Fw::StringBase> {
  protected:
    // Use concrete Fw::String as a segregate type for Fw::StringBase
    Fw::String value;

  public:
    static constexpr auto name = io_name("str", "str");
    template <typename T_,
              ::pybind11::detail::enable_if_t<std::is_same<Fw::StringBase, ::pybind11::detail::remove_cv_t<T_>>::value,
                                              int> = 0>
    static ::pybind11::handle cast(T_* src, ::pybind11::return_value_policy policy, ::pybind11::handle parent) {
        if (!src)
            return ::pybind11::none().release();
        if (policy == ::pybind11::return_value_policy::take_ownership) {
            auto h = cast(std::move(*src), policy, parent);
            delete src;
            return h;
        }
        return cast(*src, policy, parent);
    }
    operator Fw::StringBase*() { return &value; }
    operator Fw::StringBase&() { return value; }
    operator Fw::StringBase&&() && { return std::move(value); }
    template <typename T_>
    using cast_op_type = ::pybind11::detail::movable_cast_op_type<T_>;
    static handle cast(const Fw::StringBase& string, return_value_policy, handle) {
        return pybind11::str(string.toChar()).release();
    }
    bool load(handle src, bool convert) {
        if (pybind11::isinstance<pybind11::str>(src)) {
            std::string s = src.cast<std::string>();
            value = s.c_str();
            return true;
        }
        return false;
    }
};
}  // namespace detail
}  // namespace pybind11

#endif  // FPRIME_PYTHON_HPP_