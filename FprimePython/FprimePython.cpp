// Manual bindings for Fprime Python types
#include "FprimePython/FprimePython.hpp"
#include "Fw/Buffer/Buffer.hpp"
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

    pybind11::class_<Fw::Buffer>(fw_module, "Buffer")
        .def(pybind11::init([](pybind11::buffer buf) {
            pybind11::gil_scoped_acquire gil;

            pybind11::buffer_info info = buf.request();
            U8* data_allocation = new U8[info.size];
            std::memcpy(data_allocation, info.ptr, info.size);

            return Fw::Buffer(
                data_allocation,
                static_cast<FwSizeType>(info.size),
                0xFFFF9999 // Flag value to prevent bad deallocation
            );
        }))
        .def("getData", [](Fw::Buffer& self) {
            return pybind11::memoryview::from_memory(
                reinterpret_cast<void*>(self.getData()),
                static_cast<pybind11::ssize_t>(self.getSize())
            );
        })
        .def("getSize", &Fw::Buffer::getSize)
        .def("deallocate",[](Fw::Buffer& self) {
            if (self.getContext() == 0xFFFF9999) {
                delete[] self.getData();
                self = Fw::Buffer();  // Reset to default state
            }

        });
}
}  // namespace Fw
