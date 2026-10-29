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
from typing import List, Optional, Sequence, Tuple

import fpp

from .constants import FPRIME_PYTHON_ANNOTATION
from .cpp_types import StringClass, formal_parameter_type, type_name, value_parameter_type, value_type
from .names import cpp_name, flat_name, namespaces_of, scope_of


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


def declared_string_size(type_: Optional[fpp.Type.Variant]) -> Optional[int]:
    """ The `string size` a type declares, looking through aliases

    Args:
        type_: The resolved type, None for a port that returns nothing
    Returns:
        The declared size in bytes, or None when the type is not a string or is a string of default size
    """
    if type_ is None:
        return None
    underlying = type_.underlying_type
    if isinstance(underlying, fpp.Type.String):
        return underlying.value
    return None


def string_size_expression(type_: Optional[fpp.Type.Variant]) -> Optional[str]:
    """ The C++ expression for the size a string type holds, `FW_FIXED_LENGTH_STRING_SIZE` when it declares none

    Returns:
        The size expression, or None when the type is not a string
    """
    if type_ is None or not isinstance(type_.underlying_type, fpp.Type.String):
        return None
    size = declared_string_size(type_)
    return "FW_FIXED_LENGTH_STRING_SIZE" if size is None else str(size)


class ArgumentView(ABC):
    """ One argument of a handler or of a method bound into Python, with what the bindings need to know of it """

    @property
    @abstractmethod
    def name(self) -> str:
        """ The argument's name """

    @property
    @abstractmethod
    def cpp_type(self) -> str:
        """ The argument's C++ type, reference qualifiers included """

    @property
    @abstractmethod
    def resolved_type(self) -> fpp.Type.Variant:
        """ The argument's FPP semantic type """

    @property
    def declared_size(self) -> Optional[int]:
        """ The argument's declared `string size`, None unless it is a string of explicit size """
        return declared_string_size(self.resolved_type)

    @property
    def string_size(self) -> Optional[str]:
        """ The C++ expression for the size of the argument's string, None unless it is a string """
        return string_size_expression(self.resolved_type)


class FormalParameterView(ArgumentView):
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

    @property
    def resolved_type(self) -> fpp.Type.Variant:
        """ The parameter's FPP semantic type """
        type_ = self.param.type_name.resolved_type
        assert type_ is not None
        return type_


class StateMachineValueView(ArgumentView):
    """ The value a state machine signal carries, and that the actions and guards it reaches take

    F Prime names it `value` everywhere and passes it as a port passes an argument: a primitive by value,
    anything else by `const` reference, a string as `Fw::StringBase`.
    """

    def __init__(self, type_name: fpp.ast.TypeName) -> None:
        """ Wrap the type an action, guard or signal declares """
        self.type_name = type_name

    @property
    def name(self) -> str:
        """ The name F Prime gives the value """
        return "value"

    @property
    def cpp_type(self) -> str:
        """ The value's C++ type, reference qualifiers included """
        return value_parameter_type(self.resolved_type, StringClass.PORT)

    @property
    def resolved_type(self) -> fpp.Type.Variant:
        """ The value's FPP semantic type """
        type_ = self.type_name.resolved_type
        assert type_ is not None
        return type_


def state_machine_values(type_name: Optional[fpp.ast.TypeName]) -> List[ArgumentView]:
    """ The value arguments of a state machine action, guard or signal: one when it declares a type, else none """
    return [] if type_name is None else [StateMachineValueView(type_name)]


class UnsupportedModelError(Exception):
    """ The model uses a feature this autocoder cannot bind to Python """


class HandlerView(ABC):
    """ One pure virtual handler F Prime declares for a component member

    A handler's signature is a fixed prefix -- the port number for a general port, the opcode and the
    command sequence number for a command, nothing for an internal port -- followed by its formal parameters:
    the member's own, or none for a command's overflow hook. The generated C++ override, the call it forwards
    into Python, and the stub in the Python template all have to agree on that signature, so it is spelled once
    here and each generator reads it back rather than repeating the prefix.
    """

    #: The handler's fixed leading parameters, as (C++ type, name, doc comment) triples
    HANDLER_PREFIX: Tuple[Tuple[str, str, str], ...] = ()

    #: What the handler handles, as it reads in a generated comment
    HANDLER_KIND: str = ""

    #: Whether F Prime declares the handler `const`, as it does a state machine guard
    IS_CONST: bool = False

    @property
    @abstractmethod
    def name(self) -> str:
        """ The member's name as written in the model """

    @property
    @abstractmethod
    def handler_name(self) -> str:
        """ The name of the handler F Prime declares for this member """

    @property
    def description(self) -> str:
        """ What the handler is, as it reads in a generated comment """
        return f"Handler for {self.HANDLER_KIND} {self.name}"

    @property
    @abstractmethod
    def parameters(self) -> Sequence[ArgumentView]:
        """ The member's own formal parameters, in declaration order """

    @property
    def handler_return_type(self) -> str:
        """ The C++ return type of the handler; only a port or a state machine guard can return a value """
        return "void"

    @property
    def return_declared_size(self) -> Optional[int]:
        """ The declared `string size` of the handler's return value, None unless it returns a sized string """
        return None

    @property
    def handler_parameters(self) -> List[Sequence[str]]:
        """ Every parameter of the handler, prefix first, for a C++ declaration

        Prefix parameters are (C++ type, name, doc comment) triples; the member's own parameters have no doc
        comment and are (C++ type, name) pairs.
        """
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

    @property
    def return_declared_size(self) -> Optional[int]:
        """ The declared `string size` of the port's return value, None unless it returns a sized string """
        return_type_name = self.definition.return_type
        return declared_string_size(None if return_type_name is None else return_type_name.resolved_type)


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


class OverflowHookView(HandlerView):
    """ The overflow hook F Prime declares for a member with `hook` queue-full behavior

    F Prime calls it instead of the handler when the message cannot be queued. It takes the handler's arguments,
    except that a command's hook gets only the opcode and the command sequence number. The handler prefix is the
    owner's, so it is copied onto the instance rather than declared by the class.
    """

    def __init__(self, owner: HandlerView) -> None:
        """ Wrap the hook of a port, internal port or command """
        self.owner = owner
        self.HANDLER_PREFIX = owner.HANDLER_PREFIX
        self.HANDLER_KIND = f"{owner.HANDLER_KIND} overflow hook"

    @property
    def is_command_hook(self) -> bool:
        """ Whether the hook is a command's, which takes no command arguments and must answer the command """
        return isinstance(self.owner, CommandView)

    @property
    def description(self) -> str:
        """ What the hook is, as it reads in a generated comment """
        return f"Overflow hook for {self.owner.HANDLER_KIND} {self.name}"

    @property
    def name(self) -> str:
        """ The owning member's name as written in the model """
        return self.owner.name

    @property
    def handler_name(self) -> str:
        """ The name of the overflow hook F Prime declares for the owning member """
        suffix = "cmdOverflowHook" if self.is_command_hook else "overflowHook"
        return f"{self.owner.name}_{suffix}"

    @property
    def parameters(self) -> Sequence[ArgumentView]:
        """ The owning member's formal parameters, none for a command """
        return [] if self.is_command_hook else self.owner.parameters


class StateMachineView:
    """ One state machine definition, with the C++ and Python names F Prime and the bindings give it

    F Prime generates a state machine into the namespace of its enclosing modules even when it is defined
    inside a component: the component's name is folded into the machine's instead, so `M` in component `C`
    of module `Ref` becomes `Ref::C_MStateMachineBase` with its states in `Ref::C_M_State`. The Python
    bindings follow the same names, under the module's Python scope.
    """

    def __init__(self, analysis: fpp.Analysis, symbol: fpp.Symbol.Variant) -> None:
        """ Wrap the state machine a symbol defines

        Args:
            analysis: The analyzed model the state machine is part of
            symbol: The symbol of the state machine definition
        """
        self.analysis = analysis
        self.symbol = symbol
        self.state_machine = analysis.state_machine_map[symbol]

    @property
    def fpp_name(self) -> str:
        """ The state machine's FPP-qualified name """
        return self.symbol.qualified_name

    @property
    def is_internal(self) -> bool:
        """ Whether the model defines the state machine's behavior, rather than hand-written C++ """
        return self.state_machine.kind == fpp.Kind.Internal

    @property
    def enclosing_component(self) -> Optional[fpp.Symbol.Variant]:
        """ The component the state machine is defined inside, None when it is defined in a module """
        parent = self.analysis.parent_symbol_map.get(self.symbol)
        return parent if isinstance(parent, fpp.Symbol.Component) else None

    @property
    def scope(self) -> str:
        """ The FPP-qualified name of the module the state machine's C++ and Python names live in """
        component = self.enclosing_component
        return scope_of(self.fpp_name if component is None else component.qualified_name)

    @property
    def base_name(self) -> str:
        """ The state machine's name within its module, with any enclosing component's folded in """
        component = self.enclosing_component
        name = self.symbol.unqualified_name
        return name if component is None else f"{component.unqualified_name}_{name}"

    def _in_scope(self, name: str) -> str:
        """ The C++-qualified spelling of a name in the state machine's module """
        return cpp_name(f"{self.scope}.{name}") if self.scope else name

    @property
    def base_class(self) -> str:
        """ The C++-qualified name of the state machine base class F Prime generates """
        return self._in_scope(f"{self.base_name}StateMachineBase")

    @property
    def signal_type(self) -> str:
        """ The C++-qualified name of the state machine's signal enumeration """
        return f"{self.base_class}::Signal"

    @property
    def state_type(self) -> str:
        """ The C++-qualified name of the F Prime enumeration of the state machine's states """
        return self._in_scope(f"{self.base_name}_State")

    @property
    def header_name(self) -> str:
        """ The file name of the header F Prime generates for the state machine """
        return f"{self.base_name}StateMachineAc.hpp"

    @property
    def interface_name(self) -> str:
        """ The C++-qualified name of the interface an external state machine's C++ implementation provides """
        return self._in_scope(f"{self.base_name}_Interface")

    @property
    def component_class(self) -> str:
        """ The name of the class F Prime nests in a component's base class for this state machine

        It is the machine's FPP-qualified name, flattened, and prefixes the name of every action and guard
        handler.
        """
        return flat_name(self.fpp_name)

    @property
    def state_python_name(self) -> str:
        """ The name the state enumeration is bound into Python under, its C++ name in the module """
        return f"{self.base_name}_State"

    @property
    def signal_python_name(self) -> str:
        """ The name the signal enumeration is bound into Python under, alongside the state enumeration """
        return f"{self.base_name}_Signal"

    @property
    def state_constants(self) -> List[str]:
        """ The constants of the state enumeration fpp synthesizes, including its uninitialized state """
        for member in self.state_machine.node.members or []:
            if isinstance(member, fpp.ast.DefEnum):
                return [constant.name for constant in member.constants]
        return []

    @property
    def signal_constants(self) -> List[str]:
        """ The constants of the signal enumeration F Prime generates

        F Prime puts a signal of its own first, for the initial transition. An action on that transition
        receives it, so it is bound along with the modeled signals.
        """
        return [INITIAL_TRANSITION_SIGNAL] + [signal.name for signal in self._signals]

    @property
    def _signals(self) -> List[fpp.ast.DefSignal]:
        """ The state machine's signal definitions, in declaration order """
        return [
            signal.definition
            for signal in self.state_machine.signals
            if isinstance(signal.definition, fpp.ast.DefSignal)
        ]

    @property
    def signals(self) -> List[Tuple[str, List[ArgumentView]]]:
        """ The state machine's signals, as (name, value arguments) pairs in declaration order """
        return [(signal.name, state_machine_values(signal.type_name)) for signal in self._signals]

    @property
    def handlers(self) -> List[HandlerView]:
        """ The handlers F Prime declares for the state machine's actions and then its guards """
        handlers: List[HandlerView] = [
            StateMachineActionView(self, action.definition)
            for action in self.state_machine.actions
            if isinstance(action.definition, fpp.ast.DefAction)
        ]
        handlers += [
            StateMachineGuardView(self, guard.definition)
            for guard in self.state_machine.guards
            if isinstance(guard.definition, fpp.ast.DefGuard)
        ]
        return handlers


#: The signal F Prime passes to an action on a state machine's initial transition
INITIAL_TRANSITION_SIGNAL = "__FPRIME_INITIAL_TRANSITION"


class StateMachineActionView(HandlerView):
    """ The handler F Prime declares for one action of an internal state machine

    The handler belongs to the state machine rather than to an instance of it, so every instance of the
    machine in a component calls the same handler, and the state machine id says which one did. The signal
    is the one being handled, the machine's own initial-transition signal on the initial transition.
    """

    HANDLER_KIND = "state machine action"

    def __init__(self, machine: StateMachineView, action: fpp.ast.DefAction) -> None:
        """ Wrap an action of a state machine """
        self.machine = machine
        self.action = action
        self.HANDLER_PREFIX = (
            ("SmId", "smId", "The state machine id"),
            (f"{machine.component_class}::Signal", "signal", "The signal"),
        )

    @property
    def name(self) -> str:
        """ The action's name as written in the model """
        return self.action.name

    @property
    def description(self) -> str:
        """ What the handler is, as it reads in a generated comment """
        return f"Handler for {self.HANDLER_KIND} {self.name} of {self.machine.fpp_name}"

    @property
    def handler_name(self) -> str:
        """ The name of the handler F Prime declares for this action """
        return f"{self.machine.component_class}_action_{self.name}"

    @property
    def parameters(self) -> Sequence[ArgumentView]:
        """ The value the action takes, if it declares one """
        return state_machine_values(self.action.type_name)


class StateMachineGuardView(HandlerView):
    """ The handler F Prime declares for one guard of an internal state machine

    A guard is an action that decides whether a transition is taken: F Prime declares it `const`, returning
    a `bool`, with the same arguments an action has.
    """

    HANDLER_KIND = "state machine guard"
    IS_CONST = True

    def __init__(self, machine: StateMachineView, guard: fpp.ast.DefGuard) -> None:
        """ Wrap a guard of a state machine """
        self.machine = machine
        self.guard = guard
        self.HANDLER_PREFIX = (
            ("SmId", "smId", "The state machine id"),
            (f"{machine.component_class}::Signal", "signal", "The signal"),
        )

    @property
    def name(self) -> str:
        """ The guard's name as written in the model """
        return self.guard.name

    @property
    def description(self) -> str:
        """ What the handler is, as it reads in a generated comment """
        return f"Handler for {self.HANDLER_KIND} {self.name} of {self.machine.fpp_name}"

    @property
    def handler_name(self) -> str:
        """ The name of the handler F Prime declares for this guard """
        return f"{self.machine.component_class}_guard_{self.name}"

    @property
    def parameters(self) -> Sequence[ArgumentView]:
        """ The value the guard takes, if it declares one """
        return state_machine_values(self.guard.type_name)

    @property
    def handler_return_type(self) -> str:
        """ A guard answers whether the transition is taken """
        return "bool"


class StateMachineInstanceView:
    """ One state machine instance of a component

    F Prime gives each instance a getter for its current state and a method per signal that queues the
    signal for the component's thread to handle.
    """

    def __init__(self, analysis: fpp.Analysis, instance: fpp.StateMachineInstance) -> None:
        """ Wrap a state machine instance """
        self.instance = instance
        self.machine = StateMachineView(analysis, instance.symbol)

    @property
    def name(self) -> str:
        """ The instance's name, which is also its state machine id """
        return self.instance.name

    @property
    def get_state_name(self) -> str:
        """ The name of the method F Prime declares to read the instance's current state """
        return f"{self.name}_getState"

    @property
    def send_signals(self) -> List[Tuple[str, List[ArgumentView]]]:
        """ The methods F Prime declares to send the instance each signal, as (name, arguments) pairs """
        return [(f"{self.name}_sendSignal_{signal}", values) for signal, values in self.machine.signals]


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

    @property
    def parameters(self) -> List[FormalParameterView]:
        """ The event's formal parameters, in declaration order """
        return [FormalParameterView(param, StringClass.PORT) for param in self.event.node.params]


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

    @property
    def string_size(self) -> Optional[str]:
        """ The C++ expression for the size of the channel's string, None unless it is a string """
        return string_size_expression(self.channel.channel_type)


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

    def __init__(self, analysis: fpp.Analysis, component: fpp.Component) -> None:
        """ Wrap a component of an analyzed model """
        self.analysis = analysis
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
    def overflow_hooks(self) -> List[OverflowHookView]:
        """ The overflow hooks of the async input ports, internal ports and async commands with `hook` queue-full
        behavior, in that order
        """
        hooks = [
            OverflowHookView(port)
            for port in self.input_ports
            if isinstance(port.port.kind, fpp.GeneralKind.AsyncInput)
            and port.port.kind.queue_full == fpp.ast.QueueFull.Hook
        ]
        hooks += [
            OverflowHookView(port)
            for port in self.internal_ports
            if port.port.queue_full == fpp.ast.QueueFull.Hook
        ]
        hooks += [
            OverflowHookView(command)
            for command in self.commands
            if isinstance(command.command.kind, fpp.NonParamKind.Async)
            and command.command.kind.queue_full == fpp.ast.QueueFull.Hook
        ]
        return hooks

    @property
    def state_machine_instances(self) -> List[StateMachineInstanceView]:
        """ The component's state machine instances, in name order """
        return [
            StateMachineInstanceView(self.analysis, instance)
            for instance in self.component.state_machine_instance_map.values()
        ]

    @property
    def state_machines(self) -> List[StateMachineView]:
        """ The distinct state machines the component instantiates, in the order of their first instance """
        machines: List[StateMachineView] = []
        for instance in self.state_machine_instances:
            if all(machine.symbol != instance.machine.symbol for machine in machines):
                machines.append(instance.machine)
        return machines

    @property
    def nested_state_machines(self) -> List[StateMachineView]:
        """ The internal state machines defined inside the component, in definition order

        These get no binding from the module they are defined in, which does not descend into components, so the
        component's own generation binds them.
        """
        symbols = [
            self.analysis.symbol_map[member.node_id]
            for member in self.node.members
            if isinstance(member, fpp.ast.DefStateMachine)
        ]
        machines = [StateMachineView(self.analysis, symbol) for symbol in symbols]
        return [machine for machine in machines if machine.is_internal]

    def check_supported(self) -> None:
        """ Reject a component whose features this autocoder cannot bind

        F Prime declares a pure virtual handler for every data product container, and for every action and guard
        of an external state machine, and the overflow hook of a state machine instance with `hook` queue-full
        behavior. None of these has a Python counterpart -- a container handler takes a `Fw::DpContainer`, an
        external machine's actions and guards are declared by its hand-written C++ interface rather than in the
        model, and a state machine's overflow hook takes the queued signal as a raw serial buffer -- so
        generating the component anyway would leave an abstract class and fail at link time, a long way from
        the cause.

        Raises:
            UnsupportedModelError: The component has data products, or a state machine instance that
                cannot be bound
        """
        remedy = (
            f"Remove the '@ {FPRIME_PYTHON_ANNOTATION}' annotation to implement this component in C++ instead."
        )
        if self.component.has_data_products:
            raise UnsupportedModelError(
                f"Component {self.fpp_name} has data products, which fprime-python cannot bind: F Prime"
                f" declares a handler for each of them that has no Python equivalent yet. {remedy}"
            )
        for instance in self.state_machine_instances:
            machine = instance.machine
            described = f"Component {self.fpp_name} has state machine instance {instance.name}"
            if not machine.is_internal:
                raise UnsupportedModelError(
                    f"{described} of external state machine {machine.fpp_name}, which fprime-python cannot bind:"
                    f" its actions and guards are declared by the hand-written C++ interface"
                    f" {machine.interface_name}, not in the model. Define the state machine's behavior in FPP to"
                    f" bind it. {remedy}"
                )
            if instance.instance.queue_full == fpp.ast.QueueFull.Hook:
                raise UnsupportedModelError(
                    f"{described} with 'hook' queue-full behavior, which fprime-python cannot bind: its overflow"
                    f" hook {instance.name}_stateMachineOverflowHook takes the queued signal as a raw serial"
                    f" buffer (Fw::SerialBufferBase), which has no Python equivalent. Use 'assert', 'block' or"
                    f" 'drop' instead. {remedy}"
                )
            component = machine.enclosing_component
            if component is not None and component != self.component.symbol:
                raise UnsupportedModelError(
                    f"{described} of state machine {machine.fpp_name}, which is defined inside another"
                    f" component, so fprime-python binds its states and signals only with that component. Define"
                    f" the state machine in a module, or inside {self.fpp_name}, to bind it. {remedy}"
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
        """ Every handler F Prime declares, members first and overflow hooks last, in generation order

        Every family gets the same forwarding C++ override and a stub in the Python template (a command's
        stub, and its overflow hook's, also sends a response, and a guard's returns a bool), so the generators
        walk this one list rather than each family in turn. State machine actions and guards come once per
        state machine, however many instances of it the component has.
        """
        handlers: List[HandlerView] = list(self.input_ports)
        handlers += self.internal_ports
        handlers += self.commands
        handlers += self.state_machine_handlers
        handlers += self.overflow_hooks
        return handlers

    @property
    def state_machine_handlers(self) -> List[HandlerView]:
        """ The action and guard handlers of every state machine the component instantiates """
        return [handler for machine in self.state_machines for handler in machine.handlers]

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

    def check_unannotated(self, annotation: str) -> None:
        """ Reject an unannotated deployment topology that instantiates Python-bound components

        Only an annotated topology gets the setup and teardown bindings the Python runner starts a deployment
        with, so a deployment of Python components without the annotation would build and then fail at
        startup.

        Args:
            annotation: The annotation the topology lacks, and that marks a component as Python-bound
        Raises:
            UnsupportedModelError: The topology is a deployment and instantiates Python-bound components
        """
        if not self.node.is_deployment:
            return
        instances = self.bound_instances(annotation)
        if instances:
            names = ", ".join(instance.qualified_name for instance in instances)
            raise UnsupportedModelError(
                f"Deployment topology {self.fpp_name} instantiates '@ {annotation}' components ({names}) but"
                f" is not annotated '@ {annotation}', so Python would have no setup or teardown to start it"
                f" with. Annotate the topology with '@ {annotation}'."
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
