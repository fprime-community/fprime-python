# Setup the pybind11 library so that we may use it

register_fprime_library(
    SOURCES
        "${CMAKE_CURRENT_LIST_DIR}/FprimePy.cpp"
    DEPENDS
        Fw_Types
)


#add_subdirectory("${CMAKE_CURRENT_LIST_DIR}/../pybind11" pybind11)

#get_module_name(${CMAKE_CURRENT_LIST_DIR})

# Add necessary "fprime" libraries to build this package
#add_library(${MODULE_NAME} "${CMAKE_CURRENT_LIST_DIR}/FprimePy.cpp")
#add_dependencies(${MODULE_NAME} Fw_Time Fw_Tlm Fw_Cmd Fw_Log)
#set_property(TARGET ${MODULE_NAME} PROPERTY INTERPROCEDURAL_OPTIMIZATION FALSE)
#target_link_libraries(${MODULE_NAME} PUBLIC pybind11::embed)
#target_include_directories(${MODULE_NAME} PUBLIC ${CMAKE_CURRENT_LIST_DIR}/../pybind11)
#add_custom_target(${MODULE_NAME}_package_gen)

