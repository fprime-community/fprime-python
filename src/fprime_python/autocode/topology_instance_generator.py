""" fprime_python.topology_instance_generator:

Generates the pybind11 bindings for an FPP topology.

Binding a topology gives Python two things: the setup and teardown functions that bring the topology up
and down, and a handle on every component instance whose component is implemented in Python, so that a
Python caller can reach the running instances as though they were module-level objects.
"""
from __future__ import annotations

import json
from typing import Iterable, List

import fpp
from fprime_cpp_codegen import Body, CppDocBuilder, Output

from .binding_generator import BindingGenerator, expression_chain
from .constants import FPRIME_PYTHON_ANNOTATION, SELF_MEMBER
from .include import IncludeManager
from .names import cpp_name
from .view import TopologyView


#: Name of the struct the bound instances hang off, and of the Python class it becomes
INSTANCES_STRUCT = "FprimePythonInstances"
INSTANCES_CLASS = "Instances"

#: Docstring of the generated setup and teardown bindings
TOPOLOGY_FUNCTION_DOCSTRING = """Topology {action} function for {fqn} topology

This function will perform the {action} of the {fqn} topology, running through all the defined phases.

Args:
    state: The state object to use for the topology {action} (user defined, user bound)
Returns:
    None. Does not block"""

#: Binding of one topology setup or teardown function. The GIL is released for the call because the
#: topology's tasks call back into Python and would otherwise deadlock against the caller.
TOPOLOGY_FUNCTION_TEMPLATE = """m.def("{action}", &{namespace}::{action},
{docstring},
    pybind11::arg("state"), pybind11::call_guard<pybind11::gil_scoped_release>());"""

#: Read-only accessor for one bound component instance. The instance exists for the whole life of the
#: process but only mirrors a Python object once the topology has initialized it.
INSTANCE_TEMPLATE = """.def_property_readonly_static("{name}",
    [](pybind11::object /* cls */) {{
        if ({qualified_name}.{self_member}) {{
            return {qualified_name}.{self_member};
        }}
        throw std::runtime_error("Instance {qualified_name} is not initialized");
    }},
    "Instance binding {qualified_name}")"""


def cpp_string_literal(text: str) -> List[str]:
    """ Render text as a sequence of C++ string literals, one per line of text

    Adjacent C++ string literals concatenate, so splitting the text a line at a time keeps the text's own
    indentation independent of the indentation of the C++ around it. That matters here because the text
    becomes a Python docstring, which a C++ raw string literal would indent along with its surroundings.

    Args:
        text: The text to render
    Returns:
        One C++ string literal per line of the text, each ending in an escaped newline
    """
    # json escaping produces a double-quoted string whose escapes C++ also understands
    return [json.dumps(f"{text_line}\n") for text_line in text.split("\n")]


def namespace_block(namespaces: Iterable[str], interior: Iterable[str]) -> List[str]:
    """ Wrap lines of C++ in a nest of namespace blocks

    Args:
        namespaces: The namespaces to wrap the interior in, outermost first
        interior: The lines to wrap
    Returns:
        The wrapped lines
    """
    wrapped = list(interior)
    for namespace in reversed(list(namespaces)):
        wrapped = (
            [f"namespace {namespace} {{"]
            + [f"  {wrapped_line}" for wrapped_line in wrapped]
            + [f"}}  // namespace {namespace}"]
        )
    return wrapped


class TopologyBindingGenerator(BindingGenerator):
    """ Generator for topology bindings into Python

    This generator lets bound components be reached and used as attributes of the topology module in
    Python, and exposes the topology's own setup and teardown.
    """

    def __init__(
        self, include_manager: IncludeManager, symbol: fpp.Symbol.Variant, topology: fpp.Topology
    ) -> None:
        """ Initialize the generator for one topology

        Args:
            include_manager: Resolves the include paths of the headers the binding needs
            symbol: The symbol of the topology being bound
            topology: The analyzed topology being bound
        """
        super().__init__(include_manager, symbol)
        self.topology = TopologyView(topology)

    def bind(self, body: Body) -> None:
        """ Write the pybind11 statements binding this topology """
        body.comment("Bind the topology interface functions")
        for action in ("setup", "teardown"):
            docstring = TOPOLOGY_FUNCTION_DOCSTRING.format(
                action=action, fqn=self.topology.cpp_name
            )
            # The docstring is model-derived, so this is not margin-stripped
            body.lines(
                TOPOLOGY_FUNCTION_TEMPLATE.format(
                    action=action,
                    namespace=self.topology.cpp_namespace,
                    docstring="\n".join(
                        f"    {literal}" for literal in cpp_string_literal(docstring)
                    ),
                ),
                margin=None,
            )
        body.blank()
        body.comment(
            f"Bind each @{FPRIME_PYTHON_ANNOTATION} instance to Python under the"
            f" {INSTANCES_CLASS} struct"
        )
        instances = self.topology.bound_instances(FPRIME_PYTHON_ANNOTATION)
        body.raw(
            expression_chain(
                f'pybind11::class_<{self.topology.cpp_namespace}::{INSTANCES_STRUCT}>'
                f'(m, "{INSTANCES_CLASS}")',
                [
                    INSTANCE_TEMPLATE.format(
                        name=instance.unqualified_name,
                        qualified_name=cpp_name(instance.qualified_name),
                        self_member=SELF_MEMBER,
                    )
                    for instance in instances
                ],
            )
        )

    def cpp_preamble(self, doc: CppDocBuilder) -> None:
        """ Declare the struct the bound instances hang off

        pybind11 attaches static properties to a class, so the instances need a type to belong to. It has
        no members of its own and is declared in the source rather than the header so that two topologies
        in one namespace do not declare it twice in the same translation unit.
        """
        # The namespace names come from the model, so this is not margin-stripped
        doc.lines(
            "\n".join(
                ["", "// Empty struct the instance bindings hang off"]
                + namespace_block(
                    self.topology.namespaces, [f"struct {INSTANCES_STRUCT} {{}};"]
                )
            ),
            margin=None,
            output=Output.CPP,
        )

    def cpp_system_includes(self) -> List[str]:
        """ Get any system includes required by this generator """
        # std::runtime_error, thrown when an instance is read before the topology has initialized it
        return ["stdexcept"]
