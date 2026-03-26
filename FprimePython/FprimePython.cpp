// Manual bindings for Fprime Python types
#include "FprimePython/FprimePython.hpp"
#include "Fw/Time/Time.hpp"
#include "Fw/Time/TimeInterval.hpp"

namespace Fw {
// Function to bind manual Fprime types
void bind_types(pybind11::module_& fw_module) {
    pybind11::class_<Fw::TimeInterval>(fw_module, "TimeInterval").def(pybind11::init<U32, U32>());
    pybind11::class_<Fw::Time>(fw_module, "Time")
        .def(pybind11::init<>())
        .def(pybind11::init<U32, U32>())
        .def(pybind11::init<TimeBase, FwTimeContextStoreType, U32, U32>());
}
}  // namespace Fw
