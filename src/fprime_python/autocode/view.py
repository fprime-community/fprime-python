""" fprime_python.view:

Ordered, generation-facing views over the analyzed FPP model.

fpp iterates a component's ports, commands, events, channels and parameters in key order -- ports by
name, and the id-keyed maps by id -- which is the order F Prime's own autocoder emits them in, so these
views walk the maps as they come. What the views add is the derived C++ and Python names -- handler
names, `log_<SEVERITY>_<EVENT>`, `tlmWrite_<CHANNEL>` and so on -- so that every generator agrees on
them, and the checks that reject a model this autocoder cannot bind.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Sequence, Tuple

import fpp

from .constants import FPRIME_PYTHON_ANNOTATION
from .cpp_types import StringClass, formal_parameter_type, type_name, value_type
from .names import cpp_name, namespaces_of


#: The C++ token F Prime builds a `log_` method name from, per FPP event severity
EVENT_SEVERITY_TOKENS = {
    fpp.ast.EventSeverity.ActivityHigh: "ACTIVITY_HI",
    fpp.ast.EventSeverity.ActivityLow: "ACTIVITY_LO",
    fpp.ast.EventSeverity.Command: "COMMAND",
    fpp.ast.EventSeverity.Diagnostic: "DIAGNOSTIC",
    fpp.ast.EventSeverity.Fatal: "FATAL",
    fpp.ast.EventSeverity.WarningHigh: "WARNING_HI",
    fpp.ast.EventSeverity.WarningLow: "WARNING_LO",
}


def is_annotated(node: fpp.ast.AstNode, annotation: str) -> bool:
    """ Check whether an AST node carries the given annotation

    fpp strips the leading "@" and the surrounding whitespace, so annotations compare as plain text.
    Annotations before and after the definition both count.

    Args:
        node: The AST node whose annotations to search
        annotation: The annotation text to look for
    Returns:
        True when the node carries the annotation
    """
    return annotation in list(node.pre_annotation) + list(node.post_annotation)


class FormalParameterView:
    """ One formal parameter of a port, command or event """

    def __init__(self, param: fpp.ast.FormalParam, string_class: StringClass) -> None:
        """ Wrap a formal parameter, fixing the string class its context calls for """
        self.param = param
        self.string_class = string_class

    @property
    def name(self) -> str:
        """ The parameter's name """
        return self.param.name

    @property
    def cpp_type(self) -> str:
        """ The parameter's C++ type, reference qualifiers included """
        return formal_parameter_type(self.param, self.string_class)


class UnsupportedModelError(Exception):
    """ The model uses a feature this autocoder cannot bind to Python """


class HandlerView(ABC):
    """ One component member that F Prime declares a pure virtual handler for

    A handler's signature is a fixed prefix -- the port number for a general port, the opcode and the
    command sequence number for a command, nothing for an internal port -- followed by the member's own
    formal parameters. The generated C++ override, the call it forwards into Python, and the stub in the
    Python template all have to agree on that signature, so it is spelled once here and each generator
    reads it back rather than repeating the prefix.
    """

    #: The handler's fixed leading parameters, as (C++ type, name, doc comment) triples
    HANDLER_PREFIX: Tuple[Tuple[str, str, str], ...] = ()

    #: What the handler handles, as it reads in a generated comment
    HANDLER_KIND: str = ""

    @property
    @abstractmethod
    def name(self) -> str:
        """ The member's name as written in the model """

    @property
    @abstractmethod
    def handler_name(self) -> str:
        """ The name of the handler F Prime declares for this member """

    @property
    @abstractmethod
    def parameters(self) -> List[FormalParameterView]:
        """ The member's own formal parameters, in declaration order """

    @property
    def handler_return_type(self) -> str:
        """ The C++ return type of the handler; only a port can return a value """
        return "void"

    @property
    def handler_parameters(self) -> List[Sequence[str]]:
        """ Every parameter of the handler, prefix first, for a C++ declaration """
        return list(self.HANDLER_PREFIX) + [
            (param.cpp_type, param.name) for param in self.parameters
        ]

    @property
    def handler_arguments(self) -> List[str]:
        """ The names of every handler argument, prefix first, in call order """
        return [name for _, name, _ in self.HANDLER_PREFIX] + [
            param.name for param in self.parameters
        ]


class PortView(HandlerView):
    """ One general port instance of a component """

    HANDLER_PREFIX = (("FwIndexType", "portNum", "The port number"),)
    HANDLER_KIND = "input port"

    def __init__(self, port: fpp.PortInstance.General) -> None:
        """ Wrap a general port instance

        Raises:
            UnsupportedModelError: The port is a serial port, whose handler takes a serialization buffer
        """
        self.port = port
        # A serial port has no port definition to take a signature from: F Prime hands its handler a
        # Fw::LinearBufferBase, which has nothing to map onto in Python. The handler is pure virtual, so
        # skipping it would leave the generated component abstract -- refuse the component instead.
        port_type = port.type
        if not isinstance(port_type, fpp.PortInstanceType.DefPort):
            raise UnsupportedModelError(
                f"port {port.unqualified_name} is a serial port, which fprime-python cannot bind:"
                f" its handler takes a serialization buffer. Give the port a port type to bind it."
            )
        self.type = port_type

    @property
    def name(self) -> str:
        """ The port's name as written in the model """
        return self.port.unqualified_name

    @property
    def is_input(self) -> bool:
        """ Whether this is an input port """
        return self.port.direction == fpp.Direction.Input

    @property
    def handler_name(self) -> str:
        """ The name of the handler F Prime declares for this input port """
        return f"{self.name}_handler"

    @property
    def invoker_name(self) -> str:
        """ The name of the method F Prime declares to invoke this output port """
        return f"{self.name}_out"

    @property
    def connection_check_name(self) -> str:
        """ The name of the method F Prime declares to test this output port's connection """
        return f"isConnected_{self.name}_OutputPort"

    @property
    def definition(self) -> fpp.ast.DefPort:
        """ The port definition this instance is an instance of """
        return self.type.definition

    @property
    def parameters(self) -> List[FormalParameterView]:
        """ The port's formal parameters, in declaration order """
        return [
            FormalParameterView(param, StringClass.PORT) for param in self.definition.params
        ]

    @property
    def handler_return_type(self) -> str:
        """ The C++ return type of the port's handler, "void" when the port returns nothing """
        return_type_name = self.definition.return_type
        resolved = None if return_type_name is None else return_type_name.resolved_type
        return value_type(resolved, StringClass.PORT_RETURN)


class InternalPortView(HandlerView):
    """ One internal port instance of a component

    An internal port is how a component sends work to its own thread: the invoke function queues a message and
    the handler runs it off the queue. Both sides are useful from Python, and the handler is pure virtual, so
    both are generated -- but unlike a general port there is no port number, because there is no connection.
    """

    HANDLER_KIND = "internal port"

    def __init__(self, port: fpp.PortInstance.Internal) -> None:
        """ Wrap an internal port instance """
        self.port = port

    @property
    def name(self) -> str:
        """ The port's name as written in the model """
        return self.port.unqualified_name

    @property
    def handler_name(self) -> str:
        """ The name of the handler F Prime declares for this internal port """
        return f"{self.name}_internalInterfaceHandler"

    @property
    def invoker_name(self) -> str:
        """ The name of the method F Prime declares to invoke this internal port """
        return f"{self.name}_internalInterfaceInvoke"

    @property
    def parameters(self) -> List[FormalParameterView]:
        """ The port's formal parameters, in declaration order """
        return [
            FormalParameterView(param, StringClass.INTERNAL_PORT)
            for param in self.port.node.params
        ]


class CommandView(HandlerView):
    """ One command of a component """

    HANDLER_PREFIX = (
        ("FwOpcodeType", "opCode", "The opcode"),
        ("U32", "cmdSeq", "The command sequence number"),
    )
    HANDLER_KIND = "command"

    def __init__(self, command: fpp.Command.NonParam) -> None:
        """ Wrap a command """
        self.command = command

    @property
    def name(self) -> str:
        """ The command's name """
        return self.command.name

    @property
    def handler_name(self) -> str:
        """ The name of the handler F Prime declares for this command """
        return f"{self.name}_cmdHandler"

    @property
    def parameters(self) -> List[FormalParameterView]:
        """ The command's formal parameters, in declaration order """
        return [
            FormalParameterView(param, StringClass.COMMAND) for param in self.command.node.params
        ]


class EventView:
    """ One event of a component """

    def __init__(self, event: fpp.Event) -> None:
        """ Wrap an event """
        self.event = event

    @property
    def name(self) -> str:
        """ The event's name """
        return self.event.name

    @property
    def severity_token(self) -> str:
        """ The C++ severity token F Prime builds this event's method name from """
        severity = self.event.node.severity
        try:
            return EVENT_SEVERITY_TOKENS[severity]
        except KeyError:
            raise UnsupportedModelError(
                f"Unsupported event severity {severity} on event {self.name}"
            ) from None

    @property
    def dispatch_name(self) -> str:
        """ The name of the method F Prime declares to send this event """
        return f"log_{self.severity_token}_{self.name}"


class ChannelView:
    """ One telemetry channel of a component """

    def __init__(self, channel: fpp.TlmChannel) -> None:
        """ Wrap a telemetry channel """
        self.channel = channel

    @property
    def name(self) -> str:
        """ The channel's name """
        return self.channel.name

    @property
    def write_name(self) -> str:
        """ The name of the method F Prime declares to write this channel """
        return f"tlmWrite_{self.name}"


class ParameterView:
    """ One parameter of a component """

    def __init__(self, param: fpp.Param) -> None:
        """ Wrap a parameter """
        self.param = param

    @property
    def name(self) -> str:
        """ The parameter's name """
        return self.param.name

    @property
    def cpp_type(self) -> str:
        """ The C++ type F Prime's getter for this parameter returns """
        return type_name(self.param.param_type, StringClass.PARAMETER)

    @property
    def getter_name(self) -> str:
        """ The name of the getter F Prime declares for this parameter """
        return f"paramGet_{self.name}"

    @property
    def helper_name(self) -> str:
        """ The name of the generated helper that returns this parameter's value and status together """
        return f"paramGet_{self.name}_helper"


class ComponentView:
    """ One component of the model, with its members in generation order

    F Prime's autocoder declares port handlers in alphabetical order and everything else in id order;
    matching that keeps the generated code readable side by side with the component's base class.
    """

    def __init__(self, component: fpp.Component) -> None:
        """ Wrap a component """
        self.component = component

    @property
    def node(self) -> fpp.ast.DefComponent:
        """ The component's definition node """
        return self.component.node

    @property
    def name(self) -> str:
        """ The component's unqualified name """
        return self.component.symbol.unqualified_name

    @property
    def fpp_name(self) -> str:
        """ The component's FPP-qualified name """
        return self.component.symbol.qualified_name

    @property
    def cpp_name(self) -> str:
        """ The component's C++-qualified name """
        return cpp_name(self.fpp_name)

    @property
    def namespaces(self) -> List[str]:
        """ The C++ namespaces enclosing the component, outermost first """
        return namespaces_of(self.fpp_name)

    @property
    def base_class(self) -> str:
        """ The unqualified name of the F Prime autocoded base class the implementation derives from """
        return f"{self.name}ComponentBase"

    @property
    def is_queued(self) -> bool:
        """ Whether the component is queued, and so dispatches its own messages """
        return self.node.kind == fpp.ast.ComponentKind.Queued

    @property
    def has_queue(self) -> bool:
        """ Whether the component has a message queue, and so takes a queue depth at init """
        return self.node.kind != fpp.ast.ComponentKind.Passive

    @property
    def has_time_port(self) -> bool:
        """ Whether the component can request the current time """
        return fpp.ast.SpecialPortInstanceKind.TimeGet in self.component.special_port_map

    @property
    def has_commands(self) -> bool:
        """ Whether the component has commands, and so can respond to them """
        return bool(self.commands)

    @property
    def has_queue_full_hooks(self) -> bool:
        """ Whether anything on the component declares `hook` queue-full behavior

        `hook` makes F Prime declare a pure virtual overflow hook -- `<port>_overflowHook`,
        `<internal>_overflowHook` or `<cmd>_cmdOverflowHook` -- alongside the handler. Async input ports,
        internal ports and async commands can each ask for one.
        """
        for port in self.component.port_map.values():
            if isinstance(port, fpp.PortInstance.General):
                kind = port.kind
                if (
                    isinstance(kind, fpp.GeneralKind.AsyncInput)
                    and kind.queue_full == fpp.ast.QueueFull.Hook
                ):
                    return True
            elif (
                isinstance(port, fpp.PortInstance.Internal)
                and port.queue_full == fpp.ast.QueueFull.Hook
            ):
                return True
        return any(
            isinstance(command.command.kind, fpp.NonParamKind.Async)
            and command.command.kind.queue_full == fpp.ast.QueueFull.Hook
            for command in self.commands
        )

    def check_supported(self) -> None:
        """ Reject a component whose features this autocoder cannot bind

        F Prime declares a pure virtual handler for every state machine action and guard, for every data
        product container, and for every `hook` queue-full overflow. None has a Python counterpart yet --
        an action takes a state machine id and a signal, a container handler takes a `Fw::DpContainer`, and
        an overflow hook takes the message that could not be queued -- so generating the component anyway
        would leave an abstract class and fail at link time, a long way from the cause.

        Raises:
            UnsupportedModelError: The component has state machine instances, data products or a `hook`
                queue-full declaration
        """
        unsupported = [
            ("state machine instances", self.component.has_state_machine_instances),
            ("data products", self.component.has_data_products),
            ("`hook` queue-full behavior", self.has_queue_full_hooks),
        ]
        for feature, present in unsupported:
            if present:
                raise UnsupportedModelError(
                    f"Component {self.fpp_name} has {feature}, which fprime-python cannot bind: F Prime"
                    f" declares a handler for each of them that has no Python equivalent yet. Remove the"
                    f" @{FPRIME_PYTHON_ANNOTATION} annotation to implement this component in C++ instead."
                )
        # Constructing the port views rejects a serial port
        self._general_ports(inputs=True)

    def _general_ports(self, *, inputs: bool) -> List[PortView]:
        """ The component's general (that is, modeled rather than special) ports of one direction

        Special ports carry the framework's own traffic -- commands, events, telemetry, time and
        parameters -- and are bound through the dedicated methods F Prime generates for them, so only
        general ports get handlers and invocation bindings.

        Args:
            inputs: True to select input ports, False to select output ports
        Returns:
            The matching ports, in name order
        Raises:
            UnsupportedModelError: The component has a port this autocoder cannot bind
        """
        ports = []
        for port in self.component.port_map.values():
            if not isinstance(port, fpp.PortInstance.General):
                continue
            try:
                view = PortView(port)
            except UnsupportedModelError as error:
                raise UnsupportedModelError(f"Component {self.fpp_name}: {error}") from None
            if view.is_input == inputs:
                ports.append(view)
        return ports

    @property
    def input_ports(self) -> List[PortView]:
        """ The component's general input ports, in name order """
        return self._general_ports(inputs=True)

    @property
    def output_ports(self) -> List[PortView]:
        """ The component's general output ports, in name order """
        return self._general_ports(inputs=False)

    @property
    def internal_ports(self) -> List[InternalPortView]:
        """ The component's internal ports, in name order """
        return [
            InternalPortView(port)
            for port in self.component.port_map.values()
            if isinstance(port, fpp.PortInstance.Internal)
        ]

    @property
    def commands(self) -> List[CommandView]:
        """ The component's commands, in opcode order

        A component's command map also holds the pseudo-commands FPP synthesizes to set and save each
        parameter. Those are implemented by the base class and are not handled here, so only the
        commands written in the model are returned.
        """
        return [
            CommandView(command)
            for command in self.component.command_map.values()
            if isinstance(command, fpp.Command.NonParam)
        ]

    @property
    def handlers(self) -> List[HandlerView]:
        """ Every component member F Prime declares a handler for, in generation order

        The three families are generated identically -- an override that forwards into Python, and a stub
        in the Python template -- so the generators walk this one list rather than each family in turn.
        """
        handlers: List[HandlerView] = list(self.input_ports)
        handlers += self.internal_ports
        handlers += self.commands
        return handlers

    @property
    def events(self) -> List[EventView]:
        """ The component's events, in id order """
        return [EventView(event) for event in self.component.event_map.values()]

    @property
    def channels(self) -> List[ChannelView]:
        """ The component's telemetry channels, in id order """
        return [ChannelView(channel) for channel in self.component.tlm_channel_map.values()]

    @property
    def parameters(self) -> List[ParameterView]:
        """ The component's parameters, in id order """
        return [ParameterView(param) for param in self.component.param_map.values()]


class TopologyView:
    """ One topology of the model """

    def __init__(self, topology: fpp.Topology) -> None:
        """ Wrap a topology """
        self.topology = topology

    @property
    def node(self) -> fpp.ast.DefTopology:
        """ The topology's definition node """
        return self.topology.node

    @property
    def name(self) -> str:
        """ The topology's unqualified name """
        return self.topology.unqualified_name

    @property
    def fpp_name(self) -> str:
        """ The topology's FPP-qualified name """
        return self.topology.qualified_name

    @property
    def cpp_name(self) -> str:
        """ The topology's C++-qualified name """
        return cpp_name(self.fpp_name)

    @property
    def namespaces(self) -> List[str]:
        """ The C++ namespaces enclosing the topology, outermost first

        The topology's setup and teardown functions and its component instances all live in this scope.
        """
        return namespaces_of(self.fpp_name)

    @property
    def cpp_namespace(self) -> str:
        """ The C++ namespace enclosing the topology, as a qualifier """
        return "::".join(self.namespaces)

    def check_supported(self) -> None:
        """ Reject a topology this autocoder cannot bind

        The binding calls the topology's setup and teardown functions, and F Prime only generates those for a
        deployment topology. Binding any other kind would produce a source file that names a header F Prime
        never wrote.

        Raises:
            UnsupportedModelError: The topology is not a deployment
        """
        if not self.node.is_deployment:
            raise UnsupportedModelError(
                f"Topology {self.fpp_name} is not a deployment topology, so F Prime generates no setup and"
                f" teardown for it and there is nothing for fprime-python to bind. Declare it"
                f" `deployment topology {self.name}` to bind it."
            )

    def bound_instances(self, annotation: str) -> List[fpp.InterfaceInstance.Component]:
        """ The topology's component instances whose component carries the given annotation

        An instance is bound into Python when the component it instantiates is, so the annotation is
        looked for on the component definition rather than on the instance.

        A topology also instantiates other topologies, which have no component to carry an annotation, and
        an instance may name a port interface rather than a component, in which case there is no component
        definition either, so only instances that resolve to a component are considered.

        Args:
            annotation: The annotation a component must carry for its instances to be bound
        Returns:
            The matching component instances, in name order
        """
        return [
            instance
            for instance in self.topology.instance_map
            if isinstance(instance, fpp.InterfaceInstance.Component)
            and instance.component is not None
            and is_annotated(instance.component.node, annotation)
        ]
