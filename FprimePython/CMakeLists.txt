# Setup the pybind11 library so that we may use it
add_fprime_subdirectory("${CMAKE_CURRENT_LIST_DIR}/PythonConsole")
register_fprime_library(
        FprimePython
    SOURCES
        "${CMAKE_CURRENT_LIST_DIR}/FprimePython.cpp"
    HEADERS
        "${CMAKE_CURRENT_LIST_DIR}/FprimePython.hpp"
    DEPENDS
        Fw_Types
        Fw_Time
)


