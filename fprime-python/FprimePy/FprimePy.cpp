#include <fprime-python/FprimePy/FprimePy.hpp>
#include <iostream>

namespace FprimePy {
    FprimePython::FprimePython() : m_releaser(nullptr) {}

    void FprimePython::initialize() {
        py::initialize_interpreter();
        py::module_ module = py::module_::import("sys");
        py::print("[FprimePy] Python Interpreter Initialized");
        py::print("[FprimePy] PYTHONPATH set to:", module.attr("path"));
        // m_releaser = new py::gil_scoped_release();
    }

    void FprimePython::deinitalize() {
        // delete m_releaser;
    }

    FprimePython::~FprimePython() {

        py::finalize_interpreter();
    }
};
