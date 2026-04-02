// Manual bindings for Fprime Python types
#include "FprimePython/FprimePython.hpp"
#include "Fw/Buffer/Buffer.hpp"
#include "Fw/Comp/QueuedComponentBase.hpp"
#include "Fw/Time/Time.hpp"
#include "Fw/Time/TimeInterval.hpp"
#include <atomic>
#include <tuple>
#include <unordered_map>

// Counter to speed look-up of possible buffers
static std::atomic<U32> s_object_counter{0};
// Map storing the pyobject (keeping reference counting), the pointer to the original buffer, and original size
static std::unordered_map<U64, std::tuple<pybind11::object, U8*, FwSizeType>> s_object_store;


namespace Fw {
// Function to bind manual Fprime types
void bind_types(pybind11::module_& fw_module) {
    pybind11::class_<Fw::TimeInterval>(fw_module, "TimeInterval").def(pybind11::init<U32, U32>())
        .def("getInterval", [](Fw::TimeInterval& self) {
            return static_cast<F64>(self.getSeconds()) + static_cast<F64>(self.getUSeconds()) / 1000000.0;
        });
    pybind11::class_<Fw::Time>(fw_module, "Time")
        .def(pybind11::init<>())
        .def(pybind11::init<U32, U32>())
        .def(pybind11::init<TimeBase, FwTimeContextStoreType, U32, U32>())
        .def("getTime", [](Fw::Time& self) {
            return static_cast<F64>(self.getSeconds()) + static_cast<F64>(self.getUSeconds()) / 1000000.0;
        });

    pybind11::enum_<Fw::QueuedComponentBase::MsgDispatchStatus>(fw_module, "MsgDispatchStatus")
        .value("MSG_DISPATCH_OK", Fw::QueuedComponentBase::MsgDispatchStatus::MSG_DISPATCH_OK)
        .value("MSG_DISPATCH_EMPTY", Fw::QueuedComponentBase::MsgDispatchStatus::MSG_DISPATCH_EMPTY)
        .value("MSG_DISPATCH_ERROR", Fw::QueuedComponentBase::MsgDispatchStatus::MSG_DISPATCH_ERROR)
        .value("MSG_DISPATCH_EXIT", Fw::QueuedComponentBase::MsgDispatchStatus::MSG_DISPATCH_EXIT);

    pybind11::class_<Fw::Buffer>(fw_module, "Buffer")
        .def(pybind11::init([](pybind11::buffer buf) {
            pybind11::gil_scoped_acquire gil;
            pybind11::buffer_info info = buf.request();

            // Stick the original buffer in the reference store to ensure that it does not get garbage-collected while
            // the Fw::Buffer is still alive.
            U32 object_id = s_object_counter.fetch_add(1);
            s_object_store.emplace(object_id, std::make_tuple(buf, reinterpret_cast<U8*>(info.ptr), static_cast<FwSizeType>(info.size)));
            // Use the context to store 
            return Fw::Buffer(
                reinterpret_cast<U8*>(info.ptr),
                static_cast<FwSizeType>(info.size),
                object_id // Flag value to prevent bad deallocation
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
            // Only handle the case when the context is stored in our reference storage as this implies the buffer was
            // created from Python and thus should be scrubbed from our reference store.
            if (s_object_store.find(self.getContext()) != s_object_store.end()) {
                auto& tuple = s_object_store[self.getContext()];
                // Double check that the buffer's pointer is within the stored object's original window. This ensures
                // that we have not accidentally found a context collision thus preventing early release of pyobjects.
                U8* ptr = std::get<1>(tuple);
                FwSizeType size = std::get<2>(tuple);
                // Erase the global reference, decreasing the reference count and freeing-up python to collect it!
                if ((ptr <= self.getData()) && (self.getData() < (ptr + size))) {
                    s_object_store.erase(self.getContext());
                }
            }
        });
}
}  // namespace Fw
