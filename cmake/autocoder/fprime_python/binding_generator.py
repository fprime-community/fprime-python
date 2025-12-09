""" fprime_python.binding_generator: generates the pybind11 bindings for FPP constructs

Bindings have several components:

1. An initialization function that attaches to a supplied module
2. A header file that declares the initialization function
3. A snippet of code that can be used to call the initialization function

This file provides the base generators for generating these components. Specific generators for given types can inherit
from the constructors in this file.
"""
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Tuple, TypeAlias

from fprime_python_model.semantics.types_values import Type
from fprime_python_model.semantics.analysis import Analysis
from fprime_python_model.semantics.symbol import Symbol

from .include import IncludeManager

In: TypeAlias = Tuple[Analysis, ...]

STANDARD_INDENT = "    "

class DataHelper(object):
    """ Helper class for processing various data objects """

    @staticmethod
    def get_annotated_node(analysis_object):
        """ Get the annotated node for a given analysis object
        
        In some cases, an object may have a .node property that points to the AST node, but in other cases, the AST node
        may be stored in the .a_node property. This method abstracts away this difference and returns the annotated node
        for a given analysis object.

        Args:
            analysis_object: The analysis object to get the annotated node for
        Returns:
            The annotated node for the given analysis object
        """
        return getattr(analysis_object, "node", getattr(analysis_object, "a_node", None))

    @classmethod
    def get_unqualified_name(cls, analysis_object) -> str:
        """ Get the unqualified name for a given analysis object
        
        This method uses a symbol to get the unqualified name for the given analysis object. If the symbol cannot be
        made because this is not a definition, then it attempts to get the name from the AST node directly using the
        data.name field.

        Args:
            analysis_object: The analysis object to get the unqualified name for

        Returns:
            The unqualified name for the given analysis object
        """
        a_node = cls.get_annotated_node(analysis_object)
        try:
            symbol = Symbol.construct(a_node)
            unqualified_name = symbol.get_unqualified_name()
        except ValueError:
            _, node, _ = a_node
            unqualified_name = node.data.name
        return str(unqualified_name)

    @classmethod
    def get_fully_qualified_name(cls, analysis_object, analysis: Analysis) -> str:
        """ Get the fully qualified name for a given analysis object
        
        This method uses a symbol to get the fully qualified name for the given analysis object. The name returned is
        in FPP format (e.g., "Namespace.Component").

        Args:
            analysis_object: The analysis object to get the fully qualified name for
            analysis: The analysis to use for looking up qualified names
        Returns:
            The fully qualified name for the given analysis object
        """
        symbol = Symbol.construct(cls.get_annotated_node(analysis_object))
        fully_qualified_class_name = str(analysis.get_qualified_name_from_map(symbol))
        return fully_qualified_class_name

    @classmethod
    def get_fully_qualified_cpp_name(cls, analysis_object, analysis: Analysis) -> str:
        """ Get the fully qualified C++ class name for a given type object
        
        This method uses the analysis to get the fully qualified name for the given type object and then converts it
        to a C++-style name by replacing FPP's "." with C++'s "::".

        Args:
            analysis_object: The analysis object to get the fully qualified name for
            analysis: The analysis to use for looking up qualified names
        Returns:
            The fully qualified C++ class name for the given type object
        """
        return cls.get_fully_qualified_name(analysis_object, analysis).replace(".", "::")


class CodeGenerator(ABC):
    """ Abstract base class for generating code for FPP from the FPP
    
    This class supplies core functionality for generating code from FPP constructs. It serves as a base for the binding
    generators and implementation generators.
    """
    def __init__(self, include_manager: IncludeManager):
        """ Initialize the generator with an include manager"""
        super().__init__()
        self.include_manager = include_manager

    def get_annotated_node(self, analysis_object):
        """ Get the annotated node for a given analysis object
        
        In some cases, an object may have a .node property that points to the AST node, but in other cases, the AST node
        may be stored in the .a_node property. This method abstracts away this difference and returns the annotated node
        for a given analysis object.

        Caution: prefer the DataHelper.get_annotated_node method instead of this one.
        
        Args:
            analysis_object: The analysis object to get the annotated node for
        Returns:
            The annotated node for the given analysis object
        """
        return DataHelper.get_annotated_node(analysis_object)

    def get_fully_qualified_cpp_name(self, type_object: Type, in_: In) -> str:
        """ Get the fully qualified C++ class name for a given type object
        
        This method uses the analysis to get the fully qualified name for the given type object and then converts it
        to a C++-style name by replacing "." with "::".

        Args:
            type_object: The type object from the analysis' type map to generate lines for
            in_: input support tuple
        Returns:
            The fully qualified C++ class name for the given type object
        """
        full_analysis, *_ = in_
        return DataHelper.get_fully_qualified_cpp_name(type_object, full_analysis)

    def get_unqualified_name(self, type_object: Type, _: In) -> str:
        """ Get the unqualified name for a given type object
        
        This method uses a symbol to get the unqualified name for the given type object.

        Caution: prefer the DataHelper.get_annotated_node method instead of this one.

        Args:
            type_object: The type object from the analysis' type map to generate lines for
            in_: input support tuple
        Returns:
            The unqualified name for the given type object
        """
        return DataHelper.get_unqualified_name(type_object)
    
    @staticmethod
    def indent(lines: List[str], indent_level: int = 1) -> List[str]:
        """ Indent a list of lines by a given indent level
        
        This function will take the standard indentation string, multiply it by the indent level and then prepend it
        to each of the provide lines.

        Args:
            lines: The lines to indent
            indent_level: The level of indentation to apply
        Returns:
            The list of lines with the appropriate indentation applied
        """
        indent_str = STANDARD_INDENT * indent_level
        return [f"{indent_str}{line}" for line in lines]


INIT_FUNCTION_PROTOTYPE_LINES_TEMPLATE = """
// Autogenerated by fprime-python. Do not edit manually.
#ifndef FPRIME_PYTHON_{fqn_with_underscores}_HPP
#define FPRIME_PYTHON_{fqn_with_underscores}_HPP
{include_block}

//! \\brief bind {fqn} into Python
//!
//! This function initializes the Python bindings for the FPP type {fqn}. It should be called
//! from within the pybind11 module initialization macro at top level.
//!
//! One language to rule them all, one language to find them...
//!
//! \\param m The pybind11 module to bind the type into
void init_{fqn_with_underscores}(pybind11::module_& m);
#endif // FPRIME_PYTHON_{fqn_with_underscores}_HPP
"""

INIT_FUNCTION_TEMPLATE = """
{include_block}
// Autogenerated by fprime-python. Do not edit manually.
// ...and in the darkness bind them ({fqn})
void init_{fqn_with_underscores}(pybind11::module_& m) {{
{STANDARD_INDENT}{class_definition}
}}
"""

INIT_FUNCTION_INVOCATION_TEMPLATE = "(void) init_{fqn_with_underscores}(fprime_{parent_fqn_with_underscores});"

class FppPybindBindingGenerator(CodeGenerator):
    """ Abstract base class for FPP type pybind11 C++ generators
    
    This abstract base class defines the interface and common wrapping code for generating pybind11 C++ bindings and it
    additionally provides the functionality of wrapping type-specific binding code in a standard initialization
    function.
    """

    def get_hpp_lines(self, type_object: Type, in_: In) -> List[str]:
        """ Generate the lines for the C++ header file for bindings
        
        These lines consist of a type-specific binding initialization function declaration.

        Args:
            type_object: The type object from the analysis' type map to generate lines for
            in_: input support tuple
        Returns:
            A list of strings representing the lines of C++ header code for the type binding
        """
        fully_qualified_class_name = self.get_fully_qualified_cpp_name(type_object, in_)
        return INIT_FUNCTION_PROTOTYPE_LINES_TEMPLATE.format(
            include_block="\n".join(self.get_hpp_includes(type_object, in_)),
            fqn=fully_qualified_class_name,
            fqn_with_underscores=fully_qualified_class_name.replace("::", "_"),
        ).splitlines()


    def get_cpp_lines(self, type_object: Type, in_: In) -> List[str]:
        """ Generate the lines for the C++ implementation file for a type node
        
        These lines consist of a type-specific binding initialization function wrapping type specific binding code.

        Args:
            type_object: The type object from the analysis' type map to generate lines for
            in_: input support tuple
        Returns:
            A list of strings representing the lines of C++ implementation code for the type binding
        """
        unqualified_class_name = self.get_unqualified_name(type_object, in_)
        fully_qualified_class_name = self.get_fully_qualified_cpp_name(type_object, in_)
        class_definition_lines = self.get_type_lines(type_object, in_)
        binding_header_path = Path(self.include_manager.get_include_path(self.get_annotated_node(type_object))).parent / f"{unqualified_class_name}BindingAc.hpp"
        includes = [f"#include \"{binding_header_path.as_posix()}\""] + self.get_cpp_includes(type_object, in_)
        return INIT_FUNCTION_TEMPLATE.format(
            STANDARD_INDENT=STANDARD_INDENT,
            include_block="\n".join(includes),
            fqn=fully_qualified_class_name,
            fqn_with_underscores=fully_qualified_class_name.replace("::", "_"),
            class_definition=f"\n{STANDARD_INDENT}".join(class_definition_lines)
        ).splitlines()

    def get_init_function_invocation(self, type_object: Type, in_: In) -> Tuple[str, str]:
        """ Generate pair of containing module and invocation line for this type
        
        Returns the invocation statement lines for the initialization function for this type.

        TODO: fix the return type

        Args:
            type_object: The type object from the analysis' type map to generate lines for
            in_: input support tuple
        Returns:
            A tuple of the containing module and a list of strings representing the lines of C++ code
        """
        fully_qualified_class_name = self.get_fully_qualified_cpp_name(type_object, in_)
        fqn_with_underscores = str(fully_qualified_class_name).replace("::", "_")
        fqn_of_parent = ".".join(str(fully_qualified_class_name).split("::")[:-1])
        return json.dumps({fqn_of_parent: INIT_FUNCTION_INVOCATION_TEMPLATE.format(
            fqn_with_underscores=fqn_with_underscores,
            parent_fqn_with_underscores=fqn_of_parent.replace(".", "_")
        )}).splitlines()

    def get_hpp_includes(self, _: Type, __: In) -> List[str]:
        """ Get any includes required by the HPP file """
        return ["#include \"fprime-python/fprime-python.hpp\""]
    
    def get_cpp_includes(self, type_object: Type, _: In) -> List[str]:
        """ Get any includes required by the CPP file """
        return ["#include \"{}\"".format(self.include_manager.get_include_path(self.get_annotated_node(type_object)))]

    DEF_TEMPLATE = """.def("{name}", {optional_cast}&{fqn}::{name}{optional_cast_end})"""
    def standard_def(self, name: str, fqn: str, disambiguation_cast: str = "") -> str:
        """ Get a standard 'def' binding for a function
        
        This method generates a standard pybind11 definition for a function, given the function name, and the fully
        qualified name of the class it belongs to. If provided, the disambiguation cast allows a user to disambiguate
        between overloaded functions.

        Args:
            name: The name of the function to generate in python
            fqn: The fully qualified name of the C++ class the function belongs to
            disambiguation_cast: Optional static_cast type to apply to the function pointer to select between overloads
        """
        return self.DEF_TEMPLATE.format(
            name=name,
            fqn=fqn,
            optional_cast=f"static_cast<{disambiguation_cast}>(" if disambiguation_cast else "",
            optional_cast_end=")" if disambiguation_cast else ""
        )

    @abstractmethod
    def get_type_lines(self, struct_type: Type, in_: In) -> List[str]:
        """ Generate lines for a specific type
        
        This method should be implemented by subclasses to generate the lines required for a specific type. These lines
        in turn will be wrapped in a standard initialization function by this superclass.

        Args:
            struct_type: The type object to generate lines for
            in_: input support tuple
        Returns:
            A list of strings representing the lines of C++ code for the type binding
        """
        raise NotImplementedError("Subclasses must implement get_type_lines")
