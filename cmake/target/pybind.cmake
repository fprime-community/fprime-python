####
# pybind.cmake:
#
# A target used to make bindings for the python language. This will handle fprime data types
# enabling them for use the python layer. This will also be used to generate the interace
# mappings for the component targets.
#
# Author: mstarch
####
cmake_policy(SET CMP0079 NEW)
set(BINDING_AUTOCODER_PATH ${CMAKE_CURRENT_LIST_DIR}/../../autocode/pybind_gen.py)

####
# setup_pybind_autocoder:
#
# Setup the pybind autocoder for fprime items.  Input TARGET_NAME is the name of the current target that can be read
# for cached properties.
####
function(setup_pybind_autocoder TARGET_NAME)
    find_program(PYTHON NAMES python3 python REQUIRED)
    if (NOT PYTHON)
        message(FATAL_ERROR "Failed to find python3, cannot run python bindings")
    endif()
    string(REPLACE ";" ":" FPRIME_BUILD_LOCATIONS_SEP "${FPRIME_BUILD_LOCATIONS}")
    add_custom_command(
        OUTPUT ${CMAKE_BINARY_DIR}/PyBindAc.hpp ${CMAKE_BINARY_DIR}/PyBindAc.cpp ${CMAKE_BINARY_DIR}/fprime_pybind.py
        COMMAND
            ${CMAKE_COMMAND} -E chdir ${CMAKE_BINARY_DIR}
            ${CMAKE_COMMAND} -E env
                PYTHONPATH="${FPRIME_FRAMEWORK_PATH}/Autocoders/Python/src"
                BUILD_ROOT="${FPRIME_BUILD_LOCATIONS_SEP}"
                ${PYTHON} ${BINDING_AUTOCODER_PATH}
                --ai $<TARGET_PROPERTY:${TARGET_NAME},PYTHON_BINDINGS>
                # --deps $<TARGET_PROPERTY:${TARGET_NAME},PYTHON_DEPS>
        DEPENDS
            ${BINDING_AUTOCODER_PATH}
            $<TARGET_PROPERTY:${TARGET_NAME},PYTHON_BINDINGS>
            $<TARGET_PROPERTY:${TARGET_NAME},PYTHON_DEPS>
        COMMAND_EXPAND_LISTS
    )
    set_source_files_properties(${CMAKE_BINARY_DIR}/PyBindAc.cpp PROPERTIES GENERATED TRUE)
    set_source_files_properties(${CMAKE_BINARY_DIR}/PyBindAc.hpp PROPERTIES GENERATED TRUE)
endfunction(setup_pybind_autocoder)

####
# add_global_target:
#
# Adds in the global target that sets up a single pybind run. This run is composed of generator statements that will
# expand once the whole project has been scanned.
####
function(add_global_target TARGET_NAME)
# Add the target as a library and the autocoder to generate it
    setup_pybind_autocoder("${TARGET_NAME}")
    add_library(${TARGET_NAME} ${CMAKE_BINARY_DIR}/PyBindAc.cpp)

    # Initialize pybind target properties
    set_property(TARGET ${TARGET_NAME} PROPERTY PYTHON_BINDINGS)
    set_property(TARGET ${TARGET_NAME} PROPERTY PYTHON_INSTALLS ${CMAKE_BINARY_DIR}/fprime_pybind.py)
    set_property(TARGET ${TARGET_NAME} PROPERTY PYTHON_DEPS)

    # Dependency and link graph setup including the core package
    add_dependencies(${TARGET_NAME} fprime-python_FprimePy)
    target_link_libraries(${TARGET_NAME} PUBLIC fprime-python_FprimePy)

    # Add a custom package_gen target for installing the python
    add_custom_target(pybind_package_gen
        COMMAND ${CMAKE_COMMAND} -E make_directory ${FPRIME_INSTALL_DEST}/python
        COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_PROPERTY:${TARGET_NAME},PYTHON_INSTALLS> ${FPRIME_INSTALL_DEST}/python
        DEPENDS $<TARGET_PROPERTY:${TARGET_NAME},PYTHON_INSTALLS> ${TARGET_NAME}
        COMMAND_EXPAND_LISTS)
endfunction(add_global_target)



####
# register_python_component:
#
# Function used to annotate a component AI and PY pair as a pybind object. This will trigger generation of bindings. It
# **must** be called after register_fprime_module.
####
function(register_python_component AI_XML PY_IMPL)
    # Get input variables MODULE_NAME and TGT_MOD_DEPS from the mod deps applied to the target
    get_module_name("${CMAKE_CURRENT_LIST_DIR}")

    # Check that the user supplied items in the right order
    # if (NOT TARGET ${MODULE_NAME})
    #     message(FATAL_ERROR "1register_python_component must be called after register_fprime_module in CMakeLists.txt")
    # endif()
    get_target_property(TGT_MOD_DEPS "${MODULE_NAME}" MOD_DEPS)
    # if (NOT TGT_MOD_DEPS)
    #     message(FATAL_ERROR "2register_python_component must be called after register_fprime_module in CMakeLists.txt")
    # endif()
    get_property(TGT_MOD_DEPS TARGET "${MODULE_NAME}" PROPERTY MOD_DEPS)
    message("RAWR")
    message("${MODULE_NAME} doing python thingy")
    message("TGT_MOD_DEPS: ${TGT_MOD_DEPS}")

    # Setup cache properties that eill be used later
    set_property(TARGET pybind APPEND PROPERTY PYTHON_BINDINGS ${AI_XML})
    set_property(TARGET pybind APPEND PROPERTY PYTHON_INSTALLS ${PY_IMPL})
    set_property(TARGET pybind APPEND PROPERTY PYTHON_DEPS ${TGT_MOD_DEPS})

    # This target must depend on pybind as it build the necessary binding setup
    add_dependencies(${MODULE_NAME} fprime-python_FprimePy) # Direct dependency for Fw package
    add_dependencies(pybind ${MODULE_NAME})
    target_link_libraries(pybind PUBLIC ${MODULE_NAME})
endfunction(register_python_component)

####
# add_module_target:
#
# Per module target call.  Here we just store properties for use when we generate global bindings.
####
# "${MODULE}" "${TARGET_NAME}" "${SOURCES}" "${DEPENDENCIES}"
# changed because setup_single_target - lex-ari
function(add_module_target MODULE_NAME TARGET_NAME SOURCES MOD_DEPS)
    foreach (AC_IN IN LISTS SOURCES)
        # Constructing a global list of types in the system
	# if (AC_IN MATCHES ".*(Array)|(Serializable)|(Enum)Ai.xml$" AND NOT MODULE_NAME MATCHES "^Autocoders*")
    #         set_property(TARGET ${TARGET_NAME} APPEND PROPERTY PYTHON_BINDINGS ${AC_IN})
	#         add_dependencies(${TARGET_NAME} ${MODULE_NAME})
    #     # Translate MOD_DEPS to a component property
    #     elseif (AC_IN MATCHES ".*ComponentAi.xml$")
        fprime_ai_info("${AC_IN}" "${MODULE_NAME}")
        set_property(TARGET ${MODULE_NAME} PROPERTY MOD_DEPS ${MODULE_NAME} ${MOD_DEPS} ${MOD_DEPS})
        # endif()
    endforeach()
endfunction(add_module_target)

function(add_deployment_target TARGET)
endfunction(add_deployment_target)

function(pybind_add_module_target MODULE TARGET_NAME SOURCES DEPENDENCIES)
    # add_module_target("${MODULE}" "${TARGET_NAME}" "${SOURCES}" "${DEPENDENCIES}")
endfunction(pybind_add_module_target)

function(pybind_add_global_target TARGET)
    add_global_target(pybind)
endfunction(pybind_add_global_target)