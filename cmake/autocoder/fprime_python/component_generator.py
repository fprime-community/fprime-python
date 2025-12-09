
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Tuple, TypeAlias

from fprime_python_model.fpp_ast.fpp_ast import FormalParamKind
from fprime_python_model.semantics.symbol import Symbol
from fprime_python_model.semantics.types_values import StringType
from fprime_python_model.semantics.analysis import Analysis
from fprime_python_model.semantics.component import Component
from fprime_python_model.semantics.command import CommandNonParam
from fprime_python_model.semantics.port_instance import PortInstance, GeneralPortInstance

from fprime_python_model.semantics.command import Command, CommandOpcode
from fprime_python_model.semantics.tlm_channel import TlmChannel, TlmChannelId
from fprime_python_model.semantics.event import Event, EventId
from fprime_python_model.semantics.param import Param, ParamId
from types import SimpleNamespace

from .binding_generator import STANDARD_INDENT, FppPybindBindingGenerator, CodeGenerator, DataHelper

In: TypeAlias = Tuple[Analysis, ...]

def fake_param(type_string: str, name: str) -> SimpleNamespace:
    """ Create a fake paramater with the given type string and name """
    return SimpleNamespace(cpp_type=type_string, name=name)

class ObjectDataHelper(DataHelper):
    """ Base class for processing object data """
    def __init__(self, object, analysis: Analysis):
        """ Construct a ObjectDataHelper for the given object """
        self.object = object
        self.analysis = analysis
    
    def __getattribute__(self, name: str):
        """ Get the named attribute first from the helper, then from the wrapped object
        
        ObjectDataHelper are intended to patch holes in the analysis information for a given object. When an
        attribute is accessed, we first consult the helper for information, but fallback to the wrapped object in order
        to allow these objects to function interchangeably.

        Args:
            name: The name of the attribute to access
        Returns:
            The value of the attribute from the helper or the wrapped object
        """
        try:
            return super().__getattribute__(name)
        except AttributeError:
            return self.object.__getattribute__(name)
    
    @property
    def troll(self) -> str:
        """ Get the underlying object

        ...because trolls live *under* the bridge.
        """
        return self.object

    @property
    def unqualified_name(self) -> str:
        """ Get the unqualified name of this parameter """
        return self.get_unqualified_name(self.troll)

    @staticmethod
    def is_a(object, cls) -> bool:
        """ Check if the wrapped object is an instance of the given class """
        return isinstance(getattr(object, "troll", object), cls)

class DataTypeDataHelper(ObjectDataHelper):
    """ Helper class for processing type data """
    @property
    def cpp_type(self) -> str:
        """ Get the C++ type string for this type """
        if self.object is None:
            return "void"
        elif isinstance(self.object, StringType):
            return "--string--"
        symbol = Symbol.construct(self.object.node)
        return self.get_fully_qualified_cpp_name(symbol, self.analysis)


class PortDataHelper(ObjectDataHelper):
    """ Helper class for processing port data """

    @property
    def type(self):
        """ Get the type of this port """
        return self.object.get_type()

    @property
    def parameters(self):
        """ Get the parameters for this port """
        _, node, _ = self.type.symbol.node
        return [FormalParameterDataHelper(param, self.analysis) for param in node.data.params]

    @property
    def return_type(self):
        """ Get the return_type for this port """
        _, node, _ = self.type.symbol.node
        if node.data.return_type is None:
            return DataTypeDataHelper(None, self.analysis)
        type_definition = self.analysis.type_map[node.data.return_type._id]
        return DataTypeDataHelper(type_definition, self.analysis)

class CommandDataHelper(ObjectDataHelper):
    """ Helper class for processing port data """

    @property
    def parameters(self):
        """ Get the parameters for this port """
        _, node, _ = self.troll.a_node
        return [FormalParameterDataHelper(param, self.analysis) for param in node.data.params]

class FormalParameterDataHelper(ObjectDataHelper):
    """ Helper class for processing formal parameter data """

    @property
    def cpp_type(self) -> str:
        """ Get the C++ type string for this formal parameter """
        _, node, _ = self.object
        base_type = self.type.cpp_type
        const_clause = "const" if not self.type.is_primitive() and node.data.kind == FormalParamKind.VALUE else ""
        reference_clause = "&" if not self.type.is_primitive() or node.data.kind == FormalParamKind.REF else ""
        return f"{const_clause} {base_type}{reference_clause}"

    @property
    def name(self):
        """ Get the name of this formal parameter """
        _, node, _ = self.object
        return node.data.name

    @property
    def type(self):
        """ Get the type of this formal parameter """
        _, node, _ = self.object
        type_definition = self.analysis.type_map[node.data.type_name._id]
        return DataTypeDataHelper(type_definition, self.analysis)

class ComponentParameterDataHelper(ObjectDataHelper):
    """ Helper class for processing component parameter data """
    
    @property
    def type(self):
        """ Get the type of this parameter """
        _, node, _ = self.troll.a_node
        type_definition = self.analysis.type_map[node.data.type_name._id]
        return DataTypeDataHelper(type_definition, self.analysis)

class ComponentDataHelper(ObjectDataHelper):
    """ Helper class for processing component data """
    event_kind_to_severity = {
        "activity high": "ACTIVITY_HI",
        "activity low": "ACTIVITY_LO",
        "diagnostic": "DIAGNOSTIC",
        "warning high": "WARNING_HI",
        "warning low": "WARNING_LO",
        "fatal": "FATAL",
    }

    @classmethod
    def event_to_dispatch_method(cls, event) -> str:
        """ Convert an event record to the name of the log_ method
        
        This method takes an event record and converts it to the name of the log_ method that is used to send the event
        from the component. The method name is derived from the event's severity and unqualified name

        Args:
            event: The event record to convert
        Returns:
            The name of the log_ method for the event
        """
        _, u_node, _ = event.a_node
        severity = cls.event_kind_to_severity[u_node.data.severity.value]
        event_name = cls.get_unqualified_name(event)
        return f"log_{severity}_{event_name}"
    
    def get_ports(self, kind_filter: str="", type_filter: type=PortInstance) -> List[GeneralPortInstance]:
        """ Return the ports matching the kind filter and type filter
        
        This will take the set of all ports and filter them down to those that match the kind and type filters. The
        kind filter performs a substring inclusion match, and defaults to "", or match all. The type filter performs an
        instanceof check and defaults to all PortInstance objects.

        Args:
            kind_filter: A substring to match against the port kind
            type_filter: A type to filter the ports by
        Returns:
            A list of ports matching the filters
        """
        return [
            port for port in self.ports
            if kind_filter in str(port.a_node[1].data.kind.value) and ObjectDataHelper.is_a(port, type_filter)
        ]

    @property
    def fqn(self) -> str:
        """ Get the fully qualified name for this component """
        return self.get_fully_qualified_name(self.troll, self.analysis)
    
    @property
    def unqualified_name(self) -> str:
        """ Get the unqualified name for this component """
        return self.get_unqualified_name(self.troll)
    
    @property
    def cpp_fqn(self) -> str:
        """ Get the fully qualified C++ name for this component """
        return self.get_fully_qualified_cpp_name(self.troll, self.analysis)

    @property
    def kind(self) -> str:
        """ Get the kind of this component """
        return self.troll.a_node[1].data.kind.value

    @property
    def events(self) -> List[Event]:
        """ Return the event objects for this component """
        return list(self.troll.event_map.values())
    
    @property
    def commands(self) -> List[Command]:
        """ Return the command objects for this component """
        return [CommandDataHelper(command, self.analysis) for command in self.troll.command_map.values() if ObjectDataHelper.is_a(command, CommandNonParam)]
    
    @property
    def parameters(self) -> List[Param]:
        """ Return the parameter objects for this component """
        return [ComponentParameterDataHelper(param, self.analysis) for param in self.troll.param_map.values()]

    @property
    def channels(self) -> List[TlmChannel]:
        """ Return the telemetry channel objects for this component """
        return list(self.troll.tlm_channel_map.values())
    
    @property
    def ports(self) -> List[GeneralPortInstance]:
        """ Return the port objects for this component """
        return [PortDataHelper(port, self.analysis) for port in self.troll.port_map.values()]
    
    @property
    def general_ports(self) -> List[GeneralPortInstance]:
        """ Return the general port objects for this component """
        return [port for port in self.ports if isinstance(port, GeneralPortInstance)]
    
    @property
    def special_ports(self) -> List[GeneralPortInstance]:
        """ Return the special port objects for this component """
        return [port for port in self.ports if not isinstance(port, GeneralPortInstance)]

COMPONENT_TEMPLATE = """
pybind11::class_<{fqn}>(m, "{unqualified_class_name}")
{STANDARD_INDENT}{definitions};
"""

COMPONENT_TLM_TEMPLATE = """
.def("tlmWrite_{name}", &{fqn}::tlmWrite_{name}, pybind11::arg("arg"), pybind11::arg("_tlmTime") = Fw::Time())
""".strip()

COMPONENT_PRM_TEMPLATE = """.def("paramGet_{name}", &{fqn}::paramGet_{name}_helper)"""

class ComponentPybindGenerator(FppPybindBindingGenerator):
    """ Provides the generation of pybind11 bindings for FPP components"""

    def get_type_lines(self, component: Component, in_: In) -> List[str]:
        """ Generate the lines for the C++ binding file for a component type
        
        Component types require an initialization function that binds the component's members. This function will
        generate those lines along with the necessary class definition.
        """
        analysis, *_ = in_
        component = ComponentDataHelper(component, analysis)

        has_time_port = bool(component.get_ports(kind_filter="time get"))
        has_commands = bool(component.commands)
        is_queued = component.kind == "queued"

        # Establish the set of .def functions required by this component. This set includes a standard .def
        # declarations for each present item of: output ports, events, "doDispatch", "getTime", and "cmdResponse_out".

        # First establish a set of functions whose presence is optional and based on the components properties
        optional_functions = [("doDispatch", is_queued), ("getTime", has_time_port), ("cmdResponse_out", has_commands)]
        standard = [optional for optional, exists in optional_functions if exists]

        # Add in the output ports, and events
        output_ports = component.get_ports(kind_filter="output", type_filter=GeneralPortInstance)
        standard += [f"{DataHelper.get_unqualified_name(name)}_out" for name in output_ports] + \
                    [component.event_to_dispatch_method(event) for event in component.events]
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
        definitions = "\n".join(self.indent(definitions)).strip()

        return COMPONENT_TEMPLATE.format(
            fqn=component.cpp_fqn,
            unqualified_class_name=component.unqualified_name,
            definitions=definitions,
            STANDARD_INDENT=STANDARD_INDENT
        ).splitlines()
    
    def get_cpp_includes(self, type_object, _):
        return super().get_cpp_includes(type_object, _) + [
            f'#include "{self.include_manager.get_include_path(self.get_annotated_node(type_object)).replace("ComponentAc.hpp", ".hpp")}"'
        ]

COMPONENT_DEFINITION_TEMPLATE = """
// Auto-generated component implementation for {unqualified_name}
#ifndef FPRIME_PYTHON_{unqualified_name_upper}_AC_HPP
#define FPRIME_PYTHON_{unqualified_name_upper}_AC_HPP
{include_block}
{namespace_block}
#endif // FPRIME_PYTHON_{unqualified_name_upper}_AC_HPP
""".strip()

COMPONENT_IMPLEMENTATION_TEMPLATE = """
// Auto-generated component implementation for {unqualified_name}
{include_block}
{namespace_block}
""".strip()

COMPONENT_NAMESPACE_TEMPLATE = """namespace {namespace} {{
{namespace_block}
}} // Namespace {namespace}
"""

COMPONENT_CTOR_DTOR_TEMPLATE = """
{unqualified_name} ::{unqualified_name}(const char* name) : {unqualified_name}ComponentBase(name) {{}}
""".strip()

COMPONENT_INIT_TEMPLATE = """
void {unqualified_name} ::init({depth_arg}FwEnumStoreType instance) {{
{STANDARD_INDENT}pybind11::gil_scoped_acquire acquired{{}};
{STANDARD_INDENT}pybind11::module_ module = pybind11::module_::import("{unqualified_name}");
{STANDARD_INDENT}// Construct the mirror Python object
{STANDARD_INDENT}this->m_self = module.attr("{unqualified_name}")();
{STANDARD_INDENT}// Call the auto-coded initialization function passing in the C++ mirrored object
{STANDARD_INDENT}this->m_self.attr("_init_ac")(this);
{STANDARD_INDENT}// Continue the standard initialization of F Prime
{STANDARD_INDENT}{unqualified_name}ComponentBase::init({depth_arg_name_with_comma}instance);
}}
""".strip()

COMPONENT_IN_PORT_DECLARATION_TEMPLATE = """{return_type} {class_qualifier}{port_name}_handler({port_arg_specification}){terminator}"""
COMPONENT_IN_PORT_TEMPLATE = """
{port_handler_declaration}
{STANDARD_INDENT}pybind11::gil_scoped_acquire acquired{{}};
{STANDARD_INDENT}pybind11::object return_value = m_self.attr("{port_name}_handler")({port_arg_names});
{STANDARD_INDENT}{return_cast_block}
}}
""".strip()
COMPONENT_RETURN_CAST_TEMPLATE = "return {py_object_name}.cast<{return_type}>();".strip()
""""""

COMPONENT_COMMAND_DECLARATION_TEMPLATE = """void {class_qualifier}{command_name}_cmdHandler({command_arg_specification}){terminator}"""
COMPONENT_COMMAND_TEMPLATE = """
{command_handler_declaration}
{STANDARD_INDENT}pybind11::gil_scoped_acquire acquired{{}};
{STANDARD_INDENT}m_self.attr("{command_name}_cmdHandler")({command_arg_names});
}}
""".strip()

COMPONENT_PARAMETER_DECLARATION_TEMPLATE = """std::tuple<{parameter_type}, Fw::ParamValid> {class_qualifier}paramGet_{parameter_name}_helper(){terminator}"""
COMPONENT_PARAMETER_TEMPLATE = """
{parameter_helper_declaration}
{STANDARD_INDENT}Fw::ParamValid _status_;
{STANDARD_INDENT}{parameter_type} _value_ = this->paramGet_{parameter_name}(_status_);
{STANDARD_INDENT}return std::make_tuple(_value_, _status_);
}}
""".strip()

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

COMPONENT_USING_TEMPLATE = "using {unqualified_name}ComponentBase::{member_name};"


COMPONENT_PYTHON_IMPLEMENTATION_TEMPLATE = """
import fprime_python
from {unqualified_name}BaseAc import {unqualified_name}Base


class {unqualified_name}({unqualified_name}Base):
    {port_handler_functions}
    {command_handler_functions}
""".strip()

COMPONENT_PORT_HANDLER_PYTHON_TEMPLATE = """
    def {port_name}_handler(self, {port_arg_names}):
        \"\"\" Handle the {port_name} port \"\"\"
        pass
""".strip()

COMPONENT_COMMAND_HANDLER_PYTHON_TEMPLATE = """
    def {command_name}_cmdHandler(self, {command_arg_names}):
        \"\"\" Handle the {command_name} command \"\"\"
        self.cmdResponse_out(opCode, cmdSeq, fprime_python.Fw.CmdResponse(fprime_python.Fw.CmdResponse.T.OK))
""".strip()

"""
namespace {{ item.ns }} {
    class __attribute__((visibility("default"))) {{ item.name }} : public {{ item.name }}ComponentBase {
      public:
        /**
         * {{ item.name }}: c++ function implementations that delegate across to the python side.
         */
        {{ item.name }}(const char* name);

        // init function loads python code
        void init({%- if item.kind != "passive" -%}const NATIVE_INT_TYPE queueDepth, {%- endif -%}const NATIVE_INT_TYPE instance);

        ~{{ item.name }}();

        {% for in_port in item.in_ports -%}
        void {{ in_port.name }}_handler({{ ",".join(in_port.arg_full_texts) }});
        {% endfor %}
        {% for command in item.commands -%}
        void {{ command.name }}_cmdHandler({{ ", ".join(command.arg_full_texts) }});
        {% endfor %}

        {% for parameter in item.parameters %}
        std::tuple<{{ parameter.data_type }}, Fw::ParamValid> paramGet_{{ parameter.name }}_helper();
        {% endfor %}
      public:
        {% if item.kind == "queued" %}
        // doDispatch binding
        using {{ item.name }}ComponentBase::doDispatch;
        {% endif %}
        // Changing access modifiers for command response
        {% if item.commands %}
        // using {{ item.name }}ComponentBase::cmdResponse_out;
        void cmdResponse_out(FwOpcodeType opCode, U32 cmdSeq, Fw::CmdResponse::T response)
        {
          Fw::CmdResponse convertResponse(response);
          {{ item.name }}ComponentBase::cmdResponse_out(opCode, cmdSeq, convertResponse);
        }
        {%- endif %}
        {% if item.commands or items.channels or items.events or item.parameters %}
        using {{ item.name }}ComponentBase::getTime;
        {%- endif -%}
        // Changing access modifiers for output ports
        {% for out_port in item.out_ports -%}
        using {{ item.name }}ComponentBase::{{ out_port.name }}_out;
        {% endfor %}
        // Changing access modifiers for output calls to channels
        {% for channel in item.channels -%}
        using {{ item.name }}ComponentBase::tlmWrite_{{ channel.name }};
        {% endfor %}
        // Changing access modifiers for output calls to events
        {% for event in item.events -%}
        using {{ item.name }}ComponentBase::log_{{ event.severity }}_{{ event.name }};
        {% endfor %}
        // Changing access modifiers for parameter calls
        {% for param in item.parameters %}
        using {{ item.name }}ComponentBase::paramGet_{{ param.name }};
        {% endfor %}

      public:
        py::object m_self;
    };
}; // Namespace {{ item.ns }}
{% endif %}
{% endfor %}
{% endfor %}
"""

class ComponentImplementationGenerator(CodeGenerator):
    """"""
    @staticmethod
    def fix_pass_by(cpp_type: str, is_command: bool) -> str:
        """ Remove const and reference from a parameter string when told to do so"""
        if "--string--" in cpp_type and is_command:
            return "const Fw::CmdStringArg&"
        if "--string--" in cpp_type:
            return "const Fw::StringBase&"
        if is_command and cpp_type.startswith("const ") and cpp_type.endswith("&"):
            return cpp_type[len("const "):-len("&")]
        return cpp_type
    
    def get_param_specification(self, param_list: List[FormalParameterDataHelper], is_command: bool=False) -> str:
        """ Get the parameter specification string for a list of formal parameters """
        argument_spec = ", ".join(f"{self.fix_pass_by(param.cpp_type, is_command)} {param.name}" for param in param_list)
        return argument_spec

    def get_cpp_lines(self, component: Component, in_: In) -> List[str]:
        """ Generate the lines for the C++ implementation file for a component type

        Get the lines of a component's implementation that require special handling (i.e. not simply a using statement)
        for use in a component C++ implementation.
                
        """
        analysis, *_ = in_
        component = ComponentDataHelper(component, analysis)

        lines = COMPONENT_CTOR_DTOR_TEMPLATE.format(unqualified_name=component.unqualified_name).splitlines()
        lines += COMPONENT_INIT_TEMPLATE.format(
            unqualified_name=component.unqualified_name,
            depth_arg="const FwSizeType queueDepth, " if component.kind != "passive" else "",
            depth_arg_name_with_comma="queueDepth, " if component.kind != "passive" else "",
            STANDARD_INDENT=STANDARD_INDENT
        ).splitlines()
        lines += [
            COMPONENT_IN_PORT_TEMPLATE.format(
                port_handler_declaration=COMPONENT_IN_PORT_DECLARATION_TEMPLATE.format(
                    return_type=port.return_type.cpp_type,
                    class_qualifier=f"{component.unqualified_name} ::",
                    port_name=port.unqualified_name,
                    port_arg_specification=self.get_param_specification([fake_param("FwIndexType", "portNum")] +list(port.parameters)),
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
        lines += [
            COMPONENT_COMMAND_TEMPLATE.format(
                command_handler_declaration=COMPONENT_COMMAND_DECLARATION_TEMPLATE.format(
                    class_qualifier=f"{component.unqualified_name} ::",
                    command_name=command.unqualified_name,
                    command_arg_specification=self.get_param_specification([fake_param("FwOpcodeType", "opCode"), fake_param("U32", "cmdSeq")] + list(command.parameters), True),
                    terminator=" {"
                ),
                command_name=command.unqualified_name,
                command_arg_names=", ".join(["opCode", "cmdSeq"] + [param.name for param in command.parameters]),
                STANDARD_INDENT=STANDARD_INDENT
            )
            for command in component.commands
        ]
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
        namespaces = component.cpp_fqn.split("::")[:-1]

        def namespace_recurse(namespaces: List[str], interior: List[str]) -> List[str]:
            """ Recurse through namespaces to get fully wrapped namespaced lines """
            interior_lines = namespace_recurse(namespaces[1:], interior) if len(namespaces) > 1 else interior
            return COMPONENT_NAMESPACE_TEMPLATE.format(
                namespace=namespaces[0],
                namespace_block="\n".join(interior_lines)
            ).splitlines()

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

        Get the lines of a component's implementation that require special handling (i.e. not simply a using statement)
        for use in a component C++ implementation.
                
        """
        analysis, *_ = in_
        component = ComponentDataHelper(component, analysis)




        port_handler_declarations = [
            COMPONENT_IN_PORT_DECLARATION_TEMPLATE.format(
                return_type=port.return_type.cpp_type,
                class_qualifier=f"",
                port_name=port.unqualified_name,
                port_arg_specification=self.get_param_specification([SimpleNamespace(cpp_type="FwIndexType", name="portNum")] +list(port.parameters)),
                terminator=";"
            )
            for port in component.get_ports(kind_filter="input", type_filter=GeneralPortInstance)
        ]
        command_handler_declarations = [
            COMPONENT_COMMAND_DECLARATION_TEMPLATE.format(
                class_qualifier=f"",
                command_name=command.unqualified_name,
                command_arg_specification=self.get_param_specification([fake_param("FwOpcodeType", "opCode"), fake_param("U32", "cmdSeq")] + list(command.parameters), True),
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

        def namespace_recurse(namespaces: List[str], interior: List[str]) -> List[str]:
            """ Recurse through namespaces to get fully wrapped namespaced lines """
            interior_lines = namespace_recurse(namespaces[1:], interior) if len(namespaces) > 1 else interior
            return COMPONENT_NAMESPACE_TEMPLATE.format(
                namespace=namespaces[0],
                namespace_block="\n".join(interior_lines)
            ).splitlines()
        base_class_header = Path(self.include_manager.get_include_path(self.get_annotated_node(component))).parent / f"{component.unqualified_name}ComponentAc.hpp"
        includes = [f"#include \"{base_class_header.as_posix()}\""] + ["#include \"fprime-python/fprime-python.hpp\""]
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
        """
        analysis, *_ = in_
        component = ComponentDataHelper(component, analysis)
        return PYTHON_CLASS_TEMPLATE.format(
            unqualified_name=component.unqualified_name
        ).splitlines()

    def get_python_implementation_lines(self, component: Component, in_: In) -> List[str]:
        """ Generate the lines for Python implementation file for a component type

        Get the lines of a component's Python implementation that require special handling (i.e. not simply a using
        statement) for use in a component Python implementation.
                
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
