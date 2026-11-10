####
# FprimePython.cmake:
#
# Sets a project up to build F´ Python bindings. Include it from the project's top-level CMakeLists.txt, after
# including FPrime.cmake and before calling `fprime_setup_included_code()`:
#
#     include("${CMAKE_CURRENT_LIST_DIR}/lib/fprime/cmake/FPrime.cmake")
#     include(FprimePython)
#     fprime_setup_included_code()
#
# It must run in the project's top-level directory scope and before any F´ module is added: the bindings of
# every module are linked into one Python extension, so every module must be compiled as position independent
# code and must be able to include pybind11.
####
include_guard()

# The F´ sub-builds only gather model information, and compile nothing that could need pybind11
if (DEFINED FPRIME_SUB_BUILD_TARGETS)
    return()
endif()
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(PYBIND11_FINDPYTHON ON)

# pybind11 is installed with the fprime-python package, so the interpreter knows where its CMake package is
execute_process(COMMAND python3 -m pybind11 --cmakedir
    OUTPUT_VARIABLE FPRIME_PYTHON_PYBIND11_CMAKEDIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE FPRIME_PYTHON_PYBIND11_RESULT
    ERROR_QUIET)
if (NOT FPRIME_PYTHON_PYBIND11_RESULT EQUAL 0)
    message(FATAL_ERROR "[fprime_python] 'python3 -m pybind11 --cmakedir' failed. Install fprime-python into the "
        "Python environment used to build, e.g. 'pip install ./lib/fprime-python'.")
endif()
find_package(pybind11 CONFIG REQUIRED PATHS "${FPRIME_PYTHON_PYBIND11_CMAKEDIR}")
link_libraries("pybind11::module" "pybind11::headers")
register_fprime_target(target/fprime_python)
