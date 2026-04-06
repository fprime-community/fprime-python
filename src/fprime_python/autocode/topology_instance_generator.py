""" component_generator.py

Provides the generation of pybind11 bindings for FPP components.
"""
import itertools
from typing import List, Tuple, Type, TypeAlias

from fprime_python_model.semantics.analysis import Analysis
from fprime_python_model.semantics.topology import Topology
from fprime_python_model.semantics.interface_instance import InterfaceComponentInstance

from .constants import FPRIME_PYTHON_ANNOTATION
from .binding_generator import STANDARD_INDENT, FppPybindBindingGenerator, namespace_recurse

In: TypeAlias = Tuple[Analysis, ...]

INSTANCES_TEMPLATE_LINES = """
pybind11::class_<{namespace_name}::FprimePythonInstances>(m, "Instances")
{STANDARD_INDENT}{instance_lines};
"""

INSTANCE_TEMPLATE_LINES = """
{STANDARD_INDENT}.def_property_readonly_static("{unqualified_instance_name}",
{STANDARD_INDENT}{STANDARD_INDENT}[](pybind11::object /* cls */) {{
{STANDARD_INDENT}{STANDARD_INDENT}{STANDARD_INDENT}if ({qualified_instance_name}.m_self) {{
{STANDARD_INDENT}{STANDARD_INDENT}{STANDARD_INDENT}{STANDARD_INDENT}return *{qualified_instance_name}.m_self;
{STANDARD_INDENT}{STANDARD_INDENT}{STANDARD_INDENT}}}
{STANDARD_INDENT}{STANDARD_INDENT}{STANDARD_INDENT}throw std::runtime_error("Instance {qualified_instance_name} is not initialized");
{STANDARD_INDENT}{STANDARD_INDENT}}},
{STANDARD_INDENT}{STANDARD_INDENT}"Instance binding {qualified_instance_name}"
{STANDARD_INDENT})
""".strip()

class TopologyInstancePybindGenerator(FppPybindBindingGenerator):
    """Generator for topology instances in fprime-python

    This generator allows bound components to be referenced and used as global variables in python. 
    """
    @staticmethod
    def get_python_instances(topology: Topology) -> List[InterfaceComponentInstance]:
        """ Filter the instances in the topology to those that are annotated for fprime-python

        This will look through the instances in the topology, filtered to components, and then list those that are
        annotated for use with fprime-python.

        Args:
            topology: The topology to get the instances from
        Returns:
            A list of component instances that are annotated for fprime-python
        """
        instances = []
        topology_instances = topology.instance_map.keys()
        for topology_instance in [instance for instance in topology_instances if isinstance(instance, InterfaceComponentInstance)]:            
            component = topology_instance.ci.component
            full_annotation = component.a_node[0] + component.a_node[2]
            if FPRIME_PYTHON_ANNOTATION not in [line.strip() for line in full_annotation]:
                continue
            instances.append(topology_instance)
        return instances

    def get_type_lines(self, topology: Topology, in_: In) -> List[str]:
        """ Get the lines of code topology bindings """
        instances = self.get_python_instances(topology)
        topology_namespace = "::".join(str(topology.get_qualified_name()).split(".")[:-1])
        base_lines = [
            INSTANCE_TEMPLATE_LINES.format(
                unqualified_instance_name=instance.get_unqualified_name(),
                qualified_instance_name=str(instance.get_qualified_name()).replace(".", "::"),
                STANDARD_INDENT=STANDARD_INDENT
            ).splitlines()
            for instance in instances 
        ]
        return INSTANCES_TEMPLATE_LINES.format(
            namespace_name=topology_namespace,
            instance_lines="\n".join(itertools.chain.from_iterable(base_lines)),
            STANDARD_INDENT=STANDARD_INDENT
        ).splitlines()
    
    def get_cpp_includes(self, type_object: Type, _: In) -> List[str]:
        """ Override include paths"""
        base_include_paths = super().get_cpp_includes(type_object, _)

        # Add a struct called FprimePythonInstances in the same namespace as the topology
        topology_namespaces = str(type_object.get_qualified_name()).split(".")[:-1]
        full_include_paths = base_include_paths + [
            "// Empty struct to appease bindings",
        ] + namespace_recurse(topology_namespaces, ["struct FprimePythonInstances {};"])
        return full_include_paths
    
