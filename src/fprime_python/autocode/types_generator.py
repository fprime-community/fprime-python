""" fprime_python.types_generator:

Generators for three FPP types: enums, structs, and arrays. FPP types are mapped into Python but not the
other way around, so only the pybind11 C++ bindings need generating for them.
"""
from __future__ import annotations

from typing import List, Tuple

import fpp
from fprime_cpp_codegen import Body

from .binding_generator import BindingGenerator, expression_chain
from .cpp_types import StringClass, struct_member_getter, type_name
from .include import IncludeManager
from .names import flat_name
from .view import StateMachineView


class ArrayBindingGenerator(BindingGenerator):
    """ Generator for FPP array bindings into Python

    An F Prime array is a fixed-size C++ class with an `operator[]` and a `SIZE` constant, so it is bound
    as a Python sequence: a default constructor, `__getitem__`, `__setitem__`, and the size exposed both
    as `size` and as `SIZE`. Bounds are checked in the binding because a C++ `operator[]` will happily
    run off the end of the array where Python expects an `IndexError`.

    Example Output:
    ```cpp
    pybind11::class_<Ref::PyArray>(m, "PyArray")
        .def(pybind11::init<>())
        .def("__getitem__", [](const Ref::PyArray &a, int index) {
            if (index < 0 || static_cast<FwSizeType>(index) >= Ref::PyArray::SIZE) {
                throw std::out_of_range("array index out of bounds");
            }
            return a[index];
        }, pybind11::is_operator())
        ...
    ```
    """

    def __init__(
        self, include_manager: IncludeManager, symbol: fpp.Symbol.Variant, array_type: fpp.Type.Array
    ) -> None:
        """ Initialize the generator for one array definition

        Args:
            include_manager: Resolves the include paths of the headers the binding needs
            symbol: The symbol of the array being bound
            array_type: The semantic type of the array being bound
        """
        super().__init__(include_manager, symbol)
        self.array_type = array_type

    #: Bounds-checked accessor bound as one of Python's subscript operators. The index arrives from Python as
    #: a signed int and F Prime's own subscript asserts on an out-of-range one, which would abort the
    #: process, so the bound is checked at both ends before the array is touched.
    SUBSCRIPT_TEMPLATE = """.def("{python_name}", []({signature}) {{
    if (index < 0 || static_cast<FwSizeType>(index) >= {fqn}::SIZE) {{
        throw std::out_of_range("array index out of bounds");
    }}
    {statement}
}}, pybind11::is_operator())"""

    #: The array's size, exposed as a class attribute
    SIZE_TEMPLATE = """.def_property_readonly_static("{python_name}", [](pybind11::object /* cls */) {{
    return {fqn}::SIZE;
}})"""

    @property
    def has_string_elements(self) -> bool:
        """ Whether the array's elements are modeled strings

        F Prime makes such an array's `ElementType` a `Fw::ExternalString`, a view onto storage inside the
        array. It cannot be copied, so the element crosses into Python as a `std::string` instead.
        """
        return isinstance(self.array_type.anon_array.elt_type.underlying_type, fpp.Type.String)

    def bind(self, body: Body) -> None:
        """ Write the pybind11 statements binding this array """
        fqn = self.cpp_fqn
        if self.has_string_elements:
            getter, setter_value, setter = (
                "return std::string(array[index].toChar());",
                "const std::string &value",
                "FprimePython::check_string_fits(value, array[index].getCapacity());\n"
                "    array[index] = value.c_str();",
            )
        else:
            getter, setter_value, setter = (
                "return array[index];",
                f"const {fqn}::ElementType &value",
                "array[index] = value;",
            )
        links = [
            ".def(pybind11::init<>())",
            self.SUBSCRIPT_TEMPLATE.format(
                python_name="__getitem__",
                signature=f"const {fqn} &array, int index",
                statement=getter,
                fqn=fqn,
            ),
            self.SUBSCRIPT_TEMPLATE.format(
                python_name="__setitem__",
                signature=f"{fqn} &array, int index, {setter_value}",
                statement=setter,
                fqn=fqn,
            ),
        ]
        # F Prime spells the size SIZE; Python code reads more naturally with a lower-case alias, so both
        # are exposed.
        links += [
            self.SIZE_TEMPLATE.format(python_name=python_name, fqn=fqn)
            for python_name in ("size", "SIZE")
        ]
        body.raw(expression_chain(f'pybind11::class_<{fqn}>(m, "{self.name}")', links))

    def cpp_system_includes(self) -> List[str]:
        """ Get any system includes required by this type generator """
        # std::out_of_range, thrown when a Python index runs past the end of the array
        includes = ["stdexcept"]
        if self.has_string_elements:
            includes.append("string")
        return includes


class EnumBindingGenerator(BindingGenerator):
    """ Generator for FPP enum bindings into Python

    An F Prime enumeration is a class wrapping a nested `T` enumeration, so both are bound: the wrapper as
    a class holding its `e` member, and `T` as a `pybind11::native_enum` so that it arrives in Python as a
    real `enum.Enum`.

    Example Output:
    ```cpp
    pybind11::class_<Ref::PyEnum> enumeration(m, "PyEnum");
    enumeration.def_readwrite("e", &Ref::PyEnum::e);

    pybind11::native_enum<Ref::PyEnum::T>(enumeration, "T", "enum.Enum")
        .value("A", Ref::PyEnum::A)
        ...
        .export_values()
        .finalize();

    enumeration.def(pybind11::init<Ref::PyEnum::T>());
    ```
    """

    def __init__(
        self, include_manager: IncludeManager, symbol: fpp.Symbol.Variant, enum_type: fpp.Type.Enum
    ) -> None:
        """ Initialize the generator for one enum definition

        Args:
            include_manager: Resolves the include paths of the headers the binding needs
            symbol: The symbol of the enumeration being bound
            enum_type: The semantic type of the enumeration being bound
        """
        super().__init__(include_manager, symbol)
        self.enum_type = enum_type

    def bind(self, body: Body) -> None:
        """ Write the pybind11 statements binding this enumeration """
        write_enum_wrapper(body, self.cpp_fqn, self.name, [constant.name for constant in self.enum_type.node.constants])

    def cpp_system_includes(self) -> List[str]:
        """ Get any system includes required by this type generator """
        return ["pybind11/native_enum.h"]


def write_enum_wrapper(body: Body, fqn: str, python_name: str, constants: List[str]) -> None:
    """ Write the pybind11 statements binding one F Prime enumeration class and its nested `T`

    Args:
        body: The body of the initialization function to write the statements into
        fqn: The C++-qualified name of the enumeration class
        python_name: The name the class is bound into the module `m` under
        constants: The names of the enumeration's constants
    """
    # The C++ name comes from the model, so this is not margin-stripped
    body.lines(
        f'pybind11::class_<{fqn}> enumeration(m, "{python_name}");\n'
        f'enumeration.def_readwrite("e", &{fqn}::e);',
        margin=None,
    )
    body.blank()
    # `native_enum` has to be finalized before anything else touches the enclosing scope, so the
    # value chain is emitted as one statement of its own.
    body.raw(
        expression_chain(
            f'pybind11::native_enum<{fqn}::T>(enumeration, "T", "enum.Enum")',
            [f'.value("{constant}", {fqn}::{constant})' for constant in constants]
            + [".export_values()", ".finalize()"],
        )
    )
    body.blank()
    # Constructing the wrapper from one of its own values is the natural Python spelling, and can
    # only be bound once T exists.
    body.lines(f"enumeration.def(pybind11::init<{fqn}::T>());", margin=None)


class StateMachineBindingGenerator(BindingGenerator):
    """ Generator for the bindings of an internal state machine's states and signals into Python

    F Prime generates the states as an ordinary enumeration class, `<Machine>_State`, which is bound the way
    any other enumeration is, and the signals as an `enum class Signal` nested in `<Machine>StateMachineBase`,
    which is bound as a `pybind11::native_enum` named `<Machine>_Signal` beside it. A machine is bound once,
    by the module defining it, however many components instantiate it: pybind11 refuses to register a type
    twice.

    Example Output:
    ```cpp
    pybind11::class_<Ref::Blinker_State> enumeration(m, "Blinker_State");
    ...
    pybind11::native_enum<Ref::BlinkerStateMachineBase::Signal>(m, "Blinker_Signal", "enum.Enum")
        .value("__FPRIME_INITIAL_TRANSITION", Ref::BlinkerStateMachineBase::Signal::__FPRIME_INITIAL_TRANSITION)
        .value("advance", Ref::BlinkerStateMachineBase::Signal::advance)
        .finalize();
    ```
    """

    FILE_BASE_SUFFIX = "StateMachineBindingAc"
    INVOCATION_SUFFIX = "StateMachineBinding"

    def __init__(self, include_manager: IncludeManager, machine: StateMachineView) -> None:
        """ Initialize the generator for one internal state machine

        Args:
            include_manager: Resolves the include paths of the headers the binding needs
            machine: The state machine being bound
        """
        super().__init__(include_manager, machine.symbol)
        self.machine = machine

    @property
    def name(self) -> str:
        """ The state machine's name within its module, which F Prime names its files after """
        return self.machine.base_name

    @property
    def cpp_fqn(self) -> str:
        """ The C++-qualified name of the state machine base class """
        return self.machine.base_class

    @property
    def doc_name(self) -> str:
        """ The bindings are of the machine's states and signals rather than of its base class """
        return f"the states and signals of {self.machine.fpp_name}"

    @property
    def doc_subject(self) -> str:
        """ The bindings are of the machine's states and signals rather than of its base class """
        return f"the states and signals of the FPP state machine {self.machine.fpp_name}"

    @property
    def scope(self) -> str:
        """ The module the state machine's C++ names live in, even when it is defined inside a component """
        return self.machine.scope

    @property
    def init_function_name(self) -> str:
        """ The initialization function's name, kept apart from that of a type or component of the same name """
        return f"init_{flat_name(self.fpp_name)}_StateMachine"

    @property
    def include_guard(self) -> str:
        """ The include guard of the generated header """
        return f"FPRIME_PYTHON_{flat_name(self.fpp_name)}_STATE_MACHINE_HPP"

    def cpp_includes(self) -> List[str]:
        """ The generated header, and the state machine header F Prime generates, which includes its states """
        return [
            self.include_manager.get_sibling_path(self.symbol, f"{self.file_base}.hpp"),
            self.include_manager.get_sibling_path(self.symbol, self.machine.header_name),
        ]

    def bind(self, body: Body) -> None:
        """ Write the pybind11 statements binding the state machine's states and signals """
        machine = self.machine
        write_enum_wrapper(body, machine.state_type, machine.state_python_name, machine.state_constants)
        body.blank()
        # Bound straight into the module, so its values are not exported: they would land beside every other
        # definition of the module, where the signals of two machines could collide
        body.raw(
            expression_chain(
                f'pybind11::native_enum<{machine.signal_type}>(m, "{machine.signal_python_name}", "enum.Enum")',
                [f'.value("{signal}", {machine.signal_type}::{signal})' for signal in machine.signal_constants]
                + [".finalize()"],
            )
        )

    def cpp_system_includes(self) -> List[str]:
        """ Get any system includes required by this generator """
        return ["pybind11/native_enum.h"]


#: Cast picking one struct member getter overload: const when it returns by value, non-const otherwise
GETTER_STATIC_CAST_TEMPLATE = "static_cast<{field_type} ({fqn}::*)(){const_qualifier}>"

#: Property and explicit accessors bound for one struct member
STRUCT_MEMBER_TEMPLATE = """.def_property("{name}", {getter_cast}(&{fqn}::get_{name}), &{fqn}::set_{name})
.def("get_{name}", {getter_cast}(&{fqn}::get_{name}))
.def("set_{name}", &{fqn}::set_{name})"""

#: Setter of a string member. F Prime's own setter copies into the member's fixed-capacity storage and drops
#: whatever does not fit, so the length is checked against that storage first.
STRUCT_STRING_SETTER_TEMPLATE = """[]({fqn}& self, const pybind11::str& value) {{
    const std::string text = value.cast<std::string>();
    FprimePython::check_string_fits(text, self.get_{name}().getCapacity());
    self.get_{name}() = text.c_str();
}}"""

#: Property and explicit accessors bound for one string struct member
STRUCT_STRING_MEMBER_TEMPLATE = """.def_property("{name}", {getter_cast}(&{fqn}::get_{name}), {setter})
.def("get_{name}", {getter_cast}(&{fqn}::get_{name}))
.def("set_{name}", {setter})"""

#: Getter of an inline array member, copying the elements out into a new Python list
STRUCT_INLINE_ARRAY_GETTER_TEMPLATE = """[](const {fqn}& self) {{
    pybind11::list items;
    for (const auto& item : self.get_{name}()) {{
        items.append({element_to_python});
    }}
    return items;
}}"""

#: Setter of an inline array member, copying the elements of any sequence of exactly the right length in.
#: The sequence is indexed over [0, size) rather than iterated, so one whose length changes under the
#: setter cannot over- or under-fill the array.
STRUCT_INLINE_ARRAY_SETTER_TEMPLATE = """[]({fqn}& self, const pybind11::sequence& items) {{
    constexpr std::size_t size = std::extent<{fqn}::Type_of_{name}>::value;
    if (pybind11::len(items) != size) {{
        throw pybind11::value_error("{name} requires exactly " + std::to_string(size) + " elements");
    }}
    // Convert every element before writing so a failed conversion leaves the member unchanged
    std::vector<{element_cpp_type}> converted;
    converted.reserve(size);
    for (std::size_t i = 0; i < size; i++) {{
        try {{
            converted.push_back(items[i].cast<{element_cpp_type}>());
        }} catch (const pybind11::cast_error&) {{
            throw pybind11::type_error("{name}[" + std::to_string(i) + "] is not convertible to {element_python_type}");
        }}{element_check}
    }}
    for (std::size_t i = 0; i < size; i++) {{
        self.get_{name}()[i] = {element_from_cpp};
    }}
}}"""

#: Property and explicit accessors bound for one inline array struct member
STRUCT_INLINE_ARRAY_MEMBER_TEMPLATE = """.def_property("{name}", {getter}, {setter})
.def("get_{name}", {getter})
.def("set_{name}", {setter})"""


class StructBindingGenerator(BindingGenerator):
    """ Generator for FPP struct bindings into Python

    An F Prime struct is a C++ class with a getter/setter pair per member, so it is bound as a class with
    a default constructor and, per member, a Python property plus the explicit accessors.

    The generated getters are overloaded on constness for every member that is returned by reference, so
    referring to one needs a cast to pick an overload; the bindings use the non-const getter.

    Struct members that are inline arrays (e.g. `rgb: [768] U8`) are C arrays in the generated C++, which
    have no Python counterpart. They are bound by value instead: the getter copies the elements into a
    list and the setter copies the elements of any sequence of the right length (a list, tuple, bytes,
    ...) into the array. Elements cross the boundary the same way scalar members of the same type do:
    strings as `str`, enumerations as the `T` enumeration.

    Example Output:
    ```cpp
    pybind11::class_<Ref::PySimple>(m, "PySimple")
        .def(pybind11::init<>())
        .def_property("x", static_cast<U32 (Ref::PySimple::*)() const>(&Ref::PySimple::get_x),
                      &Ref::PySimple::set_x)
        .def("get_x", static_cast<U32 (Ref::PySimple::*)() const>(&Ref::PySimple::get_x))
        .def("set_x", &Ref::PySimple::set_x)
        ...
    ```
    """

    def __init__(
        self, include_manager: IncludeManager, symbol: fpp.Symbol.Variant, struct_type: fpp.Type.Struct
    ) -> None:
        """ Initialize the generator for one struct definition

        Args:
            include_manager: Resolves the include paths of the headers the binding needs
            symbol: The symbol of the struct being bound
            struct_type: The semantic type of the struct being bound
        """
        super().__init__(include_manager, symbol)
        self.struct_type = struct_type

    @property
    def has_inline_arrays(self) -> bool:
        """ Whether any member is an inline array: the struct's `sizes` map holds an entry for each """
        return bool(self.struct_type.sizes)

    @property
    def has_string_members(self) -> bool:
        """ Whether any member is a string, whose setter is bound through a length-checking lambda """
        return any(
            isinstance(member_type.underlying_type, fpp.Type.String)
            for _, member_type in self.struct_type.anon_struct.members
        )

    def scalar_member(self, name: str, member_type: fpp.Type.Variant) -> str:
        """ The bindings of one member that is not an inline array

        Args:
            name: The name of the member
            member_type: The type of the member
        Returns:
            The chained pybind11 calls binding the member
        """
        field_type, is_const = struct_member_getter(member_type)
        getter_cast = GETTER_STATIC_CAST_TEMPLATE.format(
            field_type=field_type,
            fqn=self.cpp_fqn,
            const_qualifier=" const" if is_const else "",
        )
        if isinstance(member_type.underlying_type, fpp.Type.String):
            setter = STRUCT_STRING_SETTER_TEMPLATE.format(name=name, fqn=self.cpp_fqn)
            return STRUCT_STRING_MEMBER_TEMPLATE.format(
                name=name, fqn=self.cpp_fqn, getter_cast=getter_cast, setter=setter
            )
        return STRUCT_MEMBER_TEMPLATE.format(name=name, fqn=self.cpp_fqn, getter_cast=getter_cast)

    def inline_array_member(self, name: str, element_type: fpp.Type.Variant) -> str:
        """ The bindings of one member that is an inline array

        Elements are converted to and from Python one at a time, in the representation scalar members of the
        same type use. A string element is a `Fw::ExternalString`, which cannot be copied, so it is converted
        through `std::string`; an enumeration element is the enumeration class, so it is converted through
        its `T`.

        Args:
            name: The name of the member
            element_type: The type of the member's elements
        Returns:
            The chained pybind11 calls binding the member
        """
        fqn = self.cpp_fqn
        element_name = type_name(element_type, StringClass.STRUCT_MEMBER)
        element_check = ""
        if isinstance(element_type.underlying_type, fpp.Type.String):
            to_python, cpp_type, from_cpp, python_type = (
                "pybind11::str(item.toChar())", "std::string", "converted[i].c_str()", "str"
            )
            element_check = (
                f"\n        FprimePython::check_string_fits(converted[i], self.get_{name}()[i].getCapacity());"
            )
        elif isinstance(element_type.underlying_type, fpp.Type.Enum):
            to_python, cpp_type, from_cpp, python_type = (
                "pybind11::cast(item.e)",
                f"{element_name}::T",
                "converted[i]",
                f"{element_name.replace('::', '.')}.T",
            )
        else:
            to_python, cpp_type, from_cpp, python_type = (
                "pybind11::cast(item)",
                f"std::remove_extent<{fqn}::Type_of_{name}>::type",
                "converted[i]",
                element_name.replace("::", "."),
            )
        getter = STRUCT_INLINE_ARRAY_GETTER_TEMPLATE.format(
            name=name, fqn=fqn, element_to_python=to_python
        )
        setter = STRUCT_INLINE_ARRAY_SETTER_TEMPLATE.format(
            name=name,
            fqn=fqn,
            element_cpp_type=cpp_type,
            element_from_cpp=from_cpp,
            element_python_type=python_type,
            element_check=element_check,
        )
        return STRUCT_INLINE_ARRAY_MEMBER_TEMPLATE.format(name=name, getter=getter, setter=setter)

    def bind(self, body: Body) -> None:
        """ Write the pybind11 statements binding this struct """
        links = [".def(pybind11::init<>())"]
        # The semantic type lists its members in declaration order, which is the order F Prime declares
        # the accessors in.
        for name, member_type in self.struct_type.anon_struct.members:
            if name in self.struct_type.sizes:
                links.append(self.inline_array_member(name, member_type))
            else:
                links.append(self.scalar_member(name, member_type))
        body.raw(expression_chain(f'pybind11::class_<{self.cpp_fqn}>(m, "{self.name}")', links))

    def cpp_system_includes(self) -> List[str]:
        """ Get any system includes required by this type generator """
        if self.has_inline_arrays:
            return ["cstddef", "string", "type_traits", "vector"]
        if self.has_string_members:
            return ["string"]
        return []
