""" data_helpers.py

A series of helper objects that assist with data manipulation and conversion when alternating between the FPP AST
and Analysis representations.
"""
from typing import List
from fprime_python_model.fpp_ast.fpp_ast import FormalParamKind
from fprime_python_model.semantics.analysis import Analysis
from fprime_python_model.semantics.types_values import StringType
from fprime_python_model.semantics.port_instance import PortInstance, GeneralPortInstance
from fprime_python_model.semantics.symbol import Symbol
from fprime_python_model.semantics.command import Command, CommandNonParam
from fprime_python_model.semantics.tlm_channel import TlmChannel
from fprime_python_model.semantics.event import Event
from fprime_python_model.semantics.param import Param
from .binding_generator import DataHelper


class ObjectDataHelper(DataHelper):
    """ Base class for processing object data """
    def __init__(self, object, analysis: Analysis):
        """ Construct a ObjectDataHelper for the given object """
        self.object = object
        self.analysis = analysis
    
    def __getattribute__(self, name: str):
        """ Get the named attribute first from the helper, then from the wrapped object
        
        ObjectDataHelper are intended to patch holes in the analysis information for a given object. When an
        attribute is accessed, we first consult the helper for information, but fallback to the wrapped object in order
        to allow these objects to function interchangeably.

        Args:
            name: The name of the attribute to access
        Returns:
            The value of the attribute from the helper or the wrapped object
        """
        try:
            return super().__getattribute__(name)
        except AttributeError:
            return self.object.__getattribute__(name)
    
    @property
    def troll(self) -> str:
        """ Get the underlying object

        ...because trolls live *under* the bridge.
        """
        return self.object

    @property
    def unqualified_name(self) -> str:
        """ Get the unqualified name of this parameter """
        return self.get_unqualified_name(self.troll)

    @staticmethod
    def is_a(object, cls) -> bool:
        """ Check if the wrapped object is an instance of the given class """
        return isinstance(getattr(object, "troll", object), cls)


class DataTypeDataHelper(ObjectDataHelper):
    """
    Class used to process data type information. This provides the ability to get the C++ type given the wrapped
    type object.
    """
    @property
    def cpp_type(self) -> str:
        """ Get the C++ type string for this type
        
        This returns the C++ type string for the given type object. If the type object is None, this returns "void". If
        the type object is a string type, this returns "string" as a placeholder because modeled strings are built use
        a variety of C++ types depending on context.

        Returns:
            The C++ type string for this type
        """
        if self.object is None:
            return "void"
        try:
            symbol = Symbol.construct(self.object.node)
            return self.get_fully_qualified_cpp_name(symbol, self.analysis)
        except AttributeError:
            return self.object.get_underlying_type()

class PortDataHelper(ObjectDataHelper):
    """ Helper class for processing port data

    Allows easy access to port type, parameters, and return type. 
    """
    @property
    def type(self):
        """ Get the type of this port """
        return self.object.get_type()

    @property
    def parameters(self):
        """ Get the parameters for this port """
        _, node, _ = self.type.symbol.node
        return [FormalParameterDataHelper(param, self.analysis) for param in node.data.params]

    @property
    def return_type(self):
        """ Get the return_type for this port """
        _, node, _ = self.type.symbol.node
        if node.data.return_type is None:
            return DataTypeDataHelper(None, self.analysis)
        type_definition = self.analysis.type_map[node.data.return_type._id]
        return DataTypeDataHelper(type_definition, self.analysis)

class CommandDataHelper(ObjectDataHelper):
    """ Helper class for processing port data """
    @property
    def parameters(self):
        """ Get the parameters for this port """
        _, node, _ = self.troll.a_node
        return [FormalParameterDataHelper(param, self.analysis) for param in node.data.params]

class FormalParameterDataHelper(ObjectDataHelper):
    """ Helper class for processing formal parameter data """

    @property
    def cpp_type(self) -> str:
        """ Get the C++ type string for this formal parameter """
        _, node, _ = self.object
        base_type = self.type.cpp_type
        const_clause = "const" if not self.type.is_primitive() and node.data.kind == FormalParamKind.VALUE else ""
        reference_clause = "&" if not self.type.is_primitive() or node.data.kind == FormalParamKind.REF else ""
        return f"{const_clause} {base_type}{reference_clause}"

    @property
    def name(self):
        """ Get the name of this formal parameter """
        _, node, _ = self.object
        return node.data.name

    @property
    def type(self):
        """ Get the type of this formal parameter """
        _, node, _ = self.object
        type_definition = self.analysis.type_map[node.data.type_name._id]
        return DataTypeDataHelper(type_definition, self.analysis)

class ComponentParameterDataHelper(ObjectDataHelper):
    """ Helper class for processing component parameter data """
    
    @property
    def type(self):
        """ Get the type of this parameter """
        _, node, _ = self.troll.a_node
        type_definition = self.analysis.type_map[node.data.type_name._id]
        return DataTypeDataHelper(type_definition, self.analysis)

class ComponentDataHelper(ObjectDataHelper):
    """ Helper class for processing component data """
    event_kind_to_severity = {
        "activity high": "ACTIVITY_HI",
        "activity low": "ACTIVITY_LO",
        "diagnostic": "DIAGNOSTIC",
        "warning high": "WARNING_HI",
        "warning low": "WARNING_LO",
        "fatal": "FATAL",
    }

    @classmethod
    def event_to_dispatch_method(cls, event) -> str:
        """ Convert an event record to the name of the log_ method
        
        This method takes an event record and converts it to the name of the log_ method that is used to send the event
        from the component. The method name is derived from the event's severity and unqualified name

        Args:
            event: The event record to convert
        Returns:
            The name of the log_ method for the event
        """
        _, u_node, _ = event.a_node
        severity = cls.event_kind_to_severity[u_node.data.severity.value]
        event_name = cls.get_unqualified_name(event)
        return f"log_{severity}_{event_name}"
    
    def get_ports(self, kind_filter: str="", type_filter: type=PortInstance) -> List[GeneralPortInstance]:
        """ Return the ports matching the kind filter and type filter
        
        This will take the set of all ports and filter them down to those that match the kind and type filters. The
        kind filter performs a substring inclusion match, and defaults to "", or match all. The type filter performs an
        instanceof check and defaults to all PortInstance objects.

        Args:
            kind_filter: A substring to match against the port kind
            type_filter: A type to filter the ports by
        Returns:
            A list of ports matching the filters
        """
        return [
            port for port in self.ports
            if kind_filter in str(port.a_node[1].data.kind.value) and ObjectDataHelper.is_a(port, type_filter)
        ]

    @property
    def fqn(self) -> str:
        """ Get the fully qualified name for this component """
        return self.get_fully_qualified_name(self.troll, self.analysis)
    
    @property
    def unqualified_name(self) -> str:
        """ Get the unqualified name for this component """
        return self.get_unqualified_name(self.troll)
    
    @property
    def cpp_fqn(self) -> str:
        """ Get the fully qualified C++ name for this component """
        return self.get_fully_qualified_cpp_name(self.troll, self.analysis)

    @property
    def kind(self) -> str:
        """ Get the kind of this component """
        return self.troll.a_node[1].data.kind.value

    @property
    def events(self) -> List[Event]:
        """ Return the event objects for this component """
        return list(self.troll.event_map.values())
    
    @property
    def commands(self) -> List[Command]:
        """ Return the command objects for this component """
        return [CommandDataHelper(command, self.analysis) for command in self.troll.command_map.values() if ObjectDataHelper.is_a(command, CommandNonParam)]
    
    @property
    def parameters(self) -> List[Param]:
        """ Return the parameter objects for this component """
        return [ComponentParameterDataHelper(param, self.analysis) for param in self.troll.param_map.values()]

    @property
    def channels(self) -> List[TlmChannel]:
        """ Return the telemetry channel objects for this component """
        return list(self.troll.tlm_channel_map.values())
    
    @property
    def ports(self) -> List[GeneralPortInstance]:
        """ Return the port objects for this component """
        return [PortDataHelper(port, self.analysis) for port in self.troll.port_map.values()]
    
    @property
    def general_ports(self) -> List[GeneralPortInstance]:
        """ Return the general port objects for this component """
        return [port for port in self.ports if isinstance(port, GeneralPortInstance)]
    
    @property
    def special_ports(self) -> List[GeneralPortInstance]:
        """ Return the special port objects for this component """
        return [port for port in self.ports if not isinstance(port, GeneralPortInstance)]