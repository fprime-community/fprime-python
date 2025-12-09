""" fprime_python.visitor:

Implements the visitor pattern used to traverse the FPP AST.
"""
from __future__ import annotations
from typing import Dict, List, Tuple, TypeAlias
from abc import abstractmethod
from pathlib import Path

from fprime_python_model.model import FprimePythonModel
from fprime_python_model.utils.fpp_ast_visitor import AstVisitor

from fprime_python_model.semantics.symbol import Symbol

from fprime_python_model.fpp_ast.fpp_ast_node import AstId, AstNode
from fprime_python_model.fpp_ast import fpp_ast
from fprime_python_model.utils.error import InternalError

from fprime_python_model.semantics.analysis import Analysis

from .generator import CppPythonBaseGenerator
from .include import IncludeManager
from .types_generator import ArrayPybindCppGenerator, EnumPybindCppGenerator, StructPybindCppGenerator
from .component_generator import ComponentImplementationGenerator, ComponentPybindGenerator

In: TypeAlias = Tuple[Analysis, IncludeManager]
Out: TypeAlias = Dict[Path, List[str]]


FPRIME_PYTHON_ANNOTATION: str = "fprime-python"


class AnnotatedComponentVisitor(AstVisitor):
    """ Visitor identifying components annotated with @fprime-python
    
    Generating python bindings in fprime-python is done (for components) by using the annotation @fprime-python. This
    visitor recurses from the translation unit level (root of AST) down to components and filters for components
    annotated with the @fprime-python annotation.

    Once identified, the visitor continues to visit the component's members (e.g., commands, events, etc.) detecting
    the properties that need binding generation.
    """
    def __init__(self, output_path: Path, accepted_tus: List[Path], location_map: Dict[int, str]) -> None:
        """ Initialize the visitor """
        self.output_path = output_path
        self.accepted_tus = [tu.resolve() for tu in accepted_tus]
        self.location_map = location_map

    def default(self, in_: In) -> Dict[Path, List[str]]:
        """ Default visit method is no-op """
        return {}

    def def_array_annotated_node(
        self, _in: In, a_node: fpp_ast.Annotated[AstNode[fpp_ast.DefArray]]
    ) -> Dict[Path, List[str]]:
        _, node, _ = a_node
        analysis, include_manager = _in
        type_info = analysis.type_map[node._id]
        line_generator = ArrayPybindCppGenerator(include_manager)

        cpp_lines = line_generator.get_cpp_lines(type_info, _in)
        hpp_lines = line_generator.get_hpp_lines(type_info, _in)
        invocations = line_generator.get_init_function_invocation(type_info, _in)

        return {
            self.output_path / f"{node.data.name}BindingAc.cpp": cpp_lines,
            self.output_path / f"{node.data.name}BindingAc.hpp": hpp_lines,
            self.output_path / f"{node.data.name}Binding.json": invocations,
        }

    def def_component_annotated_node(
        self, _in: In, a_node: fpp_ast.Annotated[AstNode[fpp_ast.DefComponent]]
    ) -> Dict[Path, List[str]]:
        pre_annotation, node, post_annotation = a_node
        full_annotation = pre_annotation + post_annotation

        # When the component is not annotated for fprime-python, then the visiting stops here
        if FPRIME_PYTHON_ANNOTATION not in [line.strip() for line in full_annotation]:
            return {}
        analysis, include_manager = _in
        type_info = analysis.component_map[node._id]
        bind_generator = ComponentPybindGenerator(include_manager)
        instance_generator = ComponentImplementationGenerator(include_manager)
        cpp_binding_lines = bind_generator.get_cpp_lines(type_info, _in)
        hpp_binding_lines = bind_generator.get_hpp_lines(type_info, _in)
        # This is to extend the #ifndef block around the class HPP lines
        cpp_component_lines = instance_generator.get_cpp_lines(type_info, _in) 
        hpp_component_lines = instance_generator.get_hpp_lines(type_info, _in)

        python_lines = instance_generator.get_python_base_lines(type_info, _in)
        python_implementation_lines = instance_generator.get_python_implementation_lines(type_info, _in)
        invocations = bind_generator.get_init_function_invocation(type_info, _in)
        return {
            self.output_path / f"{node.data.name}BindingAc.cpp": cpp_binding_lines,
            self.output_path / f"{node.data.name}BindingAc.hpp": hpp_binding_lines,
            self.output_path / f"{node.data.name}.cpp": cpp_component_lines,
            self.output_path / f"{node.data.name}.hpp": hpp_component_lines,
            self.output_path / f"{node.data.name}Binding.json": invocations,
            self.output_path / f"{node.data.name}BaseAc.py": python_lines,
            self.output_path / f"{node.data.name}.template.py": python_implementation_lines
        }

        return {}
        # Dry run just records the file, but not the lines
        for file, generator in self.file_template_to_visitor.items():
            if self.dry:
                self.generation_map[file]
            else:
                lines = generator.get_lines(in_.component_map[node._id], in_)
                self.generation_map[file] = lines
        return {}


    def def_enum_annotated_node(
        self, _in: In, a_node: fpp_ast.Annotated[AstNode[fpp_ast.DefEnum]]
    ) -> Dict[Path, List[str]]:
        _, node, _ = a_node
        analysis, include_manager = _in
        type_info = analysis.type_map[node._id]
        line_generator = EnumPybindCppGenerator(include_manager)

        cpp_lines = line_generator.get_cpp_lines(type_info, _in)
        hpp_lines = line_generator.get_hpp_lines(type_info, _in)
        invocations = line_generator.get_init_function_invocation(type_info, _in)
        return {
            self.output_path / f"{node.data.name}BindingAc.cpp": cpp_lines,
            self.output_path / f"{node.data.name}BindingAc.hpp": hpp_lines,
            self.output_path / f"{node.data.name}Binding.json": invocations,
        }

    def def_struct_annotated_node(
        self, _in: In, a_node: fpp_ast.Annotated[AstNode[fpp_ast.DefStruct]]
    ) -> Dict[Path, List[str]]:
        _, node, _ = a_node
        analysis, include_manager = _in
        type_info = analysis.type_map[node._id]
        line_generator = StructPybindCppGenerator(include_manager)

        cpp_lines = line_generator.get_cpp_lines(type_info, _in)
        hpp_lines = line_generator.get_hpp_lines(type_info, _in)
        invocations = line_generator.get_init_function_invocation(type_info, _in)
        return {
            self.output_path / f"{node.data.name}BindingAc.cpp": cpp_lines,
            self.output_path / f"{node.data.name}BindingAc.hpp": hpp_lines,
            self.output_path / f"{node.data.name}Binding.json": invocations,
        }

    def def_module_annotated_node(
        self, in_: In, a_node: fpp_ast.Annotated[AstNode[fpp_ast.DefModule]]
    ) -> Out:
        """ Visit a module definition recursing into its members """
        _, node, _ = a_node
        data = node.data
        output = {}
        for m in data.members:
            output.update(self.module_member(in_, m))
        return output

    def module_member(self, in_: In, member: fpp_ast.ModuleMember) -> Out:
        """ Visit a module member """
        # Using the the provided match member function effectively visits types deeper in the AST
        return self.match_module_member(in_, member)

    def translation_unit(self, in_: In, tu: fpp_ast.TransUnit) -> Out:
        """ Visit a translation unit """
        output = {}
        for member in tu.members:
            # Filter out members by translation unit path
            location = Path(self.location_map[member.node[1].node._id].path).resolve()
            if location not in self.accepted_tus:
                continue
            # Note: translation unit members are module members of the implicit module
            output.update(self.module_member(in_, member))
        return output

    def translation_units(
        self, in_: In, tu_list: List[fpp_ast.TransUnit]
    ) -> Out:
        """ Visit a list of translation units """
        output = {}
        for tu in tu_list:
            output.update(self.translation_unit(in_, tu))
        return output