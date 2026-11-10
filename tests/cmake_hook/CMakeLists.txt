####
# Stand-in project for tests/test_cmake.py: includes FprimePython.cmake the way a project does, with the one
# F Prime function it calls replaced by a report of its argument.
####
cmake_minimum_required(VERSION 3.16)
project(FprimePythonHookTest C)

list(APPEND CMAKE_MODULE_PATH "${FPRIME_PYTHON_CMAKE_DIR}")

function(register_fprime_target TARGET_FILE)
    message(STATUS "RESULT registered ${TARGET_FILE}")
endfunction()

include(FprimePython)
message(STATUS "RESULT position independent ${CMAKE_POSITION_INDEPENDENT_CODE}")
