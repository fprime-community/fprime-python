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

Every port, command, event, telemetry channel, parameter and internal port of the component is bound. Four
component features cannot be bound yet, because F Prime declares a handler for each that has no Python equivalent:

| Feature | Why | What happens |
| --- | --- | --- |
| serial port | its handler takes a serialization buffer | rejected with an error naming the port |
| state machine instance | its actions and guards take a state machine id and a signal | rejected with an error naming the component |
| data product container | its handler takes a `Fw::DpContainer` | rejected with an error naming the component |
| `hook` queue-full behavior | its overflow hook takes the message that could not be queued | rejected with an error naming the component |

In each case the autocoder refuses rather than generating a class that would leave the handler unimplemented and
fail to link. Drop the `@ fprime-python` annotation to implement such a component in C++ instead.

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
  F Prime serializes them at.
- Every string is also checked against the capacity of the F Prime string class that carries it, which is the only
  bound on a port string with no declared size: `FW_FIXED_LENGTH_STRING_SIZE` for port strings and
  `FW_INTERNAL_INTERFACE_STRING_MAX_SIZE` for internal ports.

A `ValueError` raised in a Python handler, such as a port handler returning a `str` that is too long, is not caught by
the generated C++ and ends the process. Check string lengths in Python where the input is not trusted.

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