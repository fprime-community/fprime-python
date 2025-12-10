""" fprime_python.visitor:

Implements the visitor pattern used to traverse the FPP AST.
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple, TypeAlias
from pathlib import Path

from fprime_python_model.utils.fpp_ast_visitor import AstVisitor


from fprime_python_model.fpp_ast.fpp_ast_node import AstNode
from fprime_python_model.fpp_ast import fpp_ast


from fprime_python_model.semantics.analysis import Analysis

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

    def base_type_generator(self, generator, _in: In, a_node: fpp_ast.Annotated[AstNode], is_component:bool=False) -> Dict[Path, List[str]]:
        """ Generic method to generate type bindings

        This will perform the basic steps of generating the cpp, hpp, and invocation lines for a given type generator.
        This constructs the type generator as provided and uses it to generate the lines.

        Args:
            generator: The generator class to instantiate
            _in: The input tuple of analysis and include manager
            a_node: The annotated AST node being visited
            is_component: Whether the type is a component (affects naming)
        """
        _, node, _ = a_node
        analysis, include_manager = _in
        type_info = analysis.type_map[node._id] if not is_component else analysis.component_map[node._id]
        line_generator = generator(include_manager)

        cpp_lines = line_generator.get_cpp_lines(type_info, _in)
        hpp_lines = line_generator.get_hpp_lines(type_info, _in)
        invocations = line_generator.get_init_function_invocation(type_info, _in)

        return {
            self.output_path / f"{node.data.name}BindingAc.cpp": cpp_lines,
            self.output_path / f"{node.data.name}BindingAc.hpp": hpp_lines,
            self.output_path / f"{node.data.name}Binding.json": invocations,
        }


    def def_array_annotated_node(
        self, _in: In, a_node: fpp_ast.Annotated[AstNode[fpp_ast.DefArray]]
    ) -> Dict[Path, List[str]]:
        """ Run array generation when array node is visited """
        return self.base_type_generator(ArrayPybindCppGenerator, _in, a_node)

    def def_component_annotated_node(
        self, _in: In, a_node: fpp_ast.Annotated[AstNode[fpp_ast.DefComponent]]
    ) -> Dict[Path, List[str]]:
        """ Run component generation when component node is visited
        
        Components are only generated when they are annotated with @fprime-python. Component generation consists of
        generating both the binding code (cpp/hpp/invocation) as well as the component implementation code
        (cpp/hpp/python base/python implementation) for the component.
        """

        pre_annotation, node, post_annotation = a_node
        full_annotation = pre_annotation + post_annotation
        analysis, include_manager = _in
        type_info = analysis.component_map[node._id]

        # When the component is not annotated for fprime-python, then the visiting stops here
        if FPRIME_PYTHON_ANNOTATION not in [line.strip() for line in full_annotation]:
            return {}
        base_generation = self.base_type_generator(ComponentPybindGenerator, _in, a_node, is_component=True)
   
        instance_generator = ComponentImplementationGenerator(include_manager)
        # This is to extend the #ifndef block around the class HPP lines
        cpp_component_lines = instance_generator.get_cpp_lines(type_info, _in) 
        hpp_component_lines = instance_generator.get_hpp_lines(type_info, _in)

        python_lines = instance_generator.get_python_base_lines(type_info, _in)
        python_implementation_lines = instance_generator.get_python_implementation_lines(type_info, _in)
        return {
            **base_generation,
            self.output_path / f"{node.data.name}.cpp": cpp_component_lines,
            self.output_path / f"{node.data.name}.hpp": hpp_component_lines,
            self.output_path / f"{node.data.name}BaseAc.py": python_lines,
            self.output_path / f"{node.data.name}.template.py": python_implementation_lines
        }

    def def_enum_annotated_node(
        self, _in: In, a_node: fpp_ast.Annotated[AstNode[fpp_ast.DefEnum]]
    ) -> Dict[Path, List[str]]:
        """ Generate enum bindings when enum node is visited """
        return self.base_type_generator(EnumPybindCppGenerator, _in, a_node)
    
    def def_struct_annotated_node(
        self, _in: In, a_node: fpp_ast.Annotated[AstNode[fpp_ast.DefStruct]]
    ) -> Dict[Path, List[str]]:
        """ Generate struct bindings when struct node is visited """
        return self.base_type_generator(StructPybindCppGenerator, _in, a_node)

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
        """ Visit a translation unit
        
        Translation are filtered down to the accepted translation units only because visiting TUs outside the scope of
        the current module risks visiting the same types in multiple modules.
        """
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