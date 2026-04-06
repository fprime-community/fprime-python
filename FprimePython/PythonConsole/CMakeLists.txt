# Setup the pybind11 library so that we may use it
register_fprime_library(
        FprimePython_PythonConsole_lib
    SOURCES
        "${CMAKE_CURRENT_LIST_DIR}/Console.cpp"
    HEADERS
        "${CMAKE_CURRENT_LIST_DIR}/Console.hpp"
    DEPENDS
        Fw_Types
        Fw_Time
)
register_fprime_implementation(
    FprimePython_PythonConsole
  SOURCES
    "${CMAKE_CURRENT_LIST_DIR}/DefaultConsole.cpp"
  IMPLEMENTS
    Os_Console
  DEPENDS
    FprimePython_PythonConsole_lib

)


