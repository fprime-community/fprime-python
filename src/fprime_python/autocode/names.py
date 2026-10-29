""" fprime_python.names:

Conversions between the naming conventions that FPP, C++ and pybind11 each use.

FPP qualifies names with ".", C++ with "::", and the generated initialization functions and pybind11
submodule variables flatten either separator to "_" because they live at global scope.
"""
from __future__ import annotations

from typing import List


def cpp_name(qualified_name: str) -> str:
    """ Convert an FPP qualified name to its C++ spelling

    Args:
        qualified_name: FPP-qualified name, e.g. "Ref.PyActive"
    Returns:
        The C++ spelling of that name, e.g. "Ref::PyActive"
    """
    return qualified_name.replace(".", "::")


def flat_name(qualified_name: str) -> str:
    """ Flatten a qualified name into a single C++ identifier

    Both the FPP "." and the C++ "::" separator become "_", so either spelling may be passed in. This
    names the per-definition initialization functions and the pybind11 submodule variables, both of
    which are declared at global scope and so cannot carry a namespace.

    Args:
        qualified_name: FPP- or C++-qualified name
    Returns:
        The name as a single identifier, e.g. "Ref_PyActive"
    """
    return qualified_name.replace("::", "_").replace(".", "_")


def scope_of(qualified_name: str) -> str:
    """ The FPP-qualified name of the scope enclosing a qualified name

    Args:
        qualified_name: FPP-qualified name, e.g. "Ref.PyActive"
    Returns:
        The enclosing scope, e.g. "Ref", or "" for a name at the top level
    """
    return qualified_name.rpartition(".")[0]


def namespaces_of(qualified_name: str) -> List[str]:
    """ The C++ namespaces enclosing a qualified name, outermost first

    Args:
        qualified_name: FPP-qualified name, e.g. "Ref.Inner.PyActive"
    Returns:
        The enclosing namespaces, e.g. ["Ref", "Inner"], or [] for a name at the top level
    """
    scope = scope_of(qualified_name)
    return scope.split(".") if scope else []
