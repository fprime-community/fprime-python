#include <fprime-python/FprimePy/FprimePy.hpp>
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
};
