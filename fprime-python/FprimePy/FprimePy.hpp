//
// Created by mstarch on 9/14/21.
//
#include <pybind11/pybind11.h>
namespace Fw {
    void bind_fprime_types(pybind11::module_& fw_module);
}

/*
#ifndef PYAPP_PYINIT_HPP
#define PYAPP_PYINIT_HPP

#include "pybind11/pybind11.h"
#include "pybind11/embed.h"
namespace py = pybind11;


namespace FprimePy {

class FprimePython {
  public:
    FprimePython();
    void initialize();
    void deinitalize();
    ~FprimePython();

  private:
    py::gil_scoped_release* m_releaser;
};
}
#endif  // PYAPP_PYINIT_HPP
*/