""" fprime_python.include:

Works out the include path of the header F Prime's autocoder generates for a given FPP definition.

F Prime generates its headers into the build cache under a path that mirrors the defining `.fpp` file's
path relative to a build location, so the include path of a definition's header is that relative
directory plus a file name derived from the definition's kind. This module is constructed around the
project's build locations and resolves definitions against them.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional, Type

import fpp


class IncludeError(Exception):
    """ The include path of a definition's generated header could not be determined """


class IncludeManager(object):
    """ Manages the include paths for generated C++ code based on provided prefixes

    Prefixes are the build locations of the project: the framework, library and project roots that
    F Prime mirrors into the build cache. Include paths are relative to the closest enclosing prefix.
    """

    #: The file-name suffix F Prime's autocoder appends per kind of definition. The suffix does not
    #: follow from the symbol class name -- a struct's header is "SerializableAc.hpp" -- so the kinds
    #: with a generated header are listed, and a symbol of any other kind is an error.
    symbol_type_to_include_type_name: Dict[Type[fpp.Symbol], str] = {
        fpp.Symbol.AliasType: "Alias",
        fpp.Symbol.ArrayType: "Array",
        fpp.Symbol.Component: "Component",
        fpp.Symbol.Constant: "Constant",
        fpp.Symbol.EnumType: "Enum",
        fpp.Symbol.Port: "Port",
        fpp.Symbol.StructType: "Serializable",
        fpp.Symbol.Topology: "Topology",
    }

    def __init__(
        self,
        prefixes: Iterable[Path],
        prefix_working_directory: Optional[Path] = None,
    ) -> None:
        """ Initialize the IncludeManager

        Args:
            prefixes: Build locations that include paths are relative to
            prefix_working_directory: Directory that relative prefixes are relative to
                (default: the current working directory)
        """
        working_directory = Path.cwd() if prefix_working_directory is None else prefix_working_directory
        self.prefixes = [(working_directory / prefix).resolve() for prefix in prefixes]

    def get_include_path(self, symbol: fpp.Symbol.Variant) -> str:
        """ Determine the include path of the header F Prime generates for a definition

        Args:
            symbol: The symbol of the definition whose generated header is wanted
        Returns:
            The include path, e.g. "Ref/PyActiveComponentAc.hpp"
        Raises:
            IncludeError: The definition is of a kind with no generated header, or was defined
                outside every build location
        """
        try:
            type_name = self.symbol_type_to_include_type_name[type(symbol)]
        except KeyError:
            raise IncludeError(
                f"Unsupported symbol type for include path determination: {type(symbol).__name__}"
            ) from None

        directory = Path(symbol.definition.location.uri).resolve().parent

        possible_include_paths = [
            directory.relative_to(prefix)
            for prefix in self.prefixes
            if directory.is_relative_to(prefix)
        ]
        if not possible_include_paths:
            raise IncludeError(
                f"{symbol.qualified_name} is defined in {directory}, which is under none of the build "
                f"locations {[str(prefix) for prefix in self.prefixes]}"
            )
        # The closest enclosing prefix wins, which is the relative path with the fewest components
        possible_include_paths.sort(key=lambda path: len(path.parents))
        file_name = f"{symbol.unqualified_name}{type_name}Ac.hpp"
        # A definition at the root of a build location has no directory to name
        if possible_include_paths[0] == Path("."):
            return file_name
        return f"{possible_include_paths[0].as_posix()}/{file_name}"

    def get_sibling_path(self, symbol: fpp.Symbol.Variant, file_name: str) -> str:
        """ Determine the include path of a file alongside a definition's generated header

        The files this autocoder generates land next to the ones F Prime generates, so their include
        paths share a directory with them.

        Args:
            symbol: The symbol of the definition whose directory is wanted
            file_name: Name of the file in that directory
        Returns:
            The include path of that file
        Raises:
            IncludeError: The include path of the definition's own header could not be determined
        """
        return (Path(self.get_include_path(symbol)).parent / file_name).as_posix()
