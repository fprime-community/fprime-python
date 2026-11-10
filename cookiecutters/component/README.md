# F Prime Python Component Cookiecutter

Stamps out a component implemented in Python: an FPP model annotated `@ fprime-python`, the Python implementation,
and the `CMakeLists.txt` that registers both. Run it from the directory that should hold the new component, giving
the path to this directory:

```bash
fprime-util new --from-source <path to fprime-python>/cookiecutters/component
```

The new component has one command, one event and one telemetry channel as place-holders.
