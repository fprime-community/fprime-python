####
# Stand-in project for tests/test_cmake.py: it calls the functions of target/fprime_python.cmake the way F Prime
# does, with the F Prime and pybind11 functions those rely on replaced by the minimum needed to configure and
# build. The autocoder is not run.
#
# TEST_DEPLOYMENTS lists the deployments to register, in order: "Cpp" has no bound topology; any other does.
####
cmake_minimum_required(VERSION 3.16)
project(FprimePythonTargetTest C)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_LIST_DIR}/stubs" "${FPRIME_PYTHON_CMAKE_DIR}")
set(FPRIME_FRAMEWORK_PATH "${CMAKE_CURRENT_LIST_DIR}/stubs")
set(FPRIME_INSTALL_DEST "${CMAKE_BINARY_DIR}/install")
set(EMPTY_SOURCE "${CMAKE_CURRENT_LIST_DIR}/empty.c")

add_library(pybind11::embed INTERFACE IMPORTED)
add_library(Fw_Types INTERFACE)
add_library(FprimePython INTERFACE)

function(pybind11_add_module NAME)
    add_library("${NAME}" MODULE ${ARGN})
endfunction()

# Reports the "generated" sources a test assigned to the module, as the autocoder would
macro(run_ac_set MODULE)
    set(AUTOCODER_GENERATED_BUILD_SOURCES ${TEST_GENERATED_SOURCES_${MODULE}})
    set(AUTOCODER_DEPENDENCIES)
endmacro()

include(target/fprime_python)

# Replaces the function that runs fprime-python-ac
function(_fprime_python_generate_init_file MODULE FULL_DEPENDENCIES)
    set(FPRIME_PYTHON_DEPLOYMENT_MODULES "" PARENT_SCOPE)
    set(FPRIME_PYTHON_DEPLOYMENT_INIT_FILE "${EMPTY_SOURCE}" PARENT_SCOPE)
endfunction()

# A component module with a generated template and a hand-written Python implementation
set(TEMPLATE_FILE "${CMAKE_BINARY_DIR}/Component.template.py")
file(WRITE "${TEMPLATE_FILE}" "# template\n")
add_library(Component STATIC "${EMPTY_SOURCE}")
set(TEST_GENERATED_SOURCES_Component "${EMPTY_SOURCE}")
set_target_properties(Component PROPERTIES FPRIME_PYTHON_GENERATED_PY_FILES "${TEMPLATE_FILE}")
fprime_python_add_module_target(Component "fprime_python" "${CMAKE_CURRENT_LIST_DIR}/Component.py" "")

foreach(DEPLOYMENT IN LISTS TEST_DEPLOYMENTS)
    add_library("${DEPLOYMENT}_Top" STATIC "${EMPTY_SOURCE}")
    if (NOT DEPLOYMENT STREQUAL "Cpp")
        set_target_properties("${DEPLOYMENT}_Top" PROPERTIES
            FPRIME_PYTHON_BOUND_TOPOLOGY_FILES "${DEPLOYMENT}Binding.topology.json")
    endif()
    add_executable("${DEPLOYMENT}" "${CMAKE_CURRENT_LIST_DIR}/main.c")
    fprime_python_add_deployment_target("${DEPLOYMENT}" "fprime_python" "${CMAKE_CURRENT_LIST_DIR}/main.c"
        "${DEPLOYMENT}_Top" "Component;${DEPLOYMENT}_Top;${DEPLOYMENT}")

    get_target_property(LINKED "${DEPLOYMENT}" LINK_LIBRARIES)
    message(STATUS "RESULT ${DEPLOYMENT} links ${LINKED}")
endforeach()

if (TARGET fprime_py)
    get_target_property(OWNER fprime_py FPRIME_PYTHON_DEPLOYMENT)
    message(STATUS "RESULT fprime_py built for ${OWNER}")
else()
    message(STATUS "RESULT fprime_py not built")
endif()
