"""
pybind_gen.py:

This is a very crude implementation of the python templater for python bindings.
"""
import argparse
import os
import re
import sys
from pathlib import Path
from collections import OrderedDict

from xml.dom.minidom import parse, parseString

from jinja2 import Environment, PackageLoader, select_autoescape

from fprime_ac.utils.buildroot import search_for_file, build_root_relative_path, set_build_roots

env = Environment(
    loader=PackageLoader(__name__),
    autoescape=select_autoescape()
)
STRING_PAIRS = {
    "string": ("String", "Fw/Types/String.hpp"),
    "channel": ("TlmString", "Fw/Tlm/TlmString.hpp"),
    "event": ("LogStringArg", "Fw/Log/LogString.hpp"),
    "command": ("CmdStringArg", "Fw/Cmd/CmdString.hpp"),
    "parameter": ("ParamString", "Fw/Prm/PrmString.hpp")
}

STRING_NEEDS = set()
STRING_TYPES = []
FEATURES = {
    "uses_time": False,
    "uses_string": False,
    "uses_commands": False,
    "uses_events": False,
    "uses_telemetry": False,
    "uses_parameters": False,
    "uses_queues": False,
    "uses_tasks": False
}

def make_string(item, path, ns="Fw"):
    """ Make pair """
    return {
        "ns": ns,
        "type": "string",
        "name": item,
        "header_path": path
    }


def get_type_name(cpp_type):
    return cpp_type.replace("const", "").replace("&", "").strip().replace("::", ".")


def autocast_arg(arg_name, arg_type, python_type):
    return f"{ get_type_name(arg_type) }({ arg_name }) if isinstance({ arg_name }, { python_type }) else { arg_name }"


def upcast_argument(argument):
    """ Upcast arguments en-route to features """
    return argument[0] if "string" not in argument[1].lower() else argument[0] + ".toChar()"


def downcast_argument(argument):
    """ """
    arg_name, arg_type = argument
    return arg_name if "string" not in arg_type.lower() else autocast_arg(arg_name, arg_type, "str")


def upcast_arguments(arguments):
    return ",".join([upcast_argument(argument) for argument in arguments])


def downcast_arguments(arguments):
    return ",".join([downcast_argument(argument) for argument in arguments])


def parse_enum(xml):
    """ Maps Enum XML to an enum item """
    root = xml.getElementsByTagName("enum")[0]
    values = [tag.getAttribute("name") for tag in xml.getElementsByTagName("item")]
    return {"ns": root.getAttribute("namespace"), "name": root.getAttribute("name"), "vals": values}


def parse_array(xml):
    """ Maps Enum XML to an array item """
    root = xml.getElementsByTagName("array")[0]
    size = int(root.getElementsByTagName("size")[0].firstChild.nodeValue)
    etype = root.getElementsByTagName("type")[0].firstChild.nodeValue
    return {"ns": root.getAttribute("namespace"), "name": root.getAttribute("name"), "elem_type": etype, "size": size}


def parse_serializable(xml):
    """ Maps Enum XML to an enum item """
    members_to_types = OrderedDict()
    root = xml.getElementsByTagName("serializable")[0]
    for tag in xml.getElementsByTagName("member"):
        members_to_types[tag.getAttribute("name")] = tag.getAttribute("type")
        if tag.getAttribute("type") == "Fw::String":
            FEATURES["uses_string"] = True
            STRING_NEEDS.add(STRING_PAIRS["string"])
    return {"ns": root.getAttribute("namespace"), "name": root.getAttribute("name"), "member_list": members_to_types}


def parse_args(xml, source=None):
    """"""
    results = []
    for arg in xml.getElementsByTagName("arg"):
        arg_type = arg.getAttribute("type")
        if source == "--cmd--" and arg_type == "string":
            STRING_NEEDS.add(STRING_PAIRS["command"])
            arg_type = f"const Fw::CmdStringArg&"
        elif source == "--event--" and arg_type == "string":
            arg_type = f"const Fw::LogStringArg&"
            STRING_NEEDS.add(STRING_PAIRS["event"])
        elif arg_type == "string" and source is not None:
            invented_string_type = f"{ arg.getAttribute('name') }String"
            # Check that no other types already defined
            existing = list(filter(lambda st: st["name"] == invented_string_type and st["ns"] == source, STRING_TYPES))
            if not existing:
                STRING_TYPES.append(make_string(invented_string_type, "", ns=source))
            arg_type = f"{ source }::{ invented_string_type }{ '&' if arg.getAttribute('pass_by') == 'reference' else ''}"
        results.append((arg.getAttribute("name"), arg_type))
    return results


def parse_comp_commands(xml):
    """"""
    results = []
    for command in xml.getElementsByTagName("command"):
        FEATURES["uses_time"] = True
        FEATURES["uses_commands"] = True
        name = command.getAttribute("mnemonic")
        args = [("opCode", "FwOpcodeType"), ("cmdSeq", "U32")] + parse_args(command, "--cmd--")
        results.append({"name": name, "arg_full_texts": ["{} {}".format(atype, name) for name, atype in args],
                        "arg_names": ["{}".format(name) for name, _ in args], "args": args})
    return results


def parse_comp_extras(xml, extra_type):
    """"""
    results = []
    for item in xml.getElementsByTagName(extra_type):
        obj = {"name": item.getAttribute("name")}
        if extra_type == "event":
            FEATURES["uses_time"] = True
            FEATURES["uses_events"] = True
            args = parse_args(item, source="--event--")
            obj["severity"] = item.getAttribute("severity")
            obj["args"] = args
            obj["arg_full_texts"] = ["{} {}".format(atype, name) for name, atype in args],
            obj["arg_names"] = ["{}".format(name) for name, _ in args]
        elif extra_type == "channel":
            FEATURES["uses_time"] = True
            FEATURES["uses_telemetry"] = True
            obj["data_type"] = item.getAttribute("data_type")
            if obj["data_type"] == "string":
                obj["data_type"] = "Fw::TlmString"
                STRING_NEEDS.add(STRING_PAIRS[extra_type])
        elif extra_type == "parameter":
            FEATURES["uses_time"] = True
            FEATURES["uses_commands"] = True
            FEATURES["uses_parameters"] = True
            obj["data_type"] = item.getAttribute("data_type")
            if obj["data_type"] == "string":
                obj["data_type"] = "Fw::ParamString"
                STRING_NEEDS.add(STRING_PAIRS[extra_type])
        results.append(obj)
    return results


def port_defs(xml):
    """"""
    results = {}
    for port_import in xml.getElementsByTagName("import_port_type"):
        with open(search_for_file("Port", port_import.firstChild.nodeValue), "r") as file_handle:
            port_xml = parse(file_handle)
            ns = port_xml.documentElement.getAttribute("namespace")
            args = [("portNum", "NATIVE_INT_TYPE")] + list(parse_args(port_xml, ns))
            name = port_xml.documentElement.getAttribute("name")
            results[ns + "::" + name] = {"name": name, "ns": ns, "arg_full_texts": ["{} {}".format(atype, name) for name, atype in args],
                                         "arg_names": ["{}".format(name) for name, _ in args], "args": args}
    return results


def parse_comp_ports(xml):
    """"""
    verboten = ["Fw::Cmd", "Fw::CmdResponse", "Fw::CmdReg", "Fw::LogText", "Fw::Log", "Fw::Tlm", "Fw::Time"] #TODO: fix this for role ports
    in_ports = []
    out_ports = []
    port_definitions = port_defs(xml)
    for port in xml.getElementsByTagName("port"):
        dtype = port.getAttribute("data_type")
        name = port.getAttribute("name")
        kind = port.getAttribute("kind")
        if kind != "passive":
            FEATURES["uses_queues"] = True
        if kind == "active":
            FEATURES["uses_tasks"] = True
        port_def = port_definitions[dtype]
        try:
            obj = {"name": name, "ns": port_def["ns"], "args": port_def["args"], "arg_full_texts": port_def["arg_full_texts"], "arg_names": port_def["arg_names"]}
        except:
            raise Exception(f"Malformed port definition with name: { name }")
        if "input" in kind and dtype not in verboten:
            in_ports.append(obj)
        elif "output" in kind and dtype not in verboten:
            out_ports.append(obj)
    return in_ports, out_ports


def parse_component(xml):
    """ Maps Enum XML to an enum item """
    elements = []
    for tag in xml.getElementsByTagName("import_dictionary"):
        with open(search_for_file("Any", tag.firstChild.nodeValue), "r") as file_handle:
            elements += [parse(file_handle).documentElement]
    for element in elements:
        xml.documentElement.appendChild(element)
    root = xml.documentElement
    component = {"ns": root.getAttribute("namespace"), "name": root.getAttribute("name"), "kind": root.getAttribute("kind")}
    component["commands"] = parse_comp_commands(xml)
    component["events"] = parse_comp_extras(xml, "event")
    component["channels"] = parse_comp_extras(xml, "channel")
    component["parameters"] = parse_comp_extras(xml, "parameter")
    in_ports, out_ports = parse_comp_ports(xml)
    component["in_ports"] = in_ports
    component["out_ports"] = out_ports
    return component


PARSE_ROUTE_TABLE = {
    "Enum": parse_enum,
    "Array": parse_array,
    "Serializable": parse_serializable,
    "Component": parse_component
}


def main():
    """ Reads a list of XMLs from file, generates output """
    parser = argparse.ArgumentParser(description='Parse out the python bindings and generate binding outputs')
    parser.add_argument('--ai', nargs='+', help='AI file list of files that might need bindings')
    # parser.add_argument('--deps', nargs='+', help='Dependencies of components explicitly requesting pybind')
    args = parser.parse_args()



    # Setup mechanics for fprime autocoders
    set_build_roots(os.environ["BUILD_ROOT"])
    searcher = re.compile(r"(Component)Ai\.xml")
    # Read out XML list and make them absolute
    paths = set([Path(item).absolute() for item in args.ai])
    namespaces = {}

    # Running through each path
    for path in paths:
        relative_path = build_root_relative_path(str(path))
        searched = searcher.search(str(path.name))

        # Skip files that are not something we can handle (ai.xml)
        if not searched:
            continue
        # Filter out items that are not part of a dependency package
        # elif os.path.dirname(relative_path).replace(os.sep, "_").strip("_") not in args.deps:
        #     continue
        try:
            parser_function = PARSE_ROUTE_TABLE[searched.group(1)]
        except Exception as exc:
            print(f"[ERROR] PyBind found unknown model type { searched.group(1) }", file=sys.stderr)
            sys.exit(1)
        # Parse file
        try:
            with open(path, "r") as file_handle:
                 dom = parse(file_handle)
            item = parser_function(dom)
            if item is None:
                continue
        except OSError as ose:
            print(f"[ERROR] PyBind errored reading: { path } with error { exc }", file=sys.stderr)
            sys.exit(1)
        except IndexError:
            print(f"[ERROR] PyBind errored parsing: { path }. Required tag missing, check for misspellings.", file=sys.stderr)
            sys.exit(1)
        except KeyError as ker:
            ker = str(ker)
            message = f"find symbol {ker}" if ":" in ker else f"read field {ker}"
            print(f"[ERROR] PyBind unable { message }", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"[ERROR] PyBind errored parsing: { path } with error { exc }", file=sys.stderr)
            raise
            sys.exit(1)
        item["type"] = searched.group(1)
        item["header_path"] = relative_path.replace("Ai.xml", "Ac.hpp")
        item["output_directory"] = path.parent
        if item["ns"] not in namespaces:
            namespaces[item["ns"]] = []
        namespaces[item["ns"]].append(item)

    # String type additions
    for string_type in STRING_TYPES + [make_string(*item) for item in STRING_NEEDS]:
        if string_type["ns"] not in namespaces:
            namespaces[string_type["ns"]] = []
        namespaces[string_type["ns"]].append(string_type)

    for template_name in ["PyBindAc.hpp.j2", "PyBindAc.cpp.j2", "fprime_pybind.py.j2"]:
        template = env.get_template(template_name)
        output = template.render(namespaces=namespaces, functions={
                "upcast_arguments": upcast_arguments,
                "downcast_arguments": downcast_arguments,
                "autocast_arg": autocast_arg,
            },
            **FEATURES
        )
        with open(f"{ template_name.replace('.j2', '') }", "w") as file_handle:
            file_handle.write(output)
    # Write out component templates
    template = env.get_template("ComponentTemplate.py.j2")
    for _, items in namespaces.items():
        for item in [item for item in items if item["type"] == "Component"]:
            output = template.render(item=item)
            output_path = item["output_directory"] / f"{ item['name'] }.py.tmpl"
            print(f"Created Python Template File At {output_path}")
            with open(output_path, "w") as file_handle:
                file_handle.write(output)


if __name__ == "__main__":
    main()
