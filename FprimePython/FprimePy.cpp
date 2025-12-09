
#include "FprimePython/FprimePython.hpp"
#include "Fw/Time/TimeInterval.hpp"
#include "Fw/Time/Time.hpp"

namespace Fw {

    void bind_fprime_manual_types(pybind11::module_& fw_time_module); {
        pybind11::class_<Fw::TimeInterval>(fw_time_module, "TimeInterval")
            .def(pybind11::init<U32, U32>());
        pybind11::class_<Fw::Time>(fw_time_module, "Time")
            .def(pybind11::init<>())
            .def(pybind11::init<U32, U32>())
            .def(pybind11::init<TimeBase, FwTimeContextStoreType, U32, U32>());

    }
}
