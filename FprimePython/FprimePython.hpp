// Header containing key F Prime Python binding utilities and type casters
#ifndef FPRIME_PYTHON_HPP_
#define FPRIME_PYTHON_HPP_
#include <pybind11/pybind11.h>
#include <string>
#include "Fw/Types/String.hpp"
#include "Fw/Types/StringBase.hpp"
#include "Fw/Types/StringTemplate.hpp"

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

namespace FprimePython {
//! \brief Reject a Python string that an F Prime string of the given capacity cannot hold unchanged
//!
//! Fw::StringBase::operator=(const char*) copies with string_copy, which silently drops whatever does not fit and
//! stops at the first NUL. A truncated path or command argument would then be used for logic with no indication
//! to the caller, so such a string is refused with a Python ValueError instead.
//!
//! \param value The string received from Python
//! \param capacity The capacity of the destination F Prime string, terminator included
inline void check_string_fits(const std::string& value, Fw::StringBase::SizeType capacity) {
    if (value.find('\0') != std::string::npos) {
        throw pybind11::value_error("F Prime strings cannot contain NUL characters");
    }
    // The capacity includes the terminator, so a string of exactly the capacity does not fit
    if (value.length() >= capacity) {
        throw pybind11::value_error("string of length " + std::to_string(value.length()) +
                                    " exceeds the F Prime string maximum of " +
                                    std::to_string(capacity - 1) + " characters");
    }
}
}  // namespace FprimePython

namespace pybind11 {
namespace detail {

// Every F Prime string of a fixed capacity is a Fw::StringTemplate<size> instantiation -- Fw::String,
// Fw::CmdStringArg, Fw::ParamString, Fw::FileNameString and the rest are aliases of one -- so a single partial
// specialization casts them all. Fw::StringBase itself is not an instantiation and is specialized separately
// below.
//
// A Python str that does not fit the instantiation's capacity is rejected with ValueError, see check_string_fits.
template <Fw::StringBase::SizeType size>
struct type_caster<Fw::StringTemplate<size>> {
    PYBIND11_TYPE_CASTER(Fw::StringTemplate<size>, io_name("str", "str"));

    static handle cast(const Fw::StringTemplate<size>& string,
                       return_value_policy /*policy*/,
                       handle /*parent*/) {
        return pybind11::str(string.toChar()).release();
    }

    bool load(handle src, bool convert) {
        if (pybind11::isinstance<pybind11::str>(src)) {
            std::string s = src.cast<std::string>();
            FprimePython::check_string_fits(s, value.getCapacity());
            value = s.c_str();
            return true;
        }
        return false;
    }
};

// This will bind Fw::StringBase itself into the python layer. Since StringBase cannot be instantiated directly,
// Fw::String is used as the concrete type for the value member, which provides a backing store for the Python string
// to be copied into and then passed out as a StringBase reference.
//
// The check here is against the Fw::String backing store only; the argument is then handled as F Prime handles a
// C++ caller's: an event or telemetry string is serialized up to the size declared in the model, and a port
// argument is passed on as is. Struct, array and inline-array string members are checked against their own
// capacity by the generated setters.
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
            FprimePython::check_string_fits(s, value.getCapacity());
            value = s.c_str();
            return true;
        }
        return false;
    }
};
}  // namespace detail
}  // namespace pybind11

#endif  // FPRIME_PYTHON_HPP_