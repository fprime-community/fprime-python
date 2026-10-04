""" fprime_python.types_generator:

This file contains code generators for three FPP types: enums, structs, and arrays. Since FPP types are mapped into
Python, but not vise-versa, we only need to generate the pybind11 C++ bindings for these types.
"""
import itertools
from typing import List, Tuple

from fprime_python_model.fpp_ast.fpp_ast import Unqualified 
from fprime_python_model.semantics.types_values import Type, StructType, EnumType, ArrayType, StringType, AliasType


from .binding_generator import FppPybindBindingGenerator, In, STANDARD_INDENT


ARRAY_TEMPLATE = """
pybind11::class_<{fqn}>(m, "{unqualified_class_name}")
.def(pybind11::init<>())
.def("__getitem__", [](const {fqn} &a, int index) {{
{STANDARD_INDENT}if (index >= {fqn}::SIZE) {{
{STANDARD_INDENT}{STANDARD_INDENT}throw std::out_of_range("array index out of bounds");
{STANDARD_INDENT}}}
{STANDARD_INDENT}return a[index];
}}, pybind11::is_operator())
.def("__setitem__",
{STANDARD_INDENT}[]({fqn} &a, int index, const {fqn}::ElementType &value) {{
{STANDARD_INDENT}if (index >= {fqn}::SIZE) {{
{STANDARD_INDENT}{STANDARD_INDENT}throw std::out_of_range("array index out of bounds");
{STANDARD_INDENT}}}
{STANDARD_INDENT}a[index] = value;
}}, pybind11::is_operator())
.def_property_readonly_static("size", [](pybind11::object /* self */) {{
{STANDARD_INDENT}return {fqn}::SIZE;
}})
.def_property_readonly_static("SIZE", [](pybind11::object /* self */) {{
{STANDARD_INDENT}return {fqn}::SIZE;
}});
"""


class ArrayPybindCppGenerator(FppPybindBindingGenerator):
    """ Generator for FPP array bindings into Python

    This generator works on Analysis ArrayType objects and generates the necessary pybind11 C++ code to bind the
    array to Python. This includes a default constructor, a field-enumerated constructor, and getter/setter methods for
    each member of the array.

    The code will be wrapped in an initialization function taking a pybind11::module_& parameter such that the generated code
    can be placed outside of a single unified binding file. This work is performed by the superclass.

    Specifically, this type implements get_type_lines which generates the lines for the array definition itself.
    
    Example:
    ```python
    ArrayPybindCppGenerator().get_type_lines(array_type, model)
    ```

    Example Output:
    ```cpp
    void init_FprimePythonReference_PythonArray(pybind11::module_& m) {
        
        pybind11::class_<FprimePythonReference::PythonArray>(m, "PythonArray")
        .def(pybind11::init<>())
        .def("__getitem__", [](const FprimePythonReference::PythonArray &a, int index) {
            if (index >= FprimePythonReference::PythonArray::SIZE) {
                throw std::out_of_range("array index out of bounds");
            }
            return a[index];
        }, pybind11::is_operator())
        .def("__setitem__",
            [](FprimePythonReference::PythonArray &a, int index, const FprimePythonReference::PythonArray::ElementType &value) {
            if (index >= FprimePythonReference::PythonArray::SIZE) {
                throw std::out_of_range("array index out of bounds");
            }
            a[index] = value;
        }, pybind11::is_operator())
        .def_property_readonly_static("size", [](pybind11::object /* self */) {
            return FprimePythonReference::PythonArray::SIZE;
        })
        .def_property_readonly_static("SIZE", [](pybind11::object /* self */) {
            return FprimePythonReference::PythonArray::SIZE;
        });
    }
    """

    def get_type_lines(self, array_type: ArrayType, in_: In) -> List[str]:
        """ Generate the lines for the C++ binding file for an array type

        Array types require constructors and __getitem__/__setitem__ methods for each member. This function will
        generate those lines along with the necessary class definition.

        Args:
            array_type: The ArrayType object from the analysis' type map to generate lines for
            in_: input support tuple
        Returns:
            A list of strings representing the lines of C++ code for the array binding
        """
        fully_qualified_class_name = self.get_fully_qualified_cpp_name(array_type, in_)
        unqualified_class_name = self.get_unqualified_name(array_type, in_)

        return ARRAY_TEMPLATE.format(STANDARD_INDENT=STANDARD_INDENT,
            fqn=fully_qualified_class_name,
            unqualified_class_name=unqualified_class_name).splitlines()


FPP_ENUM_TEMPLATE = """
pybind11::class_<{fqn}> enumeration(m, "{unqualified_class_name}");
{STANDARD_INDENT}enumeration.def_readwrite("e", &{fqn}::e);

pybind11::native_enum<{fqn}::T>(enumeration, "T", "enum.Enum")
{STANDARD_INDENT}{values}
{STANDARD_INDENT}.export_values()
{STANDARD_INDENT}.finalize();

enumeration.def(pybind11::init<{fqn}::T>());
"""

FPP_ENUM_ENTRY_TEMPLATE = """.value("{enumeration}", {fqn}::{enumeration})"""


class EnumPybindCppGenerator(FppPybindBindingGenerator):
    """ Generator for FPP enum bindings into Python
    This generator works on Analysis EnumType objects and generates the necessary pybind11 C++ code to bind the
    enum to Python.
    
    The code will be wrapped in an initialization function taking a pybind11::module_& parameter such that the generated code
    can be placed outside of a single unified binding file. This work is performed by the superclass.

    Specifically, this type implements get_type_lines which generates the lines for the enum definition itself.

    Example:
    ```python
    EnumPybindCppGenerator().get_type_lines(enum_type, model)
    ```

    Example Output:
    ```cpp
    void init_FprimePythonReference_PythonEnumeration(pybind11::module_& m) {
        
        pybind11::class_<FprimePythonReference::PythonEnumeration> enumeration(m, "PythonEnumeration");
            enumeration.def_readwrite("e", &FprimePythonReference::PythonEnumeration::e);
        
        pybind11::native_enum<FprimePythonReference::PythonEnumeration::T>(enumeration, "T", "enum.Enum")
            .value("ENUMERATION_A", FprimePythonReference::PythonEnumeration::ENUMERATION_A)
            .value("ENUMERATION_B", FprimePythonReference::PythonEnumeration::ENUMERATION_B)
            .value("ENUMERATION_C", FprimePythonReference::PythonEnumeration::ENUMERATION_C)
            .export_values()
            .finalize();
        
        enumeration.def(pybind11::init<FprimePythonReference::PythonEnumeration::T>());
    }
    """

    def get_type_lines(self, enum_type: EnumType, in_: In) -> List[str]:
        """ Generate the lines for the C++ binding file for an enum node

        Enum types require enum value definitions attached to a pybind11::native_enum object. This function will generate
        those lines along with the class definition for the encompassing fprime enumeration class.

        Args:
            enum_type: The EnumType object from the analysis' type map to generate lines for
            in_: input support tuple
        """
        fully_qualified_class_name = self.get_fully_qualified_cpp_name(enum_type, in_)
        unqualified_class_name = self.get_unqualified_name(enum_type, in_)

        
        # Extract node(unannotated).data.constants[...].node(unannotated).data.name
        _, unannotated_node, _ = enum_type.node
        constants = [sub_unannotated_node.data.name for _, sub_unannotated_node, _ in unannotated_node.data.constants]

        value_lines = [
            FPP_ENUM_ENTRY_TEMPLATE.format(enumeration=member, fqn=fully_qualified_class_name)
            for member in constants
        ]

        return FPP_ENUM_TEMPLATE.format(STANDARD_INDENT=STANDARD_INDENT,
            fqn=fully_qualified_class_name,
            unqualified_class_name=unqualified_class_name,
            values=f"\n{STANDARD_INDENT}".join(value_lines)).splitlines()

    def get_cpp_includes(self, enum_type: EnumType, in_: In) -> List[str]:
        """ Get any includes required by this type generator """
        return super().get_cpp_includes(enum_type, in_) + [
            "#include <pybind11/native_enum.h>",
        ]

GETTER_STATIC_CAST_TEMPLATE = "static_cast<{field_type}{reference_qualifier} ({fqn}::*)() {const_qualifier}>"
SETTER_STATIC_CAST_TEMPLATE = "static_cast<void({fqn}::*)({const_qualifier} {field_type}{reference_qualifier})>"


STRUCT_TEMPLATE = """
pybind11::class_<{fqn}>(m, "{unqualified_class_name}")
{STANDARD_INDENT}.def(pybind11::init<>())
{STANDARD_INDENT}{member_getter_setter_lines};
"""
STRUCT_GETTER_SETTER_TEMPLATE = """
.def_property("{name}", {getter_static_caster}(&{fqn}::get_{name}),
                        &{fqn}::set_{name}
             )
.def("get_{name}", {getter_static_caster}(&{fqn}::get_{name}))
.def("set_{name}", &{fqn}::set_{name})
"""

# Struct members that are inlined arrays (e.g. `rgb: [768] U8`) are C arrays in the autocoded C++ and have no Python
# equivalent. They are bound by value: the getter copies the elements into a list and the setter copies the elements
# of any sequence of the right length (a list, tuple, bytes, ...) into the array. Elements cross the boundary the same
# way scalar members of the same type do: strings as `str`, enumerations as the `T` enumeration.
STRUCT_INLINE_ARRAY_GETTER_TEMPLATE = """[](const {fqn}& self) {{
    pybind11::list items;
    for (const auto& item : self.get_{name}()) {{
        items.append({element_to_python});
    }}
    return items;
}}"""
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
        }}
    }}
    for (std::size_t i = 0; i < size; i++) {{
        self.get_{name}()[i] = {element_from_cpp};
    }}
}}"""
STRUCT_INLINE_ARRAY_GETTER_SETTER_TEMPLATE = """
.def_property("{name}", {getter}, {setter})
.def("get_{name}", {getter})
.def("set_{name}", {setter})
"""

class StructPybindCppGenerator(FppPybindBindingGenerator):
    """ Generator for FPP struct bindings into Python
    
    This generator works on Analysis StructType objects and generates the necessary pybind11 C++ code to bind the
    struct to Python. This includes a default constructor, a field-enumerated constructor, and getter/setter methods for
    each member of the struct.

    The code will be wrapped in an initialization function taking a pybind11::module_& parameter such that the generated code
    can be placed outside of a single unified binding file. This work is performed by the superclass.

    Specifically, this type implements get_type_lines which generates the lines for the struct definition itself.
    
    Example:
    ```python
    StructPybindCppGenerator().get_type_lines(struct_type, model)
    ```

    Example Output:
    ```cpp
    void init_FprimePythonReference_PythonComplexStruct(pybind11::module_& m) {
        
        pybind11::class_<FprimePythonReference::PythonComplexStruct>(m, "PythonComplexStruct")
            .def(pybind11::init<>())
            
            .def_property("x", static_cast<U32 (FprimePythonReference::PythonComplexStruct::*)() const>(&FprimePythonReference::PythonComplexStruct::get_x),
                                    &FprimePythonReference::PythonComplexStruct::set_x
                        )
            .def("get_x", static_cast<U32 (FprimePythonReference::PythonComplexStruct::*)() const>(&FprimePythonReference::PythonComplexStruct::get_x))
            .def("set_x", &FprimePythonReference::PythonComplexStruct::set_x)
            
            .def_property("y", static_cast<Fw::ExternalString& (FprimePythonReference::PythonComplexStruct::*)() >(&FprimePythonReference::PythonComplexStruct::get_y),
                                    &FprimePythonReference::PythonComplexStruct::set_y
                        )
            .def("get_y", static_cast<Fw::ExternalString& (FprimePythonReference::PythonComplexStruct::*)() >(&FprimePythonReference::PythonComplexStruct::get_y))
            .def("set_y", &FprimePythonReference::PythonComplexStruct::set_y)
            
            .def_property("u", static_cast<FprimePythonReference::PythonSimpleStruct& (FprimePythonReference::PythonComplexStruct::*)() >(&FprimePythonReference::PythonComplexStruct::get_u),
                                    &FprimePythonReference::PythonComplexStruct::set_u
                        )
            .def("get_u", static_cast<FprimePythonReference::PythonSimpleStruct& (FprimePythonReference::PythonComplexStruct::*)() >(&FprimePythonReference::PythonComplexStruct::get_u))
            .def("set_u", &FprimePythonReference::PythonComplexStruct::set_u)
            
            .def_property("w", static_cast<FprimePythonReference::PythonArray& (FprimePythonReference::PythonComplexStruct::*)() >(&FprimePythonReference::PythonComplexStruct::get_w),
                                    &FprimePythonReference::PythonComplexStruct::set_w
                        )
            .def("get_w", static_cast<FprimePythonReference::PythonArray& (FprimePythonReference::PythonComplexStruct::*)() >(&FprimePythonReference::PythonComplexStruct::get_w))
            .def("set_w", &FprimePythonReference::PythonComplexStruct::set_w)
            
            .def_property("z", static_cast<FprimePythonReference::PythonEnumeration::T (FprimePythonReference::PythonComplexStruct::*)() const>(&FprimePythonReference::PythonComplexStruct::get_z),
                                    &FprimePythonReference::PythonComplexStruct::set_z
                        )
            .def("get_z", static_cast<FprimePythonReference::PythonEnumeration::T (FprimePythonReference::PythonComplexStruct::*)() const>(&FprimePythonReference::PythonComplexStruct::get_z))
            .def("set_z", &FprimePythonReference::PythonComplexStruct::set_z);
    }
    """

    def get_type_lines(self, struct_type: StructType, in_: In) -> List[str]:
        """ Generate the lines for the C++ binding file for a struct type
        
        Struct types require constructors and getter/setter methods for each member. This function will generate those
        lines along with the necessary class definition.

        Args:
            struct_type: The StructType object from the analysis' type map to generate lines for
            in_: input support tuple
        Returns:
            A list of strings representing the lines of C++ code for the struct binding
        """
        fully_qualified_class_name = self.get_fully_qualified_cpp_name(struct_type, in_)
        unqualified_class_name = self.get_unqualified_name(struct_type, in_)

        members = struct_type.anon_struct.members
        # The getter functions in the autocoded C++ are overloaded, so we need to generate static casts to resolve the
        # ambiguity when referring to the getter methods for the purposes of binding we use the non-const version of
        # the getters.
        #
        # Struct fields with inlined arrays are C arrays in the autocoded C++, which pybind11 cannot bind directly, so
        # they get lambdas copying the elements to and from a Python list instead of the autocoded getter/setter.
        getters_setters_lines = list(itertools.chain.from_iterable([
            self.get_member_lines(member, members[member], struct_type, fully_qualified_class_name, in_).splitlines()
            for member in members.keys()])
        )

        return STRUCT_TEMPLATE.format(STANDARD_INDENT=STANDARD_INDENT,
            fqn=fully_qualified_class_name,
            unqualified_class_name=unqualified_class_name,
            member_getter_setter_lines=f"\n{STANDARD_INDENT}".join(getters_setters_lines)).splitlines()
    
    def get_member_lines(self, name, field: Type, struct_type: StructType, fqn: str, in_: In) -> str:
        """ Get the binding lines (property, getter, and setter) for one struct member

        Args:
            name: name of the member
            field: the type of the member
            struct_type: the struct containing the member
            fqn: fully qualified name of the struct containing the member
            in_: input support tuple
        Returns:
            The binding lines for the member
        """
        if Unqualified(name) in struct_type.sizes:
            element_to_python, element_cpp_type, element_from_cpp, element_python_type = \
                self.get_inline_array_element_info(name, field, fqn, in_)
            return STRUCT_INLINE_ARRAY_GETTER_SETTER_TEMPLATE.format(
                name=name,
                getter=STRUCT_INLINE_ARRAY_GETTER_TEMPLATE.format(
                    name=name, fqn=fqn, element_to_python=element_to_python
                ),
                setter=STRUCT_INLINE_ARRAY_SETTER_TEMPLATE.format(
                    name=name,
                    fqn=fqn,
                    element_cpp_type=element_cpp_type,
                    element_from_cpp=element_from_cpp,
                    element_python_type=element_python_type,
                ),
            )
        return STRUCT_GETTER_SETTER_TEMPLATE.format(
            name=name, fqn=fqn, getter_static_caster=self.get_getter_cast(name=name, field=field, fqn=fqn, in_=in_)
        )

    def get_inline_array_element_info(self, name: str, field: Type, fqn: str, in_: In) -> Tuple[str, str, str, str]:
        """ Get the conversion expressions for the elements of an inlined array member

        Elements are converted to and from Python one at a time, in the same representation the scalar members of the
        same type use. Strings are stored as `Fw::ExternalString` (which cannot be copied) so they are converted through
        `std::string`; enumerations are stored as the enumeration class so they are converted through its `T` type.

        Args:
            name: name of the member
            field: the element type of the member
            fqn: fully qualified C++ name of the struct
            in_: input support tuple
        Returns:
            A tuple of: the expression converting the C++ `item` to Python, the C++ type each Python element is cast
            to, the expression converting `converted[i]` back to the element type, and the Python type name used in
            error messages
        """
        while isinstance(field, AliasType):
            field = field.get_underlying_type()
        if isinstance(field, StringType):
            return "pybind11::str(item.toChar())", "std::string", "converted[i].c_str()", "str"
        if isinstance(field, EnumType):
            enum_class = self.get_fully_qualified_cpp_name(field, in_)
            return "pybind11::cast(item.e)", f"{enum_class}::T", "converted[i]", f"{enum_class.replace('::', '.')}.T"
        python_type = str(field) if field.is_primitive() else \
            self.get_fully_qualified_cpp_name(field, in_).replace("::", ".")
        element = f"std::remove_extent<{fqn}::Type_of_{name}>::type"
        return "pybind11::cast(item)", element, "converted[i]", python_type

    def get_cpp_includes(self, struct_type: StructType, in_: In) -> List[str]:
        """ Get any includes required by this type generator """
        return super().get_cpp_includes(struct_type, in_) + [
            "#include <cstddef>",
            "#include <string>",
            "#include <type_traits>",
            "#include <vector>",
        ]

    def get_field_info(self, name, field: Type, in_: In) -> Tuple[str, str]:
        """ Get the type of a field and whether it should be passed by reference
        
        When generating getter/setter casts for struct members, the function signature needs to be reconstructed. Thus,
        the field types and reference qualifiers need to be determined. This will determine these properties based on
        the field type.

        Warning: this function does not support inlined arrays as struct members because python does not support 
            fixed-sized basic array types. Passing these in will result in a non-array type.

        Args:
            name: name of the field (member) for the getter/setter
            field: the type of the field for the member
            in_: input support tuple
        Returns:
            A tuple of the field type and the reference qualifier for the getter/setter
        """
        # Primitive types are passed by value
        if field.is_primitive():
            return str(field) , ""
        # Alias types should be resolved to their underlying type
        elif isinstance(field, AliasType):
            return self.get_field_info(name, field.get_underlying_type(), in_)
        # String types use external string type as the return of the getter because the string references data stored
        # inside the struct.
        elif isinstance(field, StringType):
            return "Fw::ExternalString" , "&"
        fully_qualified_class_name = self.get_fully_qualified_cpp_name(field, in_)
        # Enumerations append "::T" to the fully qualified class name
        if isinstance(field, EnumType):
            return f"{fully_qualified_class_name}::T" , ""
        # Complex types use reference qualifiers
        return fully_qualified_class_name , "&"


    def get_getter_cast(self, name, fqn: str, field: Type, in_: In) -> str:
        """ Get static cast for a getter method
        
        In the autocoded C++ there are two types of (overloaded) getters: const, and non-const. This causes a compiler
        ambiguity when referring to a getter method for the purposes of binding. To resolve this, a static cast to the
        exact method type is required.

        Warning: this function does not support inlined arrays as struct members because python does not support 
            fixed-sized basic array types. Passing these in will result in a non-array type.
        
        Args:
            name: name of the field (member) for the getter
            fqn: fully qualified name of the struct containing the field
            field: the type of the field for the member
            in_: input support tuple
        Returns:
            The static cast string for the getter method   
        """

        field_type, reference_qualifier = self.get_field_info(name, field, in_)
        return GETTER_STATIC_CAST_TEMPLATE.format(field_type=field_type,
                                                  fqn=fqn,
                                                  reference_qualifier=reference_qualifier,
                                                  const_qualifier="const" if reference_qualifier != "&" else "")
