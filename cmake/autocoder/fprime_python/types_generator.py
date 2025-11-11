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
    ArrayPybindCppGenerator().get_lines(array_type, model)
    ```

    Example Output:
    ```cpp
    void init_MyNamespace_MyArray(pybind11::module_& m) {
        
        pybind11::class_<MyNamespace::MyArray>(m, "PythonArray")
        .def(pybind11::init<>())
        .def("__getitem__", [](const MyNamespace::MyArray &a, int index) {
            if (index >= MyNamespace::MyArray::SIZE) {
                throw std::out_of_range("array index out of bounds");
            }
            return a[index];
        }, pybind11::is_operator())
        .def("__setitem__",
            [](MyNamespace::MyArray &a, int index, const MyNamespace::MyArray::ElementType &value) {
            if (index >= MyNamespace::MyArray::SIZE) {
                throw std::out_of_range("array index out of bounds");
            }
            a[index] = value;
        }, pybind11::is_operator())
        .def_property_readonly_static("size", [](pybind11::object /* self */) {
            return MyNamespace::MyArray::SIZE;
        })
        .def_property_readonly_static("SIZE", [](pybind11::object /* self */) {
            return MyNamespace::MyArray::SIZE;
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

pybind11::native_enum<{fqn}::T>(enumeration, "{unqualified_class_name}", "enum.Enum")
{STANDARD_INDENT}{values}
{STANDARD_INDENT}.finalize();
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
    EnumPybindCppGenerator().get_cpp_lines(enum_type, model)
    ```

    Example Output:
    ```cpp
    void init_MyNamespace_MyEnum(pybind11::module_& m) {
        pybind11::class_<MyNamespace::MyEnum> enumeration(m, "MyEnum");
        enumeration.def_readwrite("e", &MyNamespace::MyEnum::e);

        pybind11::native_enum<MyNamespace::MyEnum::T>(enumeration, "MyEnum", "enum.Enum")
            .value("VAL1", MyNamespace::MyEnum::VAL1)
            .value("VAL2", MyNamespace::MyEnum::VAL2)
            .finalize();
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
    void init_MyNamespace_MyStruct(pybind11::module_& m) {
        pybind11::class_<MyNamespace::MyStruct>(m, "MyStruct")
            .def(pybind11::init<>())
            .def_property("member1", static_cast<some type>(&MyNamespace::MyStruct::get_member1),
                                     &MyNamespace::MyStruct::set_member1
                         )
            .def("get_member1", static_cast<some type>(&MyNamespace::MyStruct::get_member1))
            .def("set_member1", &MyNamespace::MyStruct::set_member1);

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
        # Additionally, struct fields with inlined arrays cannot be supported with Python bindings because Python does
        # not support fixed-size arrays and FPP does not provide an actual fixed-sized array class to bind to.
        getters_setters_lines = list(itertools.chain.from_iterable([
            STRUCT_GETTER_SETTER_TEMPLATE.format(name=member,
                                                 fqn=fully_qualified_class_name,
                                                 getter_static_caster=self.get_getter_cast(name=member,
                                                                                           field=members[member],
                                                                                           fqn=fully_qualified_class_name, in_=in_),
                                                ).splitlines()
            for member in members.keys() if not Unqualified(member) in struct_type.sizes])
        )

        return STRUCT_TEMPLATE.format(STANDARD_INDENT=STANDARD_INDENT,
            fqn=fully_qualified_class_name,
            unqualified_class_name=unqualified_class_name,
            member_getter_setter_lines=f"\n{STANDARD_INDENT}".join(getters_setters_lines)).splitlines()
    
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

    def get_setter_cast(self, name, fqn: str, field: Type, in_: In) -> str:
        """ Get static cast for a setter method
        
        TODO: this does not seem to be required as there is no non-const setter method. This may have been mistakenly
            written in parallel with the getter method.

            
        Warning: this function does not support inlined arrays as struct members because python does not support 
            fixed-sized basic array types. Passing these in will result in a non-array type.
            
        Args:
            name: name of the field (member) for the setter
            fqn: fully qualified name of the struct containing the field
            field: the type of the field for the member
            in_: input support tuple
        Returns:
            The static cast string for the setter method
        """
        field_type, reference_qualifier = self.get_field_info(name, field, parent, in_)
        field_type = field_type.replace("Fw::ExternalString", "Fw::StringBase")
        return SETTER_STATIC_CAST_TEMPLATE.format(field_type=field_type,
                                                  fqn=fqn,
                                                  reference_qualifier=reference_qualifier,
                                                  const_qualifier="const" if reference_qualifier == "&" else "")