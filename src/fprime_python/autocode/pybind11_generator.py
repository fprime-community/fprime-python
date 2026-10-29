""" fprime_python.pybind11_generator:

Generates the pybind11 module initialization for a deployment.

Every binding this autocoder generates for a module leaves behind a JSON snippet naming the submodule it
belongs to and the call that installs it. This file collects those snippets across a whole deployment,
declares the submodule tree they imply, and calls each of them in turn from the one `PYBIND11_MODULE`
block that makes the deployment importable from Python.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Iterator, List

from fprime_cpp_codegen import Body, CppDocBuilder, Output, wrap_in_scope

from .constants import MODULE_NAME, MODULE_VARIABLE_PREFIX, SUPPORT_HEADER, TOOL_NAME
from .names import flat_name

#: User defined function name for deployment binding
DEPLOYMENT_BINDING_FUNCTION_NAME = "setup_user_deployment"

#: Base name of the generated file
INIT_FILE_BASE = "fprime_init"

#: Submodules that always exist, holding the F Prime types and OSAL that live outside the FPP model
STANDARD_MODULES = ["Fw", "Os"]

#: Calls that bind the parts of F Prime that are not modeled in FPP
STANDARD_MODULE_BINDINGS = [
    "Fw::bind_types({prefix}Fw);",
    "Os::bind_osal({prefix}Os);",
]

#: Declaration of one pybind11 submodule, as a variable named after the FPP scope it stands for
SUBMODULE_TEMPLATE = (
    'auto {prefix}{flat_name} = {prefix}{flat_parent}.def_submodule("{name}",'
    ' "TODO: add doc strings");'
)


def read_and_merge(files: Iterable[Path]) -> Dict[str, List[str]]:
    """ Read and merge multiple JSON dictionaries into one

    Args:
        files: The per-definition invocation snippets to merge
    Returns:
        A mapping of FPP scope to every invocation belonging to that scope
    """
    merged: Dict[str, List[str]] = {}
    for file in files:
        with open(file, "r", encoding="utf-8") as file_handle:
            for key, value in json.load(file_handle).items():
                merged[key] = merged.get(key, []) + [value]
    return merged


def all_modules(scopes: Iterable[str]) -> Iterator[str]:
    """ Yield every FPP scope that needs a pybind11 submodule

    Only the scopes that directly hold a binding are passed in, so the enclosing scopes are derived by
    splitting each one. The standard modules are always yielded because they are bound by hand rather
    than from the model.

    Args:
        scopes: The FPP scopes that hold at least one binding
    Yields:
        Every scope needing a submodule, with repeats
    """
    yield from STANDARD_MODULES
    for scope in scopes:
        parts = []
        for part in scope.split("."):
            parts.append(part)
            yield ".".join(parts)


def render_module_file(files: List[Path], headers: List[Path]) -> str:
    """ Generate the module initialization file

    Args:
        files: The per-definition invocation snippets to install
        headers: The generated binding headers declaring the initialization functions
    Returns:
        The contents of the generated module initialization file
    """
    invocations = read_and_merge(files)

    # The module is loaded by the interpreter rather than called from other C++, so there is no
    # declaration to make and the document is source-only
    doc = CppDocBuilder(
        INIT_FILE_BASE,
        description=f"the {MODULE_NAME} Python module",
        tool_name=TOOL_NAME,
        emit_hpp=False,
    )
    doc.include(*[str(header) for header in headers], SUPPORT_HEADER, output=Output.CPP)

    body = Body()
    body.line(f'{MODULE_VARIABLE_PREFIX}.doc() = "F´ Python Bindings Module";')
    # Sorting puts a scope after the scopes enclosing it, so a submodule's parent always exists by the
    # time it is declared
    for module in sorted({module for module in all_modules(invocations) if module}):
        body.line(
            SUBMODULE_TEMPLATE.format(
                prefix=MODULE_VARIABLE_PREFIX,
                flat_name=flat_name(module),
                flat_parent=flat_name(module.rpartition(".")[0]),
                name=module.rpartition(".")[2],
            )
        )
    for binding in STANDARD_MODULE_BINDINGS:
        body.line(binding.format(prefix=MODULE_VARIABLE_PREFIX))
    for scope in sorted(invocations):
        for invocation in invocations[scope]:
            body.line(invocation)
    body.line(f"{DEPLOYMENT_BINDING_FUNCTION_NAME}({MODULE_VARIABLE_PREFIX});")

    doc.raw(
        wrap_in_scope(
            f"\nPYBIND11_MODULE({MODULE_NAME}, {MODULE_VARIABLE_PREFIX}) {{",
            body.build(),
            "}",
        ),
        output=Output.CPP,
    )
    return doc.render_cpp()
