""" fprime_python.binding_generator: generates the pybind11 bindings for FPP constructs

Bindings have several components:

1. An initialization function that attaches to a supplied module
2. A header file that declares the initialization function
3. A snippet of code that can be used to call the initialization function

This file provides the base generator for those components. Generators for specific kinds of definition
inherit from it and supply only the pybind11 statements that bind their own definition; the base class
wraps those in the initialization function, declares it, and records how to call it.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Dict, Iterable, List

import fpp
from fprime_cpp_codegen import Body, CppDocBuilder, Line, Output, line, lines
from fprime_cpp_codegen.lines import add_suffix, indent_lines

from .constants import MODULE_VARIABLE_PREFIX, SUPPORT_HEADER, TOOL_NAME
from .include import IncludeManager
from .names import cpp_name, flat_name, scope_of


#: Doc comment placed on every generated initialization function
INIT_FUNCTION_COMMENT = """\\brief bind {fqn} into Python

This function initializes the Python bindings for the FPP type {fqn}. It should be called
from within the pybind11 module initialization macro at top level.

One language to rule them all, one language to find them...

\\param m The pybind11 module to bind the type into"""

#: Comment placed above every generated initialization function's definition
INIT_FUNCTION_DEFINITION_COMMENT = "\n// ...and in the darkness bind them ({fqn})"


def expression_chain(head: str, links: Iterable[str]) -> List[Line]:
    """ Render a chained C++ expression as lines, one link per line, terminated with a semicolon

    A pybind11 binding is one long chained expression: the class is constructed and then each binding is
    another `.def(...)` applied to the result. Links are emitted verbatim, so a link may span lines --
    one taking a C++ lambda usually does -- and keeps its own relative indentation.

    Args:
        head: The expression the chain starts from
        links: The chained calls, each of which may span lines
    Returns:
        The rendered lines, with the statement's semicolon attached to the last of them
    """
    rendered = [line(head)]
    for link in links:
        rendered += indent_lines([line(text) for text in link.split("\n")], 4)
    return add_suffix(rendered, ";")


def standard_def(name: str, fqn: str) -> str:
    """ Get a standard 'def' binding for a member function

    This generates a standard pybind11 definition for a member function, given the function name and the
    fully qualified name of the class it belongs to. The Python name is the C++ one.

    Args:
        name: The name of the function, in C++ and in Python
        fqn: The fully qualified C++ name of the class the function belongs to
    Returns:
        The pybind11 `.def(...)` call
    """
    return f'.def("{name}", &{fqn}::{name})'


class BindingGenerator(ABC):
    """ Base class for generating the pybind11 binding of one FPP definition

    A binding is three files: a C++ source defining an initialization function that attaches the
    definition to a pybind11 module, a header declaring that function so the module initialization can
    call it, and a JSON snippet recording the call it needs to make. This class produces all three
    around the pybind11 statements that `bind` writes.
    """

    #: Suffix of the generated C++ file pair, e.g. PyActiveBindingAc.hpp
    FILE_BASE_SUFFIX = "BindingAc"

    #: Suffix of the generated invocation snippet, e.g. PyActiveBinding.json
    INVOCATION_SUFFIX = "Binding"

    def __init__(self, include_manager: IncludeManager, symbol: fpp.Symbol.Variant) -> None:
        """ Initialize the generator for one definition

        Args:
            include_manager: Resolves the include paths of the headers the binding needs
            symbol: The symbol of the definition being bound
        """
        self.include_manager = include_manager
        self.symbol = symbol

    @property
    def name(self) -> str:
        """ The definition's unqualified name """
        return self.symbol.unqualified_name

    @property
    def fpp_name(self) -> str:
        """ The definition's FPP-qualified name """
        return self.symbol.qualified_name

    @property
    def cpp_fqn(self) -> str:
        """ The definition's C++-qualified name """
        return cpp_name(self.fpp_name)

    @property
    def init_function_name(self) -> str:
        """ The name of the generated initialization function

        The function is declared at global scope so that the module initialization can call every one of
        them without opening namespaces, so the definition's qualified name is flattened into it.
        """
        return f"init_{flat_name(self.fpp_name)}"

    @property
    def file_base(self) -> str:
        """ The base name of the generated C++ file pair """
        return f"{self.name}{self.FILE_BASE_SUFFIX}"

    @property
    def include_guard(self) -> str:
        """ The include guard of the generated header """
        return f"FPRIME_PYTHON_{flat_name(self.fpp_name)}_HPP"

    @abstractmethod
    def bind(self, body: Body) -> None:
        """ Write the pybind11 statements that bind this definition into the module `m`

        Args:
            body: The body of the initialization function to write the statements into
        """

    def hpp_includes(self) -> List[str]:
        """ Headers the generated header needs """
        return [SUPPORT_HEADER]

    def cpp_includes(self) -> List[str]:
        """ Headers the generated source needs, its own header first """
        return [
            self.include_manager.get_sibling_path(self.symbol, f"{self.file_base}.hpp"),
            self.include_manager.get_include_path(self.symbol),
        ]

    def cpp_system_includes(self) -> List[str]:
        """ System headers the generated source needs """
        return []

    def cpp_preamble(self, doc: CppDocBuilder) -> None:
        """ Write anything the generated source needs at namespace scope before the binding function

        Args:
            doc: The document being built
        """

    def document(self) -> CppDocBuilder:
        """ Build the C++ document holding the binding's header and source

        Returns:
            The document, with the initialization function declared and defined
        """
        doc = CppDocBuilder(
            self.file_base,
            description=f"{self.name} Python bindings",
            include_guard=self.include_guard,
            tool_name=TOOL_NAME,
            strict=True,
        )
        doc.include(*self.hpp_includes())
        doc.include(*self.cpp_includes(), output=Output.CPP)
        doc.system_include(*self.cpp_system_includes(), output=Output.CPP)
        self.cpp_preamble(doc)
        doc.lines(
            INIT_FUNCTION_DEFINITION_COMMENT.format(fqn=self.cpp_fqn),
            margin=None,
            output=Output.CPP,
        )
        function = doc.function(
            self.init_function_name,
            params=[("pybind11::module_&", "m")],
            comment=lines(INIT_FUNCTION_COMMENT.format(fqn=self.cpp_fqn), margin=None),
        )
        self.bind(function.body)
        return doc

    def invocation(self) -> Dict[str, str]:
        """ The call the module initialization has to make to bind this definition

        Returns:
            A mapping of the FPP scope the definition lives in to the statement invoking its
            initialization function against that scope's pybind11 submodule
        """
        scope = scope_of(self.fpp_name)
        submodule_variable = f"{MODULE_VARIABLE_PREFIX}{flat_name(scope)}"
        return {scope: f"(void) {self.init_function_name}({submodule_variable});"}

    def files(self) -> Dict[str, str]:
        """ Generate the binding's files

        Returns:
            A mapping of file name to file contents
        """
        return {
            **self.document().files(),
            f"{self.name}{self.INVOCATION_SUFFIX}.json": json.dumps(self.invocation()),
        }
