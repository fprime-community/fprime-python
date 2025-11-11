""" fprime_python.pybind11_generator.py:

File used to generate the pybind11 C++ code for F´.
"""
import itertools
import json
from pathlib import Path
from typing import Dict, List

STANDARD_INDENTATION = " " * 4

INITIALIZATION_FUNCTION_TEMPLATE = """
{header_include_block}

PYBIND11_MODULE(fprime_python, fprime_) {{
{STANDARD_INDENTATION}fprime_.doc() = "F´ Python Bindings Module";
{STANDARD_INDENTATION}{modules_block}
}}
"""

INCLUDE_TEMPLATE = '#include "{header_path}"'

MODULE_TEMPLATE = """
{STANDARD_INDENTATION}auto fprime_{fqn_with_underscores} = fprime_{parent_fqn_with_underscores}.def_submodule("{unqualified_name}", "TODO: add doc strings");
"""

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
        """
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


        
    ] + [ line.replace("(m)", "(fprime_" + module.replace(".", "_") + ")") for module in merged_invocations.keys() for line in merged_invocations[module] ]
    return INITIALIZATION_FUNCTION_TEMPLATE.format(
        header_include_block=header_block,
        modules_block=f"\n{STANDARD_INDENTATION}".join(module_definitions),
        STANDARD_INDENTATION=STANDARD_INDENTATION
    ).splitlines()
