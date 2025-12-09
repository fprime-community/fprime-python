""" fprime_python.include:

This module contains utilities for managing include statements in generated C++ code. It is constructed around a set of
prefixes, and then can determine the include location based on those prefixes and the AST node provided.
"""
from typing import Dict, List
from pathlib import Path

from fprime_python_model.fpp_ast import fpp_ast
from fprime_python_model.fpp_ast.fpp_ast_node import AstNode
from fprime_python_model.semantics.symbol import Symbol, AliasTypeSymbol, ArraySymbol, ComponentSymbol, ConstantSymbol, EnumSymbol, PortSymbol, StructSymbol, TopologySymbol

class IncludeManager(object):
    """ Manages the include paths for generated C++ code based on provided prefixes

    Prefixes are synonymous with the include directories provided by the project. These prefixes are expected to be
    relative to the working directory and represent the base paths where generated header files can be found.

    Include directories are relative to the nearest prefix.
    """
    symbol_type_to_include_type_name = {
        AliasTypeSymbol: "Alias",
        ArraySymbol: "Array",
        ComponentSymbol: "Component",
        ConstantSymbol: "Constant",
        EnumSymbol: "Enum",
        PortSymbol: "Port",
        StructSymbol: "Serializable",
        TopologySymbol: "Topology",

    }

    def __init__(self, prefixes: List[Path], location_map: Dict[int, str], prefix_working_directory: Path=Path.cwd()) -> None:
        """ Initialize the IncludeManager

        The IncludeManager is initialized with a set of prefixes, a location map, and an optional working directory that
        the prefixes are relative to.

        Args:
            prefixes: A list of Path objects representing the prefixes for include paths
            location_map: A mapping from AST node IDs to their source file locations
            prefix_working_directory: The working directory that the prefixes are relative to (default: current
        
        """
        self.prefixes = [(prefix_working_directory / prefix).resolve() for prefix in prefixes]
        self.location_map = location_map

    def get_include_path(self, node: fpp_ast.Annotated[AstNode]) -> str:
        """ Determine the include path for a given AST node
        
        This will take in the AstNode and determine the include path based on the prefixes provided during. The include
        path will be relative to the nearest prefix.

        This function raises a ValueError if no include path can be determined and a KeyError if the node has not known
        location.
        
        Args:
            node: The AST node to determine the include path for

        Returns:
            The include path as a string
        """
        symbol = Symbol.construct(node)
        location = Path(self.location_map[symbol.get_node_id()].path.parent).resolve()
        
        parent_prefixes = [prefix for prefix in self.prefixes if location.is_relative_to(prefix.resolve())]

        possible_include_paths = [location.relative_to(prefix) for prefix in parent_prefixes]
        possible_include_paths.sort(key=lambda path: len(path.parents))

        try:
            type_name = self.symbol_type_to_include_type_name[type(symbol)]
        except KeyError:
            raise ValueError(f"Unsupported symbol type for include path determination: {type(symbol)}")

        if possible_include_paths:
            return f"{possible_include_paths[0].as_posix()}/{symbol.get_unqualified_name()}{type_name}Ac.hpp"
        raise ValueError(f"No prefixed location for {location} under {parent_prefixes}")