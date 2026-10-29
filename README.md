# fprime-python: F´ to Python Bindings

Once in a great blue moon, an fprime developer will find themselves in a bind: integrate into existing python code, or
incur the cost of translating that code into C++ before use. Since Python code is typically deployed as a prototype it
can be incredibly helpful to call it directly and defer the translation cost until after the project has left the
prototype phase.

This package allows users to import F Prime from within a running python interpreter and develop F Prime components in
Python. This effectively allows Python developers to run F Prime and connect it to their python code using python.

**Acknowledgements:** [`pybind11`](https://github.com/pybind/pybind11) library helps quite a bit! Also thanks to Selina
Chu, JPL, for the initial suggestion to call embedded Python directly from F´.

**WARNING:** this is experimental code without guarantee. I'll do my best to resolve issues when reported.

## What is fprime-python?

fprime-python expands F´ to allow:
- Wrapping of Python libraries in F´ Python Components
- Rapid prototyping of F´ components using Python
- Exploring F´ component implementation from a Python background

| What does fprime-python do?                  | What does fprime-python not do?                  |
|----------------------------------------------|--------------------------------------------------|
| Bridges F´ to Python                         | Reimplement F´ in Python nor remove existing C++ |
| Allows F´ component implementation in Python | Replace F´ built-in components, ports            |
| Exposes F´ types to Python                   |                                                  |

## Architecture

F´ python allows a Python interpreter to import F Prime as a library. It provides a set of automatically generated C++/Python
bindings to allow an F´ deployment to call back out to an implementation written in python.  Essentially, bindings build on the
F´ autocoder output to extend the Component's implementation into the python ecosystem.  This is all handled through autocoding
and support libraries meaning the user need only mark components as implemented in python (see below).

![fprime-python Architecture](./docs/fprime-python-architecture.png)

Bindings are generated from the component's model and are built on the [`pybind11`](https://github.com/pybind/pybind11)
library, which handles the nuances of the Python API.

## Installation and Setup

In order to use `fprime-python` download the source code, or add it as a Git submodule.  Once finished, install the
autocoder and its dependencies by running `pip install .` in the `fprime-python` checkout. This requires Python 3.10
or newer. The autocoder reads the FPP model directly, so `FPRIME_ENABLE_JSON_MODEL_GENERATION` and
`fprime-python-model` are no longer needed.

Next, add the path to the download in the `library_locations` list set in settings.ini for a deployment. 

```ini
library_locations: ./lib/fprime-python
```

When running the code, the same version of Python must be used as the python used to build it.

## Setting a Component Up With Python Bindings

In order to set up a component to be implemented in python, the user must annotate their component with the
`@ fprime-python` annotation in their FPP model.

```
@ fprime-python
active component ActivePythonExample {
    ...
}
```

Once finished, the python bindings will be autocoded and included in the next build (assuming the deployment is setup 
as shown below). This will also produce a `<component>.template.py` file in the component folder as a basic template for
implementing components in python.

Every port, command, event, telemetry channel, parameter and internal port of the component is bound, as is the
overflow hook of each member with `hook` queue-full behavior and each instance of an internal state machine (see
below). A few component features cannot be bound yet, because F Prime declares a handler for each that has no Python
equivalent:

| Feature | Why | What happens |
| --- | --- | --- |
| serial port | its handler takes a serialization buffer | rejected with an error naming the port |
| instance of an external state machine | its actions and guards are declared by hand-written C++ (`<Machine>_Interface`), not in the model | rejected with an error naming the instance |
| state machine instance with `hook` queue-full behavior | its overflow hook takes the queued signal as a raw serial buffer | rejected with an error naming the instance |
| data product container | its handler takes a `Fw::DpContainer` | rejected with an error naming the component |

In each case the autocoder refuses rather than generating a class that would leave the handler unimplemented and
fail to link. Drop the `@ fprime-python` annotation to implement such a component in C++ instead.

### Queue-Full Overflow Hooks

An async input port, internal port or async command declared with `hook` queue-full behavior gets an overflow hook
in Python next to its handler. When the component's queue is full, F Prime calls the hook instead of queuing the
message, and the message is dropped once the hook returns.

| Member | Hook | Arguments |
| --- | --- | --- |
| `async input port textIn: Text hook` | `textIn_overflowHook` | `portNum` and the port's arguments |
| `internal port poke(note: string size 5) hook` | `poke_overflowHook` | the internal port's arguments |
| `async command DO(n: U32) hook` | `DO_cmdOverflowHook` | `opCode` and `cmdSeq` only |

Every hook must be implemented: a component whose Python class lacks one raises `AttributeError` from its generated
`init`, at startup rather than at the first overflow. The template has a stub for each.

- **Thread.** The hook runs on the thread of the caller that found the queue full, not on the component's thread.
  Before any Python runs, that thread must take the GIL, which the component's own busy thread often holds, so even an
  empty hook can delay the caller. Keep the hook short, never block in it, size the queue so that overflow stays the
  exception, and prefer `drop` where the caller's timing matters.
- **Concurrency.** The hook can run while one of the component's handlers is part-way through on the component's
  thread, so it must not rely on state that a handler updates in several steps.
- **Ownership.** F Prime does not count or report a hooked drop. The hook owns the dropped message: if a port carries
  an `Fw::Buffer`, the hook must return or deallocate it.
- **Commands.** F Prime does not answer a command it dropped, so a command hook must send a response. The template's
  stub sends `BUSY`:

```python
def DO_cmdOverflowHook(self, opCode, cmdSeq):
    self.cmdResponse_out(opCode, cmdSeq, fprime_py.Fw.CmdResponse(fprime_py.Fw.CmdResponse.T.BUSY))
```

An exception raised in a hook is not caught by the generated C++, as for any handler (see [Strings](#strings)), but
here it reaches the caller's thread.

### State Machines

A component may instantiate internal state machines: ones whose actions, guards, signals and states are defined in
FPP. Take this one, instantiated twice:

```
module Ref {
    state machine Blinker {
        action store: U32
        guard allow: U32
        signal advance: U32
        signal back
        initial enter IDLE
        state IDLE { on advance if allow do { store } enter BUSY }
        state BUSY { on back enter IDLE }
    }

    @ fprime-python
    queued component PySm {
        ...
        state machine instance first: Blinker
        state machine instance second: Blinker
    }
}
```

Each action and guard is a Python handler, named as F Prime names it after the machine's flattened qualified name:
`Ref_Blinker_action_store(self, smId, signal, value)` and `Ref_Blinker_guard_allow(self, smId, signal, value)` for a
machine `Ref.Blinker`. Every handler takes `smId` and `signal`; one whose action or guard declares a type also takes
the signal's `value`. The handlers belong to the machine, not to an instance, so `first` and `second` call the same
ones, and `smId` says which: it is an `enum.Enum` bound inside the component's class, `fprime_py.Ref.PySm.SmId`, with
one value per instance named after it (`smId.name == "first"`). A guard is `const` in C++ and must return a `bool`;
anything else, `None` included, raises `TypeError`. The template's guard stubs return `False`, which leaves the guarded
transition untaken. Every action and guard must be implemented: a missing one raises `AttributeError` from the
generated `init`.

Python drives each instance through the methods F Prime generates for it:

- `first_sendSignal_advance(value)` and `first_sendSignal_back()` queue a signal on the component's queue. A string
  value is checked first against the size F Prime serializes it at: its declared size, else
  `FW_FIXED_LENGTH_STRING_SIZE`. On a full queue the instance's queue-full behavior applies: `assert` (the default)
  asserts, `drop` drops the signal, and `block` waits for room with the GIL released, so the dispatching thread can run
  the handlers that make it. Never send to a `block` instance from the thread that dispatches its queue (any action or
  guard, or on a queued component the code that calls `doDispatch`): on a full queue that send waits forever.
- `first_getState()` returns the current state as a `fprime_py.Ref.Blinker_State`, an F Prime enumeration whose `e`
  is a `Blinker_State.T`, e.g. `Blinker_State.T.IDLE`.

The machine's states and signals are bound once, into the Python module of the FPP module defining the machine, as
`Blinker_State`, an F Prime enumeration class whose values are in `Blinker_State.T`, and `Blinker_Signal`, an
`enum.Enum` of the values `signal` takes, in the order of their numbers. A machine defined inside a component
is named as F Prime names it, with the component folded in: `PySm_Local_State` and `PySm_Local_Signal` in the
component's module. Both enumerations include F Prime's internal entries, because Python can see them:
`Blinker_State.T.__FPRIME_UNINITIALIZED` is the state before the machine starts, and an action on the initial
transition receives `Blinker_Signal.__FPRIME_INITIAL_TRANSITION`. Inside a class body Python mangles such names, so
spell them `Blinker_Signal["__FPRIME_INITIAL_TRANSITION"]` there.

- **Thread.** Actions and guards run on the thread dispatching the component's queue, holding the GIL: the
  component's own thread when it is active, and whatever calls `doDispatch` or `dispatchAvailableMessages` when it is
  queued. `sendSignal` only queues the signal, and the transition happens when the queue is next dispatched.
- **Initial transition.** The actions and guards of the initial transition run during the component's `init`, on the
  thread setting up the topology, before the component's queue is created and before its ports are connected. They
  must not send signals or invoke ports; they may only set up Python state.
- **Exceptions.** An exception raised in an action or guard is not caught by the generated C++, as for any handler
  (see [Strings](#strings)). One raised on the initial transition propagates out of the component's `init`.
- **Instances defined elsewhere.** A machine defined inside another component is bound only with that component, so
  it is rejected; define it in a module instead.

## Setting a Deployment Up With Python Bindings

The deployment topology that instantiates Python components must also carry the `@ fprime-python` annotation. Only an
annotated topology gets the `setup` and `teardown` bindings and the `Instances` handles that the Python runner uses to
start the deployment. A deployment topology that instantiates `@ fprime-python` components without the annotation is
rejected with an error naming the topology.

```
@ fprime-python
deployment topology MyDeployment {
    ...
}
```

An annotated topology must be a `deployment topology`: the binding calls the topology's setup and teardown, and
F Prime only generates those for a deployment.

> [!CAUTION]
> The `<component>.template.py` is updated on every build unlike F Prime implementation templates.

To include the component in the built python package, add the final Python file to the `SOURCES` list.

```cmake
register_fprime_module(
    AUTOCODER_INPUTS
        "${CMAKE_CURRENT_LIST_DIR}/MyComponent.fpp" # Has annotated component
    SOURCES
        "${CMAKE_CURRENT_LIST_DIR}/MyComponent.py" # Has Python implementation
)
```

## F Prime Data Types

Modeled types are available to Python. These types are under the namespace module `fprime_python` and then under their
respective F Prime namespaces. For example, `import fprime_python.Fw.Time.Time` will import the `Fw::Time` type that
lives under `#include "Fw/Time/Time.hpp`.

```python
from fprime_python.Fw.Time import Time
fw_time_object = Time()
```

Struct members are available as properties and as the autocoded `get_<member>()`/`set_<member>()` functions. Members
declared as inlined arrays (e.g. `rgb: [768] U8`) are copied: reading one returns a new `list` of the elements and
writing one accepts a sequence of elements (`list`, `tuple`, `bytes` for integer elements, ...) of exactly the declared
length. Elements use the same Python representation as scalar members of that type (`str` for strings; `<Enum>.T` for
enumerations). A wrong length raises `ValueError`; an element that cannot be
converted raises `TypeError` and leaves the member unchanged.

```python
palette.rgb = bytes(768)   # or palette.set_rgb([...])
red = palette.rgb[0]       # or palette.get_rgb()[0]
palette.rgb[0] = 255       # modifies the copy only: assign the whole sequence instead
```

Because the list is a copy, element assignment does not write through to the struct. This differs from members whose
type is an FPP `array`, which are bound by reference and can be modified in place.

### Strings

A Python `str` copied into an F Prime string must fit that string's storage and contain no NUL characters, or it raises
`ValueError` rather than being stored truncated. Storage is counted in bytes of UTF-8 encoding, so check
`len(s.encode())`, not `len(s)`: a `string size 8` holds at most 8 bytes.

- Struct members, array elements, inline array elements, the string arguments of output ports and internal ports,
  and strings returned from a Python port handler are checked against their declared `string size`.
- Event string arguments and telemetry channels are checked against the smaller of their size (declared, or
  `FW_FIXED_LENGTH_STRING_SIZE` by default) and `FW_LOG_STRING_MAX_SIZE` or `FW_TLM_STRING_MAX_SIZE`, the sizes
  F Prime serializes them at. With the default configuration that is 200 bytes for an event string and 40 bytes for a
  telemetry string, even one with no declared size; F Prime itself would truncate the excess.
- Every string is also checked against the capacity of the F Prime string class that carries it, which is the only
  bound on a port string with no declared size: `FW_FIXED_LENGTH_STRING_SIZE` for port strings and
  `FW_INTERNAL_INTERFACE_STRING_MAX_SIZE` for internal ports.

A `ValueError` raised in a Python handler, such as a port handler returning a `str` that is too long, is not caught by
the generated C++. When an F Prime thread made the call it ends the process; when Python code started the call it
reaches that code, but any guarded input port it passed through is left locked, so the next call to that port blocks
forever. Do not catch such an error and carry on; check string lengths in Python where the input is not trusted.

## Development

Install the autocoder and its check dependencies into a virtual environment, then run the type check and the
generator tests:

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m mypy
.venv/bin/python -m pytest tests
```

## TODO: custom bindings

## TODO: Deployments