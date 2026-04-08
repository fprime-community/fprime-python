""" fprime_python.pybind11_generator.py:

File used to generate the pybind11 C++ code for F Prime. This includes the top-level module initialization code, the
definition of submodules, and the binding invocations for all types. This is generated from the JSON files output by
the various type binding generators.
"""
import json
from pathlib import Path
from typing import Dict, List
from .binding_generator import STANDARD_INDENT as STANDARD_INDENTATION

# User defined function name for deployment binding
DEPLOYMENT_BINDING_FUNCTION_NAME = "setup_user_deployment"

# Initialization function template for pybind11 module. This includes header files, module definitions,
# and binding calls.
INITIALIZATION_FUNCTION_TEMPLATE = """
{header_include_block}
#include "FprimePython/FprimePython.hpp"

PYBIND11_MODULE(fprime_py, fprime_) {{
{STANDARD_INDENTATION}fprime_.doc() = "F´ Python Bindings Module";
{STANDARD_INDENTATION}{modules_definition_block}
{STANDARD_INDENTATION}Fw::bind_types(fprime_Fw);
{STANDARD_INDENTATION}Os::bind_osal(fprime_Os);
{STANDARD_INDENTATION}{modules_binding_block}
{STANDARD_INDENTATION}{deployment_binding_function_name}(fprime_);
}}
""".strip()

# Template for header includes
INCLUDE_TEMPLATE = '#include "{header_path}"'

# Template for module definitions
MODULE_TEMPLATE = """
{STANDARD_INDENTATION}auto fprime_{fqn_with_underscores} = fprime_{parent_fqn_with_underscores}.def_submodule("{unqualified_name}", "TODO: add doc strings");
""".strip()

def read_and_merge(files: List[Path]) -> Dict[str, List[str]]:
    """ Read and merge multiple JSON dictionaries into one """
    merged: Dict[str, List[str]] = {}
    for file in files:
        with open(file, "r") as file_handle:
            for key, value in json.load(file_handle).items():
                merged[key] = merged.get(key, []) + [value]
    return merged

def get_module_lines(files: List[Path], headers: List[Path]) -> List[str]:
    """ Generate the lines for the module initialization file """
    header_block = "\n".join([INCLUDE_TEMPLATE.format(header_path=str(header)) for header in headers])
    merged_invocations = read_and_merge(files)

    def all_module_generator(module_strings: List[str]):
        """ Yields all modules from the parts
        
        Only leaf modules are supplied via module_strings; this generator yields all parent modules as well by splitting
        on ".", looping through the parts, and yielding the cumulative parts joined by ".".

        This will also yield standard modules: "Fw" and "Os"
        """
        for standard_module in ["Fw", "Os"]:
            yield standard_module
        for module_string in module_strings:
            parts = []
            for part in module_string.split("."):
                parts.append(part)
                yield ".".join(parts)
    modules = sorted(list({module for module in all_module_generator(merged_invocations.keys())}))
    module_definitions = [
        MODULE_TEMPLATE.format(
            fqn_with_underscores=module.replace(".", "_"),
            parent_fqn_with_underscores="_".join(module.split(".")[:-1]),
            unqualified_name=module.split(".")[-1],
            STANDARD_INDENTATION=STANDARD_INDENTATION
        )
        for module in modules if module != ""
    ]
    module_binding_lines = [ line for module in merged_invocations.keys() for line in merged_invocations[module] ]
    return INITIALIZATION_FUNCTION_TEMPLATE.format(
        header_include_block=header_block,
        modules_definition_block=f"\n{STANDARD_INDENTATION}".join(module_definitions),
        modules_binding_block=f"\n{STANDARD_INDENTATION}".join(module_binding_lines),
        STANDARD_INDENTATION=STANDARD_INDENTATION,
        deployment_binding_function_name=DEPLOYMENT_BINDING_FUNCTION_NAME
    ).splitlines()
