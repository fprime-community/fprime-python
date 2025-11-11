
from abc import ABC, abstractmethod
from typing import List, Tuple, TypeAlias

from fprime_python_model.semantics.types_values import Type
from fprime_python_model.semantics.analysis import Analysis
from fprime_python_model.semantics.component import Component
from fprime_python_model.semantics.command import CommandNonParam
from fprime_python_model.semantics.port_instance import GeneralPortInstance

from .binding_generator import FppPybindBindingGenerator

In: TypeAlias = Tuple[Analysis, ...]

COMPONENT_TEMPLATE = """
py::class_<{fqn}>(m, "{unqualified_class_name}")
    {optional_do_dispatch}
    {optional_command_response}
    {optional_get_time_block}
    {out_port_block}
    {optional_event_block}
    {tlm_block}
    {param_block};   
"""

COMPONENT_DO_DISPATCH_TEMPLATE = """
.def("doDispatch", &{fqn}::doDispatch)
"""

COMPONENT_GET_TIME_TEMPLATE = """
.def("getTime", &{fqn}::getTime)
"""

COMPONENT_COMMAND_TEMPLATE = """
.def("cmdResponse_out", &{fqn}::cmdResponse_out)
"""

COMPONENT_OUT_PORT_TEMPLATE = """
.def("{port_name}_out", &{fqn}::{port_name}_out)
"""

COMPONENT_EVENT_TEMPLATE = """
.def("log_{severity}_{event_name}", &{fqn}::log_{severity}_{event_name})
"""

COMPONENT_TLM_TEMPLATE = """
.def("tlmWrite_{channel_name}", &{fqn}::tlmWrite_{channel_name}, py::arg("arg"), py::arg("_tlmTime") = Fw::Time())
"""

COMPONENT_PRM_TEMPLATE = """
.def("paramGet_{param_name}", &{fqn}::paramGet_{param_name}_helper)
"""


"""
    {%- if item.kind == "queued" -%}
    .def("doDispatch", &{{ item.ns }}::{{ item.name }}::doDispatch)
    {%- endif -%}
    {% if item.commands %}
    .def("cmdResponse_out", &{{ item.ns }}::{{ item.name }}::cmdResponse_out)
    {%- endif -%}
    {% if item.commands or items.channels or items.events or item.parameters %}
    .def("getTime", &{{ item.ns }}::{{ item.name }}::getTime)
    {%- endif -%}
    {% for out_port in item.out_ports %}
    .def("{{ out_port.name }}_out", &{{ item.ns }}::{{ item.name }}::{{ out_port.name }}_out)
    {%- endfor -%}
    {% for event in item.events %}
    .def("log_{{ event.severity }}_{{ event.name }}", &{{ item.ns }}::{{ item.name }}::log_{{ event.severity }}_{{ event.name }})
    {%- endfor -%}
    {% for channel in item.channels %}
    .def("tlmWrite_{{ channel.name }}", &{{ item.ns }}::{{ item.name }}::tlmWrite_{{ channel.name }},py::arg("arg"), py::arg("_tlmTime") = Fw::Time())
    {%- endfor -%}
    {% for param in item.parameters %}
    .def("paramGet_{{ param.name }}", &{{ item.ns }}::{{ item.name }}::paramGet_{{ param.name }}_helper)
    {%- endfor -%};
"""

class FprimePythonComponentGenerator(FppPybindBindingGenerator):
    """ Provides the generation of pybind11 bindings for FPP components"""
    event_kind_to_severity = {
        "activity high": "ACTIVITY_HI",
        "activity low": "ACTIVITY_LO",
        "diagnostic": "DIAGNOSTIC",
        "warning high": "WARNING_HI",
        "warning low": "WARNING_LO",
        "fatal": "FATAL",
    }

    def get_type_lines(self, component: Component, in_: In) -> List[str]:
        """ Generate the lines for the C++ binding file for a component type
        
        Component types require an initialization function that binds the component's members. This function will
        generate those lines along with the necessary class definition.
        """
        _, node, _ = self.get_annotated_node(component)
        unqualified_class_name = self.get_unqualified_name(component, in_)
        fully_qualified_class_name = self.get_fully_qualified_cpp_name(component, in_)


        special_ports = [port for port in component.port_map.values() if not isinstance(port, GeneralPortInstance)]
        output_ports = [port for port in component.port_map.values() if isinstance(port, GeneralPortInstance) and port.a_node[1].data.kind.value == "output"]

        has_time_port = bool([port for port in special_ports if port.a_node[1].data.kind.value == "time get"])
        non_param_commands = [command for command in component.command_map.values() if isinstance(command, CommandNonParam)]
        channels = [channel for channel in component.tlm_channel_map.values()]
        events = [event for event in component.event_map.values()]
        parameters = [param for param in component.param_map.values()]


        optional_do_dispatch = COMPONENT_DO_DISPATCH_TEMPLATE.format(fqn=fully_qualified_class_name) if node.data.kind == "queued" else ""
        optional_get_time_block = COMPONENT_GET_TIME_TEMPLATE.format(fqn=fully_qualified_class_name) if has_time_port else ""
        optional_command_response = COMPONENT_COMMAND_TEMPLATE.format(fqn=fully_qualified_class_name) if non_param_commands else ""

        output_port_block = "\n".join([COMPONENT_OUT_PORT_TEMPLATE.format(port_name=self.get_unqualified_name(port, in_), fqn=fully_qualified_class_name) for port in output_ports])
        channel_block = "\n".join([COMPONENT_TLM_TEMPLATE.format(channel_name=self.get_unqualified_name(channel, in_), fqn=fully_qualified_class_name) for channel in channels])
        event_block = "\n".join([COMPONENT_EVENT_TEMPLATE.format(
                severity=self.event_kind_to_severity.get(event.a_node[1].data.severity.value, event.a_node[1].data.severity.value.upper()),
                event_name=self.get_unqualified_name(event, in_),
                fqn=fully_qualified_class_name)
            for event in events])
        param_block = "\n".join([COMPONENT_PRM_TEMPLATE.format(param_name=self.get_unqualified_name(param, in_), fqn=fully_qualified_class_name) for param in parameters])

        return COMPONENT_TEMPLATE.format(
            fqn=fully_qualified_class_name,
            unqualified_class_name=unqualified_class_name,
            optional_do_dispatch=optional_do_dispatch,
            optional_get_time_block=optional_get_time_block,
            optional_command_response=optional_command_response,
            out_port_block=output_port_block,
            tlm_block=channel_block,
            optional_event_block=event_block,
            param_block=param_block
        ).splitlines()
        