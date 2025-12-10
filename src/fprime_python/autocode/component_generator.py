""" component_generator.py

Provides the generation of pybind11 bindings for FPP components.
"""
from pathlib import Path
from typing import List, Tuple, TypeAlias
from types import SimpleNamespace

from fprime_python_model.semantics.analysis import Analysis
from fprime_python_model.semantics.component import Component
from fprime_python_model.semantics.port_instance import GeneralPortInstance

from .binding_generator import STANDARD_INDENT, FppPybindBindingGenerator, CodeGenerator, DataHelper
from .data_helpers import ComponentDataHelper, FormalParameterDataHelper

In: TypeAlias = Tuple[Analysis, ...]

def fake_param(type_string: str, name: str) -> SimpleNamespace:
    """ Fake a formal parameter object for use in argument lists

    F Prime functions (ports, commands, etc.) use formal parameter objects to represent their arguments. C++ requires a
    few additional parameters for functions: portNum, opCode, cmdSeq, etc. This function creates a simple object that
    masquerades as a formal parameter for use in argument lists.

    Args:
        type_string: The C++ type string of the parameter
        name: The name of the parameter
    """
    return SimpleNamespace(cpp_type=type_string, name=name)


# Templates for component binding generation
COMPONENT_TEMPLATE = """
pybind11::class_<{fqn}>(m, "{unqualified_class_name}")
{STANDARD_INDENT}{definitions};
"""
# Template used to translate telemetry channel emit call bindings while preserving default time argument
COMPONENT_TLM_TEMPLATE = """
.def("tlmWrite_{name}", &{fqn}::tlmWrite_{name}, pybind11::arg("arg"), pybind11::arg("_tlmTime") = Fw::Time())
""".strip()

# Component parameter get helper binding template. Calls a helper so that status and value can be returned as a tuple.
COMPONENT_PRM_TEMPLATE = """.def("paramGet_{name}", &{fqn}::paramGet_{name}_helper)"""

class ComponentPybindGenerator(FppPybindBindingGenerator):
    """ Provides the generation of pybind11 bindings for FPP components
    
    This generator creates the pybind11 binding code required to bind FPP components to Python. This includes the
    various telemetry channels, parameters, handlers, and commands.
    """

    def get_type_lines(self, component: Component, in_: In) -> List[str]:
        """ Generate the lines for the C++ binding file for a component type
        
        Component types require an initialization function that binds the component's members. This function will
        generate those lines along with the necessary class definition.
        """
        analysis, *_ = in_
        component = ComponentDataHelper(component, analysis)

        # Determine component properties that affect binding generation
        has_time_port = bool(component.get_ports(kind_filter="time get"))
        has_commands = bool(component.commands)
        is_queued = component.kind == "queued"

        # Establish the set of .def functions required by this component. This set includes a standard .def
        # declarations for each present item of: output ports, events, "doDispatch", "getTime", and "cmdResponse_out".

        # First establish a set of functions whose presence is optional and based on the components properties
        optional_functions = [("doDispatch", is_queued), ("getTime", has_time_port), ("cmdResponse_out", has_commands)]
        standard = [optional for optional, exists in optional_functions if exists]

        # Add in the output ports, and events to the standard list
        output_ports = component.get_ports(kind_filter="output", type_filter=GeneralPortInstance)
        standard += [f"{DataHelper.get_unqualified_name(name)}_out" for name in output_ports] + \
                    [component.event_to_dispatch_method(event) for event in component.events]
        # Generate the .def lines for each standard method using the standard_def helper
        definitions = [self.standard_def(method, component.cpp_fqn) for method in standard]

        # Definitions should be augmented with the special declarations for parameters and telemetry channels as
        # parameters use a helper function, and telemetry channels require a default argument for the time.
        definitions += [
            COMPONENT_PRM_TEMPLATE.format(name=DataHelper.get_unqualified_name(param), fqn=component.cpp_fqn)
            for param in component.parameters
        ] + [
            COMPONENT_TLM_TEMPLATE.format(name=DataHelper.get_unqualified_name(channel), fqn=component.cpp_fqn)
            for channel in component.channels
        ]

        # Indent and join the definitions into a single block, feed it into the template, and return the lines
        definitions = "\n".join(self.indent(definitions)).strip()
        return COMPONENT_TEMPLATE.format(
            fqn=component.cpp_fqn,
            unqualified_class_name=component.unqualified_name,
            definitions=definitions,
            STANDARD_INDENT=STANDARD_INDENT
        ).splitlines()
    
    def get_cpp_includes(self, type_object, _):
        """ Get the C++ includes for a component type
        
        This will get the standard includes and add in the component's own header file. This header file is the header
        file of the fprime-python generated component implementation and not the base Ac component header.
        """
        base_ac_header = self.include_manager.get_include_path(self.get_annotated_node(type_object))
        component_header =base_ac_header.replace("ComponentAc.hpp", ".hpp")
        return super().get_cpp_includes(type_object, _) + [f'#include "{component_header}"']

#### Component Implementation Generation Templates ####
# These templates are used to generate the C++ implementation files that replace the standard hand-written
# implementations and provide calls to/from the Python layer.
####


# Template for the definition of a component's auto-generated "implementation" header file
COMPONENT_DEFINITION_TEMPLATE = """
// Auto-generated component implementation for {unqualified_name}
#ifndef FPRIME_PYTHON_{unqualified_name_upper}_AC_HPP
#define FPRIME_PYTHON_{unqualified_name_upper}_AC_HPP
{include_block}
{namespace_block}
#endif // FPRIME_PYTHON_{unqualified_name_upper}_AC_HPP
""".strip()

# Template for the auto-generated component "implementation" C++ file
COMPONENT_IMPLEMENTATION_TEMPLATE = """
// Auto-generated component implementation for {unqualified_name}
{include_block}
{namespace_block}
""".strip()

# Namespace wrapper template
COMPONENT_NAMESPACE_TEMPLATE = """namespace {namespace} {{
{namespace_block}
}} // Namespace {namespace}
"""
# Component constructor template
COMPONENT_CTOR_TEMPLATE = """
{unqualified_name} ::{unqualified_name}(const char* name) : {unqualified_name}ComponentBase(name) {{}}
""".strip()

# Component init function template. This function does some important work:
# 1. Acquires the GIL for Python interaction as we are doing Python calls
# 2. Imports the Python module for this component.
# 3. Constructs the mirrored Python object found in the Python module and stores it in the C++ object's m_self member
#    allowing for C++ to reference the paired Python object.
# 4. Calls the auto-coded _init_ac function on the Python object that is provided by the autocode python base class
#    allowing python to register the paired C++ "this" object.
# 5. Continues with the standard F Prime initialization by calling the base class init function. 
#
# Note: GIL use is scoped to just the portions that require Python interaction.
COMPONENT_INIT_TEMPLATE = """
void {unqualified_name} ::init({depth_arg}FwEnumStoreType instance) {{
{STANDARD_INDENT}// Acquire the GIL and import the Python module releasing the GIL before continuing with C++ init
{STANDARD_INDENT}{{
{STANDARD_INDENT}{STANDARD_INDENT}pybind11::gil_scoped_acquire acquired{{}};
{STANDARD_INDENT}{STANDARD_INDENT}pybind11::module_ module = pybind11::module_::import("{unqualified_name}");
{STANDARD_INDENT}{STANDARD_INDENT}// Construct the mirror Python object, storing it for C++ access
{STANDARD_INDENT}{STANDARD_INDENT}this->m_self = module.attr("{unqualified_name}")();
{STANDARD_INDENT}{STANDARD_INDENT}// Call auto-coded initialization function storing the C++ "this" object for Python
{STANDARD_INDENT}{STANDARD_INDENT}this->m_self.attr("_init_ac")(this);
{STANDARD_INDENT}}}
{STANDARD_INDENT}// Continue the standard initialization of F Prime
{STANDARD_INDENT}{unqualified_name}ComponentBase::init({depth_arg_name_with_comma}instance);
}}
""".strip()

# Template for component input port handler implementation including arguments
COMPONENT_IN_PORT_DECLARATION_TEMPLATE = """
{return_type} {class_qualifier}{port_name}_handler({port_arg_specification}){terminator}
""".strip()

# Template for component input port handler implementation. This template acquires the GIL in preparation for the call
# into python, calls python, and casts the return value if necessary. GIL is released upon exit of the handler invocation.
COMPONENT_IN_PORT_TEMPLATE = """
{port_handler_declaration}
{STANDARD_INDENT}pybind11::gil_scoped_acquire acquired{{}};
{STANDARD_INDENT}pybind11::object return_value = m_self.attr("{port_name}_handler")({port_arg_names});
{STANDARD_INDENT}{return_cast_block}
}}
""".strip()

# Template for return value casting from pybind11 object to C++ type
COMPONENT_RETURN_CAST_TEMPLATE = "return {py_object_name}.cast<{return_type}>();".strip()

# Template for component command handler implementation including arguments
COMPONENT_COMMAND_DECLARATION_TEMPLATE = """
void {class_qualifier}{command_name}_cmdHandler({command_arg_specification}){terminator}
""".strip()

# Template for component command handler implementation. This template acquires the GIL in preparation for the call
# into python and calls python. GIL is released upon exit of the handler invocation.
COMPONENT_COMMAND_TEMPLATE = """
{command_handler_declaration}
{STANDARD_INDENT}pybind11::gil_scoped_acquire acquired{{}};
{STANDARD_INDENT}m_self.attr("{command_name}_cmdHandler")({command_arg_names});
}}
""".strip()

# Template for component parameter get helper implementation. Since parameters return both a value and a status we need
# to call a helper function that returns both as a tuple because the C++ style in/out parameters do not map cleanly to
# Python return values.
COMPONENT_PARAMETER_DECLARATION_TEMPLATE = """
std::tuple<{parameter_type}, Fw::ParamValid> {class_qualifier}paramGet_{parameter_name}_helper(){terminator}
""".strip()

# Template for component parameter get helper implementation. This template reads the parameter value using the standard
# F Prime call, and then returns both the value and status as a tuple to Python. This is done to avoid in/out parameter
# patterns that do not map cleanly to Python.
COMPONENT_PARAMETER_TEMPLATE = """
{parameter_helper_declaration}
{STANDARD_INDENT}Fw::ParamValid _status_;
{STANDARD_INDENT}{parameter_type} _value_ = this->paramGet_{parameter_name}(_status_);
{STANDARD_INDENT}return std::make_tuple(_value_, _status_);
}}
""".strip()

# Template for using statement for base class member
COMPONENT_USING_TEMPLATE = "using {unqualified_name}ComponentBase::{member_name};"

# Template for the full component class definition in the header file. This includes the constructor, init function,
# deleted copy constructor, default destructor, port handler declarations, command handler declarations, parameter
# get functions, and using statements for base class members.
#
# Importantly it defines the m_self member that holds the mirrored Python object allowing C++ to call into Python.
COMPONENT_CLASS_TEMPLATE = """
class __attribute__((visibility("default"))) {unqualified_name} : public {unqualified_name}ComponentBase {{
  public:
{STANDARD_INDENT}{unqualified_name}(const char* name);
{STANDARD_INDENT}{unqualified_name}(const {unqualified_name}&) = delete;
{STANDARD_INDENT}~{unqualified_name}() = default;
{STANDARD_INDENT}void init({depth_arg}const FwEnumStoreType instance);
  public:
{port_handler_declarations}
{command_handler_declarations}
{parameter_helper_declarations}
  public:
{using_statements}
  public:
{STANDARD_INDENT}pybind11::object m_self;
}};
""".strip()


#### Python Component Implementation Templates ####
# These templates are used to generate the Python implementation templates that replace the standard implementation
# templates and can be filled in by the user.
####

# Template for the basic component Python implementation file. This template includes the necessary imports, class
# skeleton, and method stubs for port handlers and command handlers.
COMPONENT_PYTHON_IMPLEMENTATION_TEMPLATE = """
\"\"\" {unqualified_name} Python component implementation

This is the Python implementation for the {unqualified_name} component. This class extends the auto-coded python base
class {unqualified_name}Base that provides the necessary plumbing to connect to the C++ stub connected to the rest of
the F Prime topology.
\"\"\"
import fprime_py
from {unqualified_name}BaseAc import {unqualified_name}Base


class {unqualified_name}({unqualified_name}Base):
    \"\"\" Python implementation for the {unqualified_name} component \"\"\"
    {port_handler_functions}
    {command_handler_functions}
""".strip()

# Template for component port handler function stub
COMPONENT_PORT_HANDLER_PYTHON_TEMPLATE = """
    def {port_name}_handler(self, {port_arg_names}):
        \"\"\" Handle the {port_name} port \"\"\"
        # TODO: Implement port handler
        pass
""".strip()

# Template for component command handler function stub
COMPONENT_COMMAND_HANDLER_PYTHON_TEMPLATE = """
    def {command_name}_cmdHandler(self, {command_arg_names}):
        \"\"\" Handle the {command_name} command \"\"\"
        # TODO: Implement command handler
        self.cmdResponse_out(opCode, cmdSeq, fprime_py.Fw.CmdResponse(fprime_py.Fw.CmdResponse.T.OK))
""".strip()

# Template for the Python component base class that provides delegation to the C++ implementation and the _init_ac
# method that stores a pointer to the C++ object. Delegation is done via __getattr__ and __setattr__ methods such that
# any attribute will be deledgated to the C++ implementation unless it is the "this" attribute itself.
PYTHON_CLASS_TEMPLATE = '''
class {unqualified_name}Base(object):
    """ Auto-coded base class for {unqualified_name}
    
    This base class is auto-generated to mirror the C++ component class. It delegates the methods to the C++
    implementation provided by the _init_ac function. The __init_ac function must be called first and is done so by the
    auto-generated init function in the component C++.

    This implies that a Python user cannot instantiate this class directly and must rely on the F Prime topology to
    instantiate the component as all F Prime components are.

    Caution: This class relies on an absence of an __init__ method. We cannot guarantee that a derived class will not
        define an __init__ method that fails to call super().__init__() and thus this implementation must not rely on
        __init__ to be called. Instead this implementation relies on the _init_ac method to be called by the C++
        and converts use of the internal delegate before that call to an Exception.
    """
    def _init_ac(self, this):
        """ Initialize 'this' object to redirect into the C++ implementation
        
        In order to automatically bind to the C++ implementation, a pointer to the C++ object must be stored and
        within this class. This method *must* be called before any Python calls are made.
        """
        self.this = this

    def __getattr__(self, name):
        """ Delegate attribute read access to the C++ implementation
        
        This method provides automatic delegation to the C++ implementation for any attribute that are not found within
        this implementation. 

        Args:
            name: The name of the attribute to access
        Returns:
            The value of the attribute from the C++ implementation
        """
        # Prevent infinite recursion if looking for 'this' before it is initialized. If "this" was set in _init_ac,
        # then this fallback method would not have been called. If the name is "this", then _init_ac was not called and
        # therefore this attributed cannot be accessed.
        if name == "this":
            raise AttributeError("'this' not initialized. Call _init_ac first.")
        elif not hasattr(self, "this"):
            raise Exception("{unqualified_name} cannot be instantiated directly. It must be instantiated by F Prime")
        return getattr(self.this, name)

        
    def __setattr__(self, name, value):
        """ Delegate attribute write access to the C++ implementation
        
        This method provides automatic delegation to the C++ implementation for any attribute that are not found within
        this implementation. First, it this method attempts to set the attribute in the C++ implementation. If that
        fails the attribute is set in this (Python) implementation.

        Args:
            name: The name of the attribute to set
            value: The value to set the attribute to
        """
        try:
            return setattr(self.this, name, value)
        except Exception:
            super().__setattr__(name, value)
'''

def fix_arguments(cpp_type: str, is_command: bool) -> str:
    """ Fix argument types for calls

    Strings must be select their type by the usage. Comands use CmdStringArg while ports use StringBase. This
    function selects between the two.

    Additionally, this patches a bug where the FPP generated arguments are passed-by-value, and thus need to have
    const and & striped from them.

    Args:
        cpp_type: The C++ type string of the argument (or --string-- for strings)
        is_command: Whether this argument is for a command (True) or not (False)
    Returns:
        The fixed C++ type string for use in argument lists
    """
    if "--string--" in cpp_type and is_command:
        return "const Fw::CmdStringArg&"
    if "--string--" in cpp_type:
        return "const Fw::StringBase&"
    if is_command and cpp_type.startswith("const ") and cpp_type.endswith("&"):
        return cpp_type[len("const "):-len("&")]
    return cpp_type


def get_param_specification(param_list: List[FormalParameterDataHelper], is_command: bool=False) -> str:
    """ Get the parameter specification string for a list of formal parameters
    
    This is a helper function that generates the C++ argument specification string for a list of formal parameters.
    This includes the type and name of each parameter, separated by commas.

    Args:
        param_list: list of formal parameters where each element is has attributes .cpp_type and .name
        is_command: Whether these parameters are for a command (True) or not (False)
    Returns:
        The C++ argument specification string
    """
    argument_spec = ", ".join(f"{fix_arguments(param.cpp_type, is_command)} {param.name}" for param in param_list)
    return argument_spec

def namespace_recurse(namespaces: List[str], interior: List[str]) -> List[str]:
    """ Recursively wrap lines in namespaces
    
    This is a helper function that recursively wraps a set of lines in namespace blocks without using :: notation.
    This will wrap one instance of COMPONENT_NAMESPACE_TEMPLATE per recursion until all namespaces are wrapped
    around the interior lines.

    Args:
        namespaces: The list of namespaces to wrap around the interior lines
        interior: The lines to wrap in namespaces
    Returns:
        The lines wrapped in the namespace blocks
    """
    interior_lines = namespace_recurse(namespaces[1:], interior) if len(namespaces) > 1 else interior
    return COMPONENT_NAMESPACE_TEMPLATE.format(
        namespace=namespaces[0],
        namespace_block="\n".join(interior_lines)
    ).splitlines()


class ComponentImplementationGenerator(CodeGenerator):
    """ Generator for Python/C++ component implementation files

    This generator creates the C++ implementation files that connect the F Prime component topology to the Python
    layer. This includes the necessary port handler implementations, command handler implementations, and parameter
    get helper implementations.

    Additionally, this generator creates the Python base class that provides delegation to the C++ implementation and
    the Python implementation template that provides the skeleton for user code.
    """
    def get_cpp_lines(self, component: Component, in_: In) -> List[str]:
        """ Generate the lines for the C++ implementation file for a component type

        Get the lines of a component's implementation. This will be used for the auto-generated component C++
        implementation which connects the F Prime topology (via component base) to the Python layer.

        Args:
            component: The component type to generate the implementation for
            in_: The input analysis context
        Returns:
            The lines of the component's C++ implementation file
        """
        analysis, *_ = in_
        component = ComponentDataHelper(component, analysis)

        # Start with the constructor and init function
        lines = COMPONENT_CTOR_TEMPLATE.format(unqualified_name=component.unqualified_name).splitlines()
        lines += COMPONENT_INIT_TEMPLATE.format(
            unqualified_name=component.unqualified_name,
            depth_arg="const FwSizeType queueDepth, " if component.kind != "passive" else "",
            depth_arg_name_with_comma="queueDepth, " if component.kind != "passive" else "",
            STANDARD_INDENT=STANDARD_INDENT
        ).splitlines()
        # Now add in a port template for each port 
        lines += [
            # Port invocation with sub-templates for declaration and return casting
            COMPONENT_IN_PORT_TEMPLATE.format(
                # Port handler declaration with arguments
                port_handler_declaration=COMPONENT_IN_PORT_DECLARATION_TEMPLATE.format(
                    return_type=port.return_type.cpp_type,
                    class_qualifier=f"{component.unqualified_name} ::",
                    port_name=port.unqualified_name,
                    port_arg_specification=get_param_specification([fake_param("FwIndexType", "portNum")] +list(port.parameters)),
                    terminator=" {",
                ),
                port_name=port.unqualified_name,
                port_arg_names=", ".join(["portNum"] + [param.name for param in port.parameters]),
                STANDARD_INDENT=STANDARD_INDENT,
                return_cast_block=COMPONENT_RETURN_CAST_TEMPLATE.format(
                    py_object_name="return_value",
                    return_type=port.return_type.cpp_type
                ) if port.return_type.cpp_type != "void" else ""
            )
            for port in component.get_ports(kind_filter="input", type_filter=GeneralPortInstance)
        ]
        # Now add in a command handler for each command
        lines += [
            COMPONENT_COMMAND_TEMPLATE.format(
                command_handler_declaration=COMPONENT_COMMAND_DECLARATION_TEMPLATE.format(
                    class_qualifier=f"{component.unqualified_name} ::",
                    command_name=command.unqualified_name,
                    command_arg_specification=get_param_specification([fake_param("FwOpcodeType", "opCode"), fake_param("U32", "cmdSeq")] + list(command.parameters), True),
                    terminator=" {"
                ),
                command_name=command.unqualified_name,
                command_arg_names=", ".join(["opCode", "cmdSeq"] + [param.name for param in command.parameters]),
                STANDARD_INDENT=STANDARD_INDENT
            )
            for command in component.commands
        ]
        # Now add in a parameter get helper for each parameter
        lines += [
            COMPONENT_PARAMETER_TEMPLATE.format(
                parameter_helper_declaration=COMPONENT_PARAMETER_DECLARATION_TEMPLATE.format(
                    class_qualifier=f"{component.unqualified_name} ::",
                    parameter_name=param.unqualified_name,
                    parameter_type=param.type.cpp_type,
                    terminator=" {"
                ),
                parameter_name=param.unqualified_name,
                parameter_type=param.type.cpp_type,
                STANDARD_INDENT=STANDARD_INDENT
            )
            for param in component.parameters
        ]
        # Calculate the namespaces for this component
        namespaces = component.cpp_fqn.split("::")[:-1]
        class_header = Path(self.include_manager.get_include_path(self.get_annotated_node(component))).parent / f"{component.unqualified_name}.hpp"
        includes = [f"#include \"{class_header.as_posix()}\""]
        component_hpp_lines = COMPONENT_IMPLEMENTATION_TEMPLATE.format(
            unqualified_name=component.unqualified_name,
            include_block="\n".join(includes),
            namespace_block="\n".join(namespace_recurse(namespaces, lines)),
        ).splitlines()
        return component_hpp_lines


    def get_hpp_lines(self, component: Component, in_: In) -> List[str]:
        """ Generate the lines for the C++ implementation file for a component type

        Get the lines of a component's implementation header. This will be used for the auto-generated component C++
        implementation header which declares the necessary port handler implementations, command handler
        implementations etc.

        Args:
            component: The component type to generate the implementation for
            in_: The input analysis context
        Returns:
            The lines of the component's C++ implementation header file        
        """
        analysis, *_ = in_
        component = ComponentDataHelper(component, analysis)

        port_handler_declarations = [
            COMPONENT_IN_PORT_DECLARATION_TEMPLATE.format(
                return_type=port.return_type.cpp_type,
                class_qualifier=f"",
                port_name=port.unqualified_name,
                port_arg_specification=get_param_specification([SimpleNamespace(cpp_type="FwIndexType", name="portNum")] +list(port.parameters)),
                terminator=";"
            )
            for port in component.get_ports(kind_filter="input", type_filter=GeneralPortInstance)
        ]
        command_handler_declarations = [
            COMPONENT_COMMAND_DECLARATION_TEMPLATE.format(
                class_qualifier=f"",
                command_name=command.unqualified_name,
                command_arg_specification=get_param_specification([fake_param("FwOpcodeType", "opCode"), fake_param("U32", "cmdSeq")] + list(command.parameters), True),
                terminator=";"
            )
            for command in component.commands
        ]
        parameter_helper = [
            COMPONENT_PARAMETER_DECLARATION_TEMPLATE.format(
                class_qualifier=f"",
                parameter_name=param.unqualified_name,
                parameter_type=param.type.cpp_type,
                terminator=";"
            )
            for param in component.parameters
        ]

        has_time_port = bool(component.get_ports(kind_filter="time get"))
        has_commands = bool(component.commands)
        is_queued = component.kind == "queued"

        # First establish a set of functions whose presence is optional and based on the components properties
        optional_functions = [("doDispatch", is_queued), ("getTime", has_time_port), ("cmdResponse_out", has_commands)]
        standard = [optional for optional, exists in optional_functions if exists]

        # Add in the output ports, and events
        output_ports = component.get_ports(kind_filter="output", type_filter=GeneralPortInstance)
        standard += [f"{DataHelper.get_unqualified_name(name)}_out" for name in output_ports] + \
                    [component.event_to_dispatch_method(event) for event in component.events] + \
                    [f"tlmWrite_{DataHelper.get_unqualified_name(channel)}" for channel in component.channels]
        using_statements = [COMPONENT_USING_TEMPLATE.format(unqualified_name=component.unqualified_name, member_name=method) for method in standard]

        lines = COMPONENT_CLASS_TEMPLATE.format(
            unqualified_name=component.unqualified_name,
            depth_arg="const FwSizeType queueDepth, " if component.kind != "passive" else "",
            port_handler_declarations="\n".join(self.indent(port_handler_declarations)),
            command_handler_declarations="\n".join(self.indent(command_handler_declarations)),
            parameter_helper_declarations="\n".join(self.indent(parameter_helper)),
            using_statements="\n".join(self.indent(using_statements)),
            STANDARD_INDENT=STANDARD_INDENT
        ).splitlines()


        namespaces = component.cpp_fqn.split("::")[:-1]
        base_class_header = Path(self.include_manager.get_include_path(self.get_annotated_node(component))).parent / f"{component.unqualified_name}ComponentAc.hpp"
        includes = [f"#include \"{base_class_header.as_posix()}\""] + ["#include \"FprimePython/FprimePython.hpp\""]
        component_hpp_lines = COMPONENT_DEFINITION_TEMPLATE.format(
            unqualified_name=component.unqualified_name,
            include_block="\n".join(includes),
            namespace_block="\n".join(namespace_recurse(namespaces, lines)),
            unqualified_name_upper=component.unqualified_name.upper()
        ).splitlines()
        return component_hpp_lines

    def get_python_base_lines(self, component: Component, in_: In) -> List[str]:
        """ Generate the lines for Python base-class lines
                
        This method generates the lines for the Python base class that will be inherited by the user-defined Python
        implementation. It represents the mirror of the C++ generation.

        Args:
            component: The component type to generate the base class for
            in_: The input analysis context
        Returns:
            The lines of the component's Python base class file
        """
        analysis, *_ = in_
        component = ComponentDataHelper(component, analysis)
        return PYTHON_CLASS_TEMPLATE.format(
            unqualified_name=component.unqualified_name
        ).splitlines()

    def get_python_implementation_lines(self, component: Component, in_: In) -> List[str]:
        """ Generate the lines for Python implementation file for a component type

        This method generates the lines for the Python implementation template that provides the skeleton for user code
        for the component. This includes the port handler stubs and command handler stubs.
        
        Args:
            component: The component type to generate the implementation for
            in_: The input analysis context
        Returns:
            The lines of the component's Python implementation file
        """
        analysis, *_ = in_
        component = ComponentDataHelper(component, analysis)

        port_handler_functions = f"\n{STANDARD_INDENT}".join([
            COMPONENT_PORT_HANDLER_PYTHON_TEMPLATE.format(
                port_name=port.unqualified_name,
                port_arg_names=", ".join(["portNum"] + [param.name for param in port.parameters])
            )
            for port in component.get_ports(kind_filter="input", type_filter=GeneralPortInstance)
        ])

        command_handler_functions = f"\n{STANDARD_INDENT}".join([
            COMPONENT_COMMAND_HANDLER_PYTHON_TEMPLATE.format(
                command_name=command.unqualified_name,
                command_arg_names=", ".join(["opCode", "cmdSeq"] + [param.name for param in command.parameters])
            )
            for command in component.commands
        ])

        return COMPONENT_PYTHON_IMPLEMENTATION_TEMPLATE.format(
            unqualified_name=component.unqualified_name,
            port_handler_functions=port_handler_functions,
            command_handler_functions=command_handler_functions
        ).splitlines()

