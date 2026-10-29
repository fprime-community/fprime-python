""" Stores constants for fprime-python generation """

#: Annotation a component, type or topology must carry to be bound into Python
FPRIME_PYTHON_ANNOTATION: str = "fprime-python"

#: Name recorded in the banner of every generated file
TOOL_NAME: str = "fprime-python"

#: Support header providing the pybind11 include, the F Prime string type casters, and the
#: hooks a project implements to bind its own deployment
SUPPORT_HEADER: str = "FprimePython/FprimePython.hpp"

#: Name of the pybind11 module the generated bindings are attached to
MODULE_NAME: str = "fprime_py"

#: Prefix of the C++ variables holding the module and its submodules. A submodule's variable is this
#: prefix followed by the flattened FPP scope it stands for, so the module itself is the bare prefix.
MODULE_VARIABLE_PREFIX: str = "fprime_"

#: Member of a generated component class that holds the mirrored Python object. The component generator
#: declares it and the topology generator reads it off each bound instance, so both spell it from here.
SELF_MEMBER: str = "m_self"
