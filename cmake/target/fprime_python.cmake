####
# target/fprime_python.cmake:
#
# This implements the fprime_python autocoding as a target in the F´ build system.
####
include_guard()
include(autocoder/autocoder) # Allows running autocoder sets

####
# Function `fprime_python_add_global_target`:
#
# Registers a global targets for fprime_python. This allows a user to build just the fprime_python modules and
# functions as a build all for the fprime_python targets.
####
function(fprime_python_add_global_target)
    #add_custom_target("fprime_python")
endfunction()

####
# Function `fprime_python_add_module_target`:
#
# Runs the fprime_python autocode on the specified module and attaches the outputs to a target for building the module
# specific fprime_python code.
#
# Args:
#  - MODULE: name of the module
####
function(fprime_python_add_module_target MODULE TARGET SOURCE_FILES DEPENDENCIES)
    run_ac_set("${MODULE}" "autocoder/fprime_python") # Run the fprime_python autocoder on this module
    if (AUTOCODER_GENERATED_BUILD_SOURCES)
        add_library("${MODULE}_fprime_python" STATIC ${AUTOCODER_GENERATED_BUILD_SOURCES})
        target_link_libraries("${MODULE}_fprime_python" PUBLIC ${AUTOCODER_DEPENDENCIES} ${MODULE} Fw_Types)

        # Copies any generated python template files back to the source directory for users to rename-and-edit. This
        # is designed to not require a separate "impl" step and ensures the latest templates are always up-to-date.
        set(PYTHON_TEMPLATE_SOURCES ${AUTOCODER_GENERATED_OTHER})
        list(FILTER PYTHON_TEMPLATE_SOURCES INCLUDE REGEX "^.*\\.template\\.py$")
        if (PYTHON_TEMPLATE_SOURCES)
            add_custom_command(TARGET "${MODULE}" POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E copy_if_different ${PYTHON_TEMPLATE_SOURCES} ${CMAKE_CURRENT_SOURCE_DIR}
                COMMENT "Copying Python template files to source directory"
            )
        endif()
    endif()
    # Install python files into the 'python' folder of the installation tree
    set(PYTHON_SOURCES ${AUTOCODER_GENERATED_OTHER} ${SOURCE_FILES})
    list(FILTER PYTHON_SOURCES INCLUDE REGEX "^.*\\.py$")
    list(FILTER PYTHON_SOURCES EXCLUDE REGEX "^.*\\.template\\.py$")
    set_target_properties(${MODULE} PROPERTIES FPRIME_PYTHON_SOURCES "${PYTHON_SOURCES}")
endfunction(fprime_python_add_module_target)


# Function `fprime_python_add_deployment_target`:
#
# Generates the pybind11 module for the specified deployment target. This will create a shared library that can be
# imported into Python containing the F´ deployment.
#
####
function(fprime_python_add_deployment_target MODULE TARGET SOURCES DEPENDENCIES FULL_DEPENDENCIES)
    fprime_python_add_module_target("${MODULE}" "${TARGET}" "${SOURCES}" "${DEPENDENCIES}")
     run_ac_set("${MODULE}" "autocoder/fprime_python") # Run the fprime_python autocoder on this module
    _fprime_python_generate_init_file("${MODULE}" "${FULL_DEPENDENCIES}")
    set_property(SOURCE ${FPRIME_PYTHON_DEPLOYMENT_INIT_FILE} PROPERTY GENERATED TRUE)
    pybind11_add_module("fprime_python" ${FPRIME_PYTHON_DEPLOYMENT_INIT_FILE})
    list(REMOVE_ITEM FULL_DEPENDENCIES "${MODULE}")
    target_link_libraries("fprime_python" PUBLIC ${FPRIME_PYTHON_DEPLOYMENT_MODULES} ${FULL_DEPENDENCIES} Fw_Types fprime-python_FprimePy)
    install(TARGETS "fprime_python"
            LIBRARY DESTINATION "python"
            COMPONENT "fprime-python"
    )

    foreach(DEPENDENCY IN LISTS FULL_DEPENDENCIES MODULE)
        get_target_property(PY_SOURCES ${DEPENDENCY} FPRIME_PYTHON_SOURCES)
        if (PY_SOURCES)
            install(FILES ${PY_SOURCES} DESTINATION "python" COMPONENT "fprime-python")
        endif()
    endforeach()
    add_custom_command(TARGET "fprime_python" POST_BUILD COMMAND "${CMAKE_COMMAND}"
            -DCMAKE_INSTALL_COMPONENT=fprime-python -P ${CMAKE_BINARY_DIR}/cmake_install.cmake)
    #add_dependencies("fprime_python" "${MODULE}_fprime_python")
endfunction()

####
# Function `_fprime_python_generate_init_file`:
#
# Generates the pybind11 file that contains all the initialization code for the fprime_python deployment.
#####
function(_fprime_python_generate_init_file MODULE FULL_DEPENDENCIES)
    foreach(DEPENDENCY IN LISTS FULL_DEPENDENCIES)
        if (TARGET "${DEPENDENCY}_fprime_python")
            get_target_property(MODULE_JSON_FILES "${DEPENDENCY}" FPRIME_PYTHON_GENERATED_JSON_FILES)
            get_target_property(MODULE_HPP_FILES "${DEPENDENCY}" FPRIME_PYTHON_GENERATED_HPP_FILES)
            list(APPEND ALL_JSON_FILES ${MODULE_JSON_FILES})
            list(APPEND ALL_HPP_FILES ${MODULE_HPP_FILES})
            list(APPEND ALL_MODULES "${DEPENDENCY}_fprime_python")
        endif()
    endforeach()
    set(ENV{PYTHONPATH} "${FPRIME_PYTHON_PYTHON_PATH}")
    execute_process(
        COMMAND "${PYTHON}" -m "fprime_python" "initialization" "--dry-run" "--output-directory" "${CMAKE_CURRENT_BINARY_DIR}" --header-files ${ALL_HPP_FILES} "--json-files" ${ALL_JSON_FILES}
        OUTPUT_VARIABLE GENERATED_INIT_FILE
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    message(STATUS "Generated fprime_python init file: ${GENERATED_INIT_FILE}")
    add_custom_command(
        OUTPUT ${GENERATED_INIT_FILE}
        DEPENDS ${ALL_JSON_FILES}
        COMMAND ${CMAKE_COMMAND} -E env PYTHONPATH=${FPRIME_PYTHON_PYTHON_PATH}
                "${PYTHON}" -m "fprime_python" "initialization" "--output-directory" "${CMAKE_CURRENT_BINARY_DIR}" --header-files ${ALL_HPP_FILES} "--json-files" ${ALL_JSON_FILES}
    )
    set(FPRIME_PYTHON_DEPLOYMENT_MODULES "${ALL_MODULES}" PARENT_SCOPE)
    set(FPRIME_PYTHON_DEPLOYMENT_INIT_FILE "${GENERATED_INIT_FILE}" PARENT_SCOPE)
endfunction()