""" fprime_python.component_generator:

Generates everything an FPP component annotated for Python needs.

Two generators live here. `ComponentBindingGenerator` produces the pybind11 bindings that expose the
component's methods to Python. `ComponentImplementationGenerator` produces the component implementation
itself: the C++ class that F Prime's topology instantiates, which forwards every handler into a mirrored
Python object, plus the Python base class that object inherits from and a template for the user to fill
in.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import fpp
from fprime_cpp_codegen import Body, ClassBuilder, CppDocBuilder, Output

from .binding_generator import BindingGenerator, expression_chain, standard_def
from .constants import SELF_MEMBER, SUPPORT_HEADER, TOOL_NAME
from .include import IncludeManager
from .view import CommandView, ComponentView, HandlerView, ParameterView


#: Telemetry write bindings keep the default timestamp argument F Prime declares, so that Python callers
#: may leave it out and have the component request the time itself
TELEMETRY_DEF_TEMPLATE = (
    '.def("{name}", &{fqn}::{name}, pybind11::arg("arg"), '
    'pybind11::arg("_tlmTime") = Fw::Time())'
)


def base_class_methods(component: ComponentView) -> List[str]:
    """ The base-class methods the component exposes to Python

    F Prime declares these `protected`, so the generated class re-exposes them with using-declarations
    and the bindings take their addresses. They are the methods a Python implementation calls to act on
    the rest of the topology: dispatching its own queue, reading the time, responding to commands,
    invoking its output ports, and sending events.

    Args:
        component: The component to list the methods of
    Returns:
        The method names, in binding order
    """
    # A queued component dispatches its own messages, whereas an active component's task does it and a
    # passive component has no queue at all
    conditional = [
        ("doDispatch", component.is_queued),
        ("dispatchAvailableMessages", component.is_queued),
        ("getTime", component.has_time_port),
        ("cmdResponse_out", component.has_commands),
    ]
    methods = [name for name, present in conditional if present]
    methods += [port.invoker_name for port in component.output_ports]
    methods += [port.connection_check_name for port in component.output_ports]
    methods += [port.invoker_name for port in component.internal_ports]
    methods += [event.dispatch_name for event in component.events]
    return methods


class ComponentBindingGenerator(BindingGenerator):
    """ Provides the generation of pybind11 bindings for FPP components

    This generator creates the pybind11 binding code required to bind FPP components to Python. This
    includes the various telemetry channels, parameters, handlers, and commands.
    """

    def __init__(
        self, include_manager: IncludeManager, symbol: fpp.Symbol.Variant, component: fpp.Component
    ) -> None:
        """ Initialize the generator for one component

        Args:
            include_manager: Resolves the include paths of the headers the binding needs
            symbol: The symbol of the component being bound
            component: The analyzed component being bound
        """
        super().__init__(include_manager, symbol)
        self.component = ComponentView(component)

    def bind(self, body: Body) -> None:
        """ Write the pybind11 statements binding this component """
        fqn = self.cpp_fqn
        links = [standard_def(method, fqn) for method in base_class_methods(self.component)]
        # A parameter is read through the generated helper rather than through F Prime's own getter,
        # because the getter reports validity through an out parameter that has no Python equivalent
        links += [
            f'.def("{param.getter_name}", &{fqn}::{param.helper_name})'
            for param in self.component.parameters
        ]
        links += [
            TELEMETRY_DEF_TEMPLATE.format(name=channel.write_name, fqn=fqn)
            for channel in self.component.channels
        ]
        body.raw(expression_chain(f'pybind11::class_<{fqn}>(m, "{self.name}")', links))

    def cpp_includes(self) -> List[str]:
        """ Get the C++ includes for a component type

        Alongside the standard includes this adds the component's own header, which is the header of the
        implementation this autocoder generates rather than F Prime's autocoded component base header.
        """
        return super().cpp_includes() + [
            self.include_manager.get_sibling_path(self.symbol, f"{self.name}.hpp")
        ]


#: Attribute that exports the component class from the shared object it is compiled into, so that
#: pybind11 can see its symbols in the object it loads
VISIBILITY_ATTRIBUTE = '__attribute__((visibility("default")))'

#: Docstring of the generated Python base class
PYTHON_BASE_CLASS_DOCSTRING = '''""" Auto-coded base class for {name}

    This base class is auto-generated to mirror the C++ component class. It delegates the methods to the
    C++ implementation provided by the _init_ac function. The _init_ac function must be called first and
    is done so by the auto-generated init function in the component C++.

    This implies that a Python user cannot instantiate this class directly and must rely on the F Prime
    topology to instantiate the component as all F Prime components are.

    Caution: This class relies on an absence of an __init__ method. We cannot guarantee that a derived
        class will not define an __init__ method that fails to call super().__init__() and thus this
        implementation must not rely on __init__ to be called. Instead this implementation relies on the
        _init_ac method to be called by the C++ and converts use of the internal delegate before that
        call to an Exception.
    """'''

#: The Python base class that delegates to the C++ implementation. Delegation is done through
#: __getattr__ and __setattr__ so that any attribute reaches the C++ implementation unless this class or
#: the user's subclass defines it.
PYTHON_BASE_CLASS_TEMPLATE = '''class {name}Base(object):
    {docstring}

    def _init_ac(self, this):
        """ Initialize 'this' object to redirect into the C++ implementation

        In order to automatically bind to the C++ implementation, a pointer to the C++ object must be
        stored within this class. This method *must* be called before any Python calls are made.
        """
        self.this = this

    def __getattr__(self, name):
        """ Delegate attribute read access to the C++ implementation

        This method provides automatic delegation to the C++ implementation for any attribute that is not
        found within this implementation.

        Args:
            name: The name of the attribute to access
        Returns:
            The value of the attribute from the C++ implementation
        """
        # Prevent infinite recursion if looking for 'this' before it is initialized. If "this" was set in
        # _init_ac, then this fallback method would not have been called. If the name is "this", then
        # _init_ac was not called and therefore this attribute cannot be accessed.
        if name == "this":
            raise AttributeError("'this' not initialized. Call _init_ac first.")
        elif not hasattr(self, "this"):
            raise Exception(
                "{name} cannot be instantiated directly. It must be instantiated by F Prime"
            )
        return getattr(self.this, name)

    def __setattr__(self, name, value):
        """ Delegate attribute write access to the C++ implementation

        This method provides automatic delegation to the C++ implementation for any attribute that is not
        found within this implementation. First, this method attempts to set the attribute in the C++
        implementation. If that fails the attribute is set in this (Python) implementation.

        Args:
            name: The name of the attribute to set
            value: The value to set the attribute to
        """
        try:
            return setattr(self.this, name, value)
        except Exception:
            super().__setattr__(name, value)
'''

#: The Python implementation template a user renames and fills in
PYTHON_IMPLEMENTATION_TEMPLATE = '''""" {name} Python component implementation

This is the Python implementation for the {name} component. This class extends the auto-coded Python base
class {name}Base that provides the necessary plumbing to connect to the C++ stub connected to the rest of
the F Prime topology.
"""
import fprime_py
from {name}BaseAc import {name}Base


class {name}({name}Base):
    """ Python implementation for the {name} component """
{handlers}'''

#: Stub for one port handler in the Python implementation template
PYTHON_PORT_HANDLER_TEMPLATE = '''    def {handler}(self{args}):
        """ Handle the {name} {kind} """
        # TODO: Implement {kind} handler{return_note}
        pass
'''

#: Stub for one command handler in the Python implementation template
PYTHON_COMMAND_HANDLER_TEMPLATE = '''    def {handler}(self{args}):
        """ Handle the {name} command """
        # TODO: Implement command handler
        self.cmdResponse_out(opCode, cmdSeq, fprime_py.Fw.CmdResponse(fprime_py.Fw.CmdResponse.T.OK))
'''


class ComponentImplementationGenerator(object):
    """ Generator for the Python/C++ component implementation files

    This generator creates the C++ implementation that connects the F Prime topology to the Python layer:
    a class deriving from F Prime's autocoded component base whose port, command and parameter members
    forward into a mirrored Python object.

    Alongside it, this generator creates the Python base class that provides delegation back to the C++
    implementation, and the Python implementation template that provides the skeleton for user code.
    """

    def __init__(
        self, include_manager: IncludeManager, symbol: fpp.Symbol.Variant, component: fpp.Component
    ) -> None:
        """ Initialize the generator for one component

        Args:
            include_manager: Resolves the include paths of the headers the implementation needs
            symbol: The symbol of the component being implemented
            component: The analyzed component being implemented
        """
        self.include_manager = include_manager
        self.symbol = symbol
        self.component = ComponentView(component)

    @property
    def name(self) -> str:
        """ The component's unqualified name """
        return self.component.name

    def _init_params(self) -> List[Tuple[str, str, str]]:
        """ The parameters of the generated init function

        A component with a message queue takes its depth, matching the base class it forwards to.
        """
        params = [("FwEnumStoreType", "instance", "The instance number")]
        if self.component.has_queue:
            return [("FwSizeType", "queueDepth", "The queue depth")] + params
        return params

    def _write_init(self, body: Body) -> None:
        """ Write the body of the generated init function

        The Python module for the component is imported and its mirror object constructed, then the
        object is handed the C++ `this` pointer so that calls can travel back the other way. Only that
        part needs the interpreter, so the GIL is held for it alone and released before F Prime's own
        initialization runs.
        """
        body.comment(
            "Acquire the GIL and import the Python module releasing the GIL before continuing with"
            " C++ init"
        )
        with body.block():
            body.line("pybind11::gil_scoped_acquire acquired{};")
            body.line(f'pybind11::module_ module = pybind11::module_::import("{self.name}");')
            body.comment("Construct the mirror Python object, storing it for C++ access")
            body.line(f'this->{SELF_MEMBER} = module.attr("{self.name}")();')
            body.comment(
                'Call auto-coded initialization function storing the C++ "this" object for Python'
            )
            body.line(f'this->{SELF_MEMBER}.attr("_init_ac")(this);')
        body.comment("Continue the standard initialization of F Prime")
        arguments = ", ".join(name for _, name, _ in self._init_params())
        body.line(f"{self.component.base_class}::init({arguments});")

    def _write_deinit(self, body: Body) -> None:
        """ Write the body of the generated deinit function

        Dropping the reference to the mirror object lets the interpreter shut down cleanly. The base class
        is then given its own teardown -- a queued or active component returns its message queue there --
        so that `deinit` undoes what `init` did rather than only the Python half of it.
        """
        body.comment("Acquire the GIL and dereference the Python object")
        with body.block():
            body.line("pybind11::gil_scoped_acquire acquired{};")
            body.line(f"this->{SELF_MEMBER} = pybind11::none();")
        body.comment("Continue the standard teardown of F Prime")
        body.line(f"{self.component.base_class}::deinit();")

    def _write_forwarding_call(self, body: Body, handler: HandlerView) -> None:
        """ Write a handler body that forwards the call into the mirrored Python object

        Args:
            body: The function body to write into
            handler: The component member whose handler is being written
        """
        body.line("pybind11::gil_scoped_acquire acquired{};")
        arguments = ", ".join(handler.handler_arguments)
        call = f'{SELF_MEMBER}.attr("{handler.handler_name}")({arguments})'
        if handler.handler_return_type == "void":
            body.line(f"{call};")
            return
        body.line(f"pybind11::object return_value = {call};")
        body.line(f"return return_value.cast<{handler.handler_return_type}>();")

    def _write_lifecycle(self, cls: ClassBuilder) -> None:
        """ Declare and define the component's construction, initialization and destruction

        Args:
            cls: The class builder to add the members to
        """
        component = self.component
        with cls.public("Construction, initialization, and destruction"):
            constructor = cls.constructor(
                params=[("const char*", "name", "The component name")],
                comment=f"Construct {self.name} object",
                # Nothing is constructed beyond what the base class does, and the document is strict, so
                # the empty body has to be declared rather than merely left unwritten
                body="",
            )
            constructor.init(f"{component.base_class}(name)")
            # The mirror object is owned by exactly one C++ object, so copying is not meaningful
            cls.constructor(
                params=[(f"const {self.name}&", "other")],
                deleted=True,
                comment=f"Copy construction of {self.name} is not supported",
            )
            cls.destructor(defaulted=True, comment=f"Destroy {self.name} object")
            init = cls.function(
                "init",
                params=self._init_params(),
                comment=f"Initialize {self.name} object and its mirrored Python object",
            )
            self._write_init(init.body)
            deinit = cls.function(
                "deinit",
                override=True,
                comment="Release the mirrored Python object",
            )
            self._write_deinit(deinit.body)

    def _write_handlers(self, cls: ClassBuilder) -> None:
        """ Declare and define one forwarding override per handler F Prime declares

        Args:
            cls: The class builder to add the handlers to
        """
        with cls.public("Handlers forwarded to Python"):
            for handler in self.component.handlers:
                override = cls.function(
                    handler.handler_name,
                    ret=handler.handler_return_type,
                    params=handler.handler_parameters,
                    override=True,
                    comment=f"Handler for {handler.HANDLER_KIND} {handler.name}",
                )
                self._write_forwarding_call(override.body, handler)

    def _write_exposed_members(self, cls: ClassBuilder) -> None:
        """ Re-expose the base class members Python needs, and declare the mirror object

        F Prime declares the methods a Python implementation calls on itself `protected`, so they are
        pulled into public scope for the bindings to take their addresses.

        Args:
            cls: The class builder to add the members to
        """
        component = self.component
        using_statements = base_class_methods(component) + [
            channel.write_name for channel in component.channels
        ]
        if using_statements:
            with cls.public("Base class members exposed to Python"):
                # The method names come from the model, so this is not margin-stripped
                cls.lines(
                    "\n".join(
                        f"using {component.base_class}::{method};"
                        for method in using_statements
                    ),
                    margin=None,
                )

        with cls.public("Member variables"):
            cls.var(
                "pybind11::object",
                SELF_MEMBER,
                comment="The mirrored Python object this component forwards into",
            )

    def document(self) -> CppDocBuilder:
        """ Build the C++ document holding the implementation's header and source

        Returns:
            The document, with the component class declared and defined
        """
        component = self.component
        doc = CppDocBuilder(
            self.name,
            description=f"{self.name} Python component implementation",
            include_guard=f"FPRIME_PYTHON_{self.name.upper()}_AC_HPP",
            tool_name=TOOL_NAME,
            # Every handler this generator declares has to forward into Python; one left unfilled would
            # otherwise render as an empty override that silently swallows the call
            strict=True,
        )
        doc.include(
            self.include_manager.get_include_path(self.symbol),
            SUPPORT_HEADER,
        )
        if component.parameters:
            # std::tuple, returned by the parameter helpers
            doc.system_include("tuple")
        doc.include(
            self.include_manager.get_sibling_path(self.symbol, f"{self.name}.hpp"),
            output=Output.CPP,
        )

        namespace = doc.namespace(*component.namespaces) if component.namespaces else doc
        with namespace.class_(
            self.name,
            extends=f"public {component.base_class}",
            comment=f"Python implementation of the {component.fpp_name} component",
            attributes=VISIBILITY_ATTRIBUTE,
        ) as cls:
            self._write_lifecycle(cls)
            self._write_handlers(cls)
            if component.parameters:
                with cls.public("Parameter helpers"):
                    for param in component.parameters:
                        self._write_parameter_helper(cls, param)
            self._write_exposed_members(cls)
        return doc

    def _write_parameter_helper(self, cls: ClassBuilder, param: ParameterView) -> None:
        """ Declare and define the helper that reads one parameter

        F Prime's parameter getter reports validity through an out parameter, which does not map onto a
        Python return value, so the helper returns the value and the status together as a tuple.

        Args:
            cls: The class builder to add the helper to
            param: The parameter to generate the helper for
        """
        helper = cls.function(
            param.helper_name,
            ret=f"std::tuple<{param.cpp_type}, Fw::ParamValid>",
            comment=f"Read parameter {param.name} and its validity together",
        )
        with helper.body as body:
            body.line("Fw::ParamValid _status_;")
            body.line(f"{param.cpp_type} _value_ = this->{param.getter_name}(_status_);")
            body.line("return std::make_tuple(_value_, _status_);")

    def python_base_class(self) -> str:
        """ Generate the Python base class the user's implementation inherits from

        Returns:
            The contents of the generated Python base class file
        """
        return PYTHON_BASE_CLASS_TEMPLATE.format(
            name=self.name,
            docstring=PYTHON_BASE_CLASS_DOCSTRING.format(name=self.name),
        )

    def python_implementation(self) -> str:
        """ Generate the Python implementation template for the user to fill in

        Returns:
            The contents of the generated Python implementation template file
        """
        stubs = []
        for handler in self.component.handlers:
            args = "".join(f", {name}" for name in handler.handler_arguments)
            # A command handler is not left to fall off the end: the ground waits for a response, so the
            # stub sends one
            if isinstance(handler, CommandView):
                stubs.append(
                    PYTHON_COMMAND_HANDLER_TEMPLATE.format(
                        handler=handler.handler_name, name=handler.name, args=args
                    )
                )
                continue
            return_type = handler.handler_return_type
            stubs.append(
                PYTHON_PORT_HANDLER_TEMPLATE.format(
                    handler=handler.handler_name,
                    name=handler.name,
                    kind=handler.HANDLER_KIND,
                    args=args,
                    # A port that returns a value cannot be left returning None: the C++ side casts what
                    # comes back to the port's return type and raises if it cannot
                    return_note=(
                        "" if return_type == "void" else f", returning a {return_type}"
                    ),
                )
            )
        return PYTHON_IMPLEMENTATION_TEMPLATE.format(
            name=self.name, handlers="\n".join(stubs)
        )

    def files(self) -> Dict[str, str]:
        """ Generate the component implementation's files

        Returns:
            A mapping of file name to file contents
        """
        return {
            **self.document().files(),
            f"{self.name}BaseAc.py": self.python_base_class(),
            f"{self.name}.template.py": self.python_implementation(),
        }
