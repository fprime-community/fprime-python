""" fprime_python.model:

Loads the FPP model that the bindings are generated from.

The model is parsed and analyzed in-process by `fpp.analyze`, so there is no intermediate JSON model to
generate first. What `fpp.analyze` needs is the complete set of FPP files the model is made of: the
module's own translation units, plus the transitive closure of everything they reference. F Prime's FPP
autocoder already computes that closure with `fpp-depend` and leaves it in the module's build cache, so
this module reads it from there.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List

import fpp


#: fpp-depend writes the module's transitive FPP closure here, one path per line. It is produced by
#: F Prime's `fpp_depend` sub-build, which runs before any autocoder does, so it is always on disk.
IMPORT_LIST_PATH = Path("fpp-cache") / "stdout.txt"

#: F Prime's FPP autocoder writes the module's own FPP sources here, as a CMake ";"-separated list
SOURCE_LIST_PATH = Path("fpp-source-list")


class ModelError(Exception):
    """ The FPP model could not be loaded """


def read_path_list(path: Path) -> List[Path]:
    """ Read a list of FPP paths out of the build cache

    fpp-depend writes one path per line and CMake writes ";"-separated lists. Both separators are
    accepted so that a single reader handles either file.

    Args:
        path: File to read the list from
    Returns:
        The paths listed in the file, in the order listed
    Raises:
        ModelError: The file does not exist
    """
    if not path.is_file():
        raise ModelError(
            f"Required FPP file list {path} does not exist. Has the fpp autocoder run for this module?"
        )
    entries = re.split(r"[;\r\n]+", path.read_text(encoding="utf-8"))
    return [Path(entry.strip()) for entry in entries if entry.strip()]


def deduplicate(paths: Iterable[Path], *, exclude: Iterable[Path] = ()) -> List[Path]:
    """ Drop repeated paths, keeping the first occurrence

    A translation unit may appear twice in one list, or appear both in the module's own sources and in
    another module's dependency closure. Passing it to `fpp.analyze` twice would analyze it as two
    translation units and report every definition in it as a duplicate, so the lists are reduced first.

    Args:
        paths: Paths to deduplicate
        exclude: Paths to drop entirely, whether or not they are repeated
    Returns:
        The paths with repeats and exclusions removed, in first-seen order
    """
    seen = {path.resolve() for path in exclude}
    unique = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def load_model(sources: Iterable[Path], imports: Iterable[Path]) -> fpp.Model:
    """ Parse and analyze the FPP model made up of the given sources and imports

    The two are kept apart the way `fpp-to-cpp` keeps them apart: the sources are the translation units
    this module generates for, and the imports are present only to resolve references out of them. fpp
    records the split on the model, so a definition reached during generation answers whether it came
    from a source; see `visitor.AnnotatedDefinitionVisitor`.

    Args:
        sources: The module's own translation units
        imports: Every other FPP file needed to resolve them
    Returns:
        The analyzed model
    Raises:
        ModelError: A listed file is missing, or the model does not analyze cleanly
    """
    source_paths = deduplicate(sources)
    # A unit that is both a source and an import is a source: it is one of the units generated for, and
    # analyzing it twice would report every definition in it as a duplicate
    import_paths = deduplicate(imports, exclude=source_paths)
    missing = [path for path in source_paths + import_paths if not path.is_file()]
    if missing:
        raise ModelError(
            "FPP files listed in the model do not exist:\n"
            + "\n".join(f"  {path}" for path in missing)
        )
    model = fpp.analyze(
        [str(path) for path in source_paths], imports=[str(path) for path in import_paths]
    )
    if model.has_errors:
        raise ModelError(
            f"FPP model has {model.error_count} error(s):\n"
            + "\n".join(f"  {diagnostic.display}" for diagnostic in model.diagnostics)
        )
    return model
