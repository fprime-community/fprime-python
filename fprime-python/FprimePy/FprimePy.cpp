
#include "fprime-python/FprimePy/FprimePy.hpp"
#include "Fw/Time/TimeInterval.hpp"
#include "Fw/Time/Time.hpp"
#include "fprime-python/fprime-python.hpp"

namespace Fw {

    void bind_fprime_types(pybind11::module_& fw_module) {
        pybind11::class_<Fw::TimeInterval>(fw_module, "TimeInterval")
            .def(pybind11::init<U32, U32>());
        pybind11::class_<Fw::Time>(fw_module, "Time")
            .def(pybind11::init<>())
            .def(pybind11::init<U32, U32>())
            .def(pybind11::init<TimeBase, FwTimeContextStoreType, U32, U32>());

    }
}
//    TYPE_CASTER_FW_STRING_BASE_CHILD(Fw::ExternalString);
/*#include <fprime-python/FprimePy/FprimePy.hpp>
#include <iostream>

namespace FprimePy {
    FprimePython::FprimePython() : m_releaser(nullptr) {}

    void FprimePython::initialize() {
        py::initialize_interpreter(); 
        {
            py::module_ module = py::module_::import("sys");
            py::print("[FprimePy] Python Interpreter Initialized");
            py::print("[FprimePy] PYTHONPATH set to:", module.attr("path"));
        }

        m_releaser = new py::gil_scoped_release();
        std::cout << "After GIL release" << std::endl;
    }

    void FprimePython::deinitalize() {
        std::cout << "Before Delete" << std::endl;
        delete m_releaser;
        std::cout << "After Delete" << std::endl;
    }

    FprimePython::~FprimePython() {
        py::gil_scoped_acquire acquire;
        py::finalize_interpreter();
    }
};*/
