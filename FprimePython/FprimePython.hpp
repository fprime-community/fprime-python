
#ifndef FPRIME_PYTHON_HPP_
#define FPRIME_PYTHON_HPP_
#include <pybind11/pybind11.h>
#include "Fw/Types/StringBase.hpp"
#include "Fw/Types/String.hpp"
#include "Fw/Cmd/CmdString.hpp"



// All strings in F Prime behave the same way: they inherit from StringBase, they store a fixed size buffer etc.
// Thus we can create a generic type caster for all derivatives of StringBase. Since the type_caster is already
// a template we cannot template it further, so we use a macro to generate specializations for each derived type.
//
// Usage: TYPE_CASTER_FW_STRING_BASE_CHILD(<string type>); 
#define TYPE_CASTER_FW_STRING_BASE_CHILD(ChildType)\
    template <>\
    struct type_caster<ChildType> {\
        static_assert(std::is_base_of<Fw::StringBase, ChildType>::value,\
            "TYPE_CASTER_FW_STRING_BASE_CHILD(T) requires T to derive from Fw::StringBase");\
        PYBIND11_TYPE_CASTER(ChildType, io_name("str", "str"));\
\
        static handle\
        cast(const ChildType &string, return_value_policy /*policy*/, handle /*parent*/) {\
            return pybind11::str(string.toChar()).release();\
        }\
\
        bool load(handle src, bool convert) {\
            if (pybind11::isinstance<pybind11::str>(src)) {\
                std::string s = src.cast<std::string>();\
                value = s.c_str();\
                return true;\
            }\
            return false;\
        }\
    }

namespace Fw {
    //! \brief Bind F Prime types to Python for non-model types
    //!
    //! Several F Prime types that exist outside the FPP model. These types need to be bound into Python manually. This
    //! function binds those types.
    //!
    //! \warning this function (currently) only operates on the fw_time module.
    //!
    //! \param fw_time_module The pybind11 module to bind the types into. 
    void bind_fprime_manual_types(pybind11::module_& fw_time_module);
}

namespace pybind11 {
namespace detail {

    TYPE_CASTER_FW_STRING_BASE_CHILD(Fw::String);
    TYPE_CASTER_FW_STRING_BASE_CHILD(Fw::CmdStringArg);
}
}

#endif // FPRIME_PYTHON_HPP_