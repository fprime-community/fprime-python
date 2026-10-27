""" fprime_python.cpp_types:

Renders the C++ spelling of an FPP semantic type.

These spellings have to match F Prime's own autocoder exactly, because the generated component overrides
its handlers and the generated bindings take the address of its member functions. The rules F Prime uses
are:

 - a primitive is passed and returned by value, under its own name
 - everything else is passed by `const` reference and returned by value
 - a `ref` formal parameter is passed by non-const reference
 - an alias keeps its own name rather than resolving to the type it aliases, but is passed and returned
   according to the type it aliases

Strings are the exception, twice over. F Prime has no single string type and picks a different class per
context, so callers say which one they want; and an alias of a string is spelled as that class rather than as
the alias, because in FPP such an alias names a size and not a C++ type.
"""
from __future__ import annotations

import enum
from typing import Optional, Tuple

import fpp

from .names import cpp_name


class StringClass(enum.Enum):
    """ The C++ string class F Prime uses for a modeled string in each context

    A port or event argument arrives as the abstract `Fw::StringBase`, but a port *return* has to be a
    concrete owning string, so it is a `Fw::String`. A command argument is a `Fw::CmdStringArg`, an internal
    port argument a `Fw::InternalInterfaceString` because it is copied onto the component's queue, and a
    parameter value a `Fw::ParamString`. A struct member is a view onto storage held inside the struct, so it
    is a `Fw::ExternalString`.
    """
    PORT = "Fw::StringBase"
    PORT_RETURN = "Fw::String"
    COMMAND = "Fw::CmdStringArg"
    INTERNAL_PORT = "Fw::InternalInterfaceString"
    PARAMETER = "Fw::ParamString"
    STRUCT_MEMBER = "Fw::ExternalString"


class UnsupportedTypeError(Exception):
    """ An FPP type has no C++ spelling that this autocoder knows how to produce """


def type_name(type_: fpp.Type.Variant, string_class: StringClass) -> str:
    """ The C++ name of an FPP type, as declared

    Args:
        type_: The FPP semantic type to name
        string_class: The string class to use should this type, or the type it aliases, be a modeled string
    Returns:
        The C++ name of the type, e.g. "U32", "bool", "Ref::PySimple"
    Raises:
        UnsupportedTypeError: The type is anonymous and so cannot be named
    """
    # A modeled string has no C++ type of its own. An alias of one is spelled the same way, because such an
    # alias names a size rather than a type -- F Prime generates no header for it.
    if isinstance(type_.underlying_type, fpp.Type.String):
        return string_class.value
    # Arrays, enums, structs, aliases and abstract types are all named by their defining symbol. Using the
    # symbol keeps an alias spelled as the alias rather than as the type it aliases.
    symbol = type_.def_symbol
    if symbol is not None:
        return cpp_name(symbol.qualified_name)
    if isinstance(type_, fpp.Type.Boolean):
        return "bool"
    # Integers and floats name themselves through their kind, e.g. IntegerKind.U32 -> "U32"
    if isinstance(type_, (fpp.Type.PrimitiveInt, fpp.Type.Float)):
        return type_.value.name
    raise UnsupportedTypeError(
        f"FPP type {type_!r} is anonymous and has no C++ name; name it in the model to bind it"
    )


def value_type(type_: Optional[fpp.Type.Variant], string_class: StringClass) -> str:
    """ The C++ spelling of a type where it is passed or returned by value

    Args:
        type_: The FPP semantic type, or None for no type at all
        string_class: The string class to use should this type be a modeled string
    Returns:
        The by-value C++ spelling, or "void" when there is no type
    """
    if type_ is None:
        return "void"
    return type_name(type_, string_class)


def formal_parameter_type(param: fpp.ast.FormalParam, string_class: StringClass) -> str:
    """ The C++ spelling of a formal parameter, reference qualifiers included

    Args:
        param: The FPP formal parameter to spell
        string_class: The string class to use should the parameter be a modeled string
    Returns:
        The C++ parameter type, e.g. "U32", "const Ref::PySimple&", "Ref::PyComplex&"
    """
    type_ = param.type_name.resolved_type
    assert type_ is not None
    name = type_name(type_, string_class)
    if param.kind == fpp.ast.FormalParamKind.Ref:
        return f"{name}&"
    # `is_primitive` looks through aliases, so an alias of a primitive is passed by value under the
    # alias's own name, which is how F Prime's autocoder spells it.
    if type_.is_primitive:
        return name
    return f"const {name}&"


def struct_member_getter(type_: fpp.Type.Variant) -> Tuple[str, bool]:
    """ The return type of a generated struct member getter, and whether that getter is const

    F Prime generates one const getter returning by value for a member whose type is primitive or an
    enumeration, and a const/non-const overload pair returning a reference for everything else. The
    bindings use the non-const getter of a pair, so the pair has to be disambiguated by a cast, which is
    what the const flag is for.

    Args:
        type_: The FPP semantic type of the struct member
    Returns:
        A tuple of the getter's return type and whether the getter is const qualified
    """
    # An enumeration member is stored and returned as the enumeration's underlying `T`, not as the F Prime
    # enumeration class that wraps it. An alias of an enumeration is the same, under the alias's own name.
    if isinstance(type_.underlying_type, fpp.Type.Enum):
        return f"{type_name(type_, StringClass.STRUCT_MEMBER)}::T", True
    if type_.is_primitive:
        return type_name(type_, StringClass.STRUCT_MEMBER), True
    return f"{type_name(type_, StringClass.STRUCT_MEMBER)}&", False
