""" fprime_python.visitor:

Implements the visitor pattern used to traverse the FPP AST.

Generating Python bindings starts by finding what to generate them for. This visitor walks the model from
the translation-unit level down to the definitions that get bindings: every array, enum and struct, and
the components and topologies annotated with @fprime-python.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import fpp

from .component_generator import ComponentBindingGenerator, ComponentImplementationGenerator
from .constants import FPRIME_PYTHON_ANNOTATION
from .include import IncludeManager
from .topology_instance_generator import TopologyBindingGenerator
from .types_generator import (
    ArrayBindingGenerator,
    EnumBindingGenerator,
    StructBindingGenerator,
)
from .view import ComponentView, TopologyView, is_annotated


class AnnotatedDefinitionVisitor(fpp.AstVisitor):
    """ Visitor generating bindings for the definitions of one set of translation units

    Bindings for FPP types are generated for every type in the visited translation units, because a bound
    component can name any of them in a port, command, event, channel or parameter. Components and
    topologies are only bound when they carry the @fprime-python annotation, since binding one commits the
    project to implementing it in Python.

    Definitions nested inside a component are not visited: they belong to the component's own namespace in
    C++ and are not reachable as module-level Python types.
    """

    def __init__(
        self,
        output_path: Path,
        analysis: fpp.Analysis,
        include_manager: IncludeManager,
    ):
        """ Initialize the visitor

        Args:
            output_path: Directory the generated files are written into
            analysis: The analyzed model being visited
            include_manager: Resolves the include paths of the headers the generated code needs
        """
        self.output_path = output_path
        self.analysis = analysis
        self.include_manager = include_manager
        self.output: Dict[Path, str] = {}

    def symbol_of(self, node: fpp.ast.AstNode) -> fpp.Symbol.Variant:
        """ The symbol a definition node defines

        Args:
            node: The definition node
        Returns:
            The symbol of that definition
        """
        return self.analysis.symbol_map[node.node_id]

    def emit(self, files: Dict[str, str]) -> None:
        """ Record generated files against the output directory

        Args:
            files: A mapping of file name to file contents
        """
        for name, contents in files.items():
            self.output[self.output_path / name] = contents

    def visit_DefArray(self, node: fpp.ast.DefArray) -> None:
        """ Run array generation when an array node is visited """
        symbol = self.symbol_of(node)
        assert isinstance(node.resolved_type, fpp.Type.Array)
        self.emit(
            ArrayBindingGenerator(self.include_manager, symbol, node.resolved_type).files()
        )

    def visit_DefEnum(self, node: fpp.ast.DefEnum) -> None:
        """ Run enum generation when an enum node is visited """
        symbol = self.symbol_of(node)
        assert isinstance(node.resolved_type, fpp.Type.Enum)
        self.emit(
            EnumBindingGenerator(self.include_manager, symbol, node.resolved_type).files()
        )

    def visit_DefStruct(self, node: fpp.ast.DefStruct) -> None:
        """ Run struct generation when a struct node is visited """
        symbol = self.symbol_of(node)
        assert isinstance(node.resolved_type, fpp.Type.Struct)
        self.emit(
            StructBindingGenerator(self.include_manager, symbol, node.resolved_type).files()
        )

    def visit_DefStateMachine(self, node: fpp.ast.DefStateMachine) -> None:
        """ Skip a state machine definition without descending into it

        fpp's analysis synthesizes a `State` enumeration inside every state machine. F Prime generates that
        enumeration under a flattened name of its own -- `<Machine>_StateEnumAc.hpp` rather than
        `StateEnumAc.hpp` -- and it is not a module-level type a Python implementation names, so descending
        would bind a type that does not exist under a file name that collides between state machines.
        """

    def visit_DefComponent(self, node: fpp.ast.DefComponent) -> None:
        """ Run component generation when a component node is visited

        Components are only generated when they are annotated with @fprime-python. Component generation
        produces both the binding code and the component implementation that forwards into Python.
        """
        if not is_annotated(node, FPRIME_PYTHON_ANNOTATION):
            return
        symbol = self.symbol_of(node)
        component = self.analysis.component_map[symbol]
        # Refuse up front rather than generating a class that will not link
        ComponentView(component).check_supported()
        self.emit(ComponentBindingGenerator(self.include_manager, symbol, component).files())
        self.emit(
            ComponentImplementationGenerator(self.include_manager, symbol, component).files()
        )

    def visit_DefTopology(self, node: fpp.ast.DefTopology) -> None:
        """ Generate topology bindings when an annotated topology node is visited

        A topology holds Python-bound component instances, and Python needs a handle on those instances
        and on the topology's own setup and teardown, so an annotated topology is bound as a whole.
        """
        if not is_annotated(node, FPRIME_PYTHON_ANNOTATION):
            return
        symbol = self.symbol_of(node)
        topology = self.analysis.topology_map[symbol]
        # Refuse up front rather than generating a source file that names a header F Prime never wrote
        TopologyView(topology).check_supported()
        self.emit(TopologyBindingGenerator(self.include_manager, symbol, topology).files())

    def generate(self, model: fpp.Model) -> Dict[Path, str]:
        """ Visit the model's source translation units and generate for their definitions

        The import units are skipped: they are present only to resolve references out of the sources, and
        visiting them would generate the same definition in every module that depends on it. Membership is
        the unit's rather than the file's, so a definition spliced into a source unit by `include` is
        still generated.

        Args:
            model: The analyzed model to generate from
        Returns:
            A mapping of output path to file contents
        """
        self.output = {}
        for translation_unit in model.ast:
            if translation_unit.is_source:
                self.visit(translation_unit)
        return self.output
