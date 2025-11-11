from __future__ import annotations
import itertools
import logging
LOGGER = logging.getLogger("fprime-python.autocode.generator.cpp_python_base")
from typing import List
from fprime_python_model.fpp_ast.fpp_ast import FormalParamKind
from fprime_python_model.semantics.analysis import Analysis
from fprime_python_model.semantics.port_instance import Direction, GeneralPortInstance, DefPortPortInstanceType

PORT_TEMPLATE = """
{function_signature} {{
    py::gil_scoped_acquire acquired{{}};
    m_self.attr("{port_name}_handler")({argument_name_list});
    py::gil_scoped_release released{{}};
}}
"""

FUNCTION_SIGNATURE_TEMPLATE = """{return_type} {function_name}({parameter_specification_list})"""

PARAMETER_TEMPLATE = """{pre_annotation}{const_qualifier}{fully_qualified_type} {reference_qualifier}{parameter_name}{{optional_comma}}{post_annotation}"""

class CppPythonBaseGenerator(object):



    def get_lines(self, component_analysis: Analysis, full_analysis: Analysis) -> List[str]:
        """ Generate the lines for the C++ binding file """
        lines = []
        for port in [port for port in component_analysis.port_map.values() if isinstance(port, GeneralPortInstance) and port.get_direction() == Direction.INPUT]:
            port_lines = self.get_port_lines(component_analysis.a_node[1].data.name, port, full_analysis)
            print("\n".join(port_lines))

        return lines

    def get_port_lines(self, component_class_name: str, port_analysis: GeneralPortInstance, full_analysis: Analysis) -> List[str]:
        """ Generate the lines for the C++ binding file for a port """
        port_name = port_analysis.get_node().data.name # HELP: why can't I just do port_analysis.get_unqualified_name()?
        port_type = port_analysis.get_type()

        if not isinstance(port_type, DefPortPortInstanceType):
            LOGGER.warning("Skipping port %s of component %s: unsupported port type %s", port_name, component_class_name, type(port_type))
        _, node, _ = port_type.symbol.node
        port_data = node.data
        return_type = "void"
        parameters_lines = list(itertools.chain.from_iterable([self.get_parameter_lines(param, full_analysis) for param in port_data.params]))
        parameters_lines = [line.format(optional_comma=",") for line in parameters_lines[:-1]] + [line.format(optional_comma="") for line in parameters_lines[-1:]]

        function_name = "{component_class_name}::{port_name}_handler".format(component_class_name=component_class_name, port_name=port_name)
        function_signature = self.get_function_signature_lines(return_type, function_name, parameters_lines)

        
        return PORT_TEMPLATE.format(component_class_name=component_class_name,
                                    port_name=port_name,
                                    function_signature="\n".join(function_signature),
                                    argument_name_list=", ".join([param.data.name for _, param, _ in port_data.params])
                                    ).splitlines()

    def get_parameter_lines(self, param: tuple, full_analysis: Analysis) -> List[str]:
        """ Generate segment for a parameter """
        pre_annotation, node, post_annotation = param
        data = node.data

        parameter_name = data.name
        parameter_kind = data.kind

        pre_annotation_lines = "\n".join(self.get_pre_annotation_lines(pre_annotation))
        post_annotation_lines = "\n".join(self.get_post_annotation_lines(post_annotation))

        return PARAMETER_TEMPLATE.format(
            pre_annotation=pre_annotation_lines,
            const_qualifier="",
            fully_qualified_type=self.get_fully_qualified_type(data.type_name, full_analysis),
            reference_qualifier="&" if parameter_kind == FormalParamKind.REF else "",
            parameter_name=parameter_name,
            post_annotation=post_annotation_lines,
        ).splitlines()
    
    def get_function_signature_lines(self, return_type: str, function_name: str, parameter_lines: list[str]) -> str:
        """ Generate function signature lines """
        indentation = " " * (len(return_type) + 1 + len(function_name) + 1) 
        # Indent all but the first line
        indented_lines = parameter_lines[:1] + [f"{indentation}{line}" for line in parameter_lines[1:]]
        return FUNCTION_SIGNATURE_TEMPLATE.format(
            return_type=return_type,
            function_name=function_name,
            parameter_specification_list="\n".join(indented_lines),
        ).splitlines()

    def get_fully_qualified_type(self, type_name, full_analysis: Analysis) -> str:
        """ Get the fully qualified type name """
        type_name_symbol = full_analysis.use_def_map.get(type_name.get_id())
        type_name = full_analysis.get_qualified_name_from_map(type_name_symbol)
        return str(type_name).replace(".", "::")

    def get_post_annotation_lines(self, post_annotation: List[str]) -> str:
        """ Generate post-annotation lines """
        return ["  //!< {post_annotation}".format(post_annotation=line) for line in post_annotation]

    def get_pre_annotation_lines(self, pre_annotation: List[str]) -> str:
        """ Generate pre-annotation lines """
        return [" //! {pre_annotation}".format(pre_annotation=line) for line in pre_annotation]