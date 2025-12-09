
"""fprime-python:

An autocoder that is used to generate Python bindings for F Prime components. This module provides two functions:
 - bindings: Generate Python bindings for F Prime types and components that have the @fprime-python annotation
 - initialization: Generate the pybind11 module initialization code that ties together the generated bindings
"""
from __future__ import annotations


import argparse
from pathlib import Path
from typing import Dict, List


from fprime_python_model.model import FprimePythonModel
from fprime_python_model.semantics.analysis import Analysis


from .visitor import AnnotatedComponentVisitor
from .include import IncludeManager
from .pybind11_generator import get_module_lines

def patch_analysis(analysis: Analysis) -> Analysis:
	""" Fill in missing analysis information
	
	The visitor pattern allows us to map AST node to AST node. However, the analysis information is only indexed by AST
	node ID through the component. Thus the visitor pattern breaks once reaching the component, or we must extend the
	information.

	Thus function takes the later approach by deriving an analysis mapping for each of the listed patch fields thus
	allowing direct indexing by AST node ID.

	WARNING: this function mutates the analysis in place.

	"""
	PATCH_FIELDS = [
		'command_map', 'container_map', 'event_map', 'param_map', 'port_map', 'record_map',
		'special_port_map', 'state_machine_instance_map', 'tlm_channel_map', 'tlm_channel_name_map'
	]
	for component in analysis.component_map.values():
		for field in PATCH_FIELDS:
			# Grab any previously existing mappings, starting with an empty dictionary
			mapping = getattr(analysis, field, {})
			# Loop through the values of the component's field mappings. Map the AST node ID to the value thus
			# creating a direct lookup from AST node ID to analysis information for that type.
			for value in getattr(component, field, {}).values():
				mapping[value.get_node()._id] = value
			setattr(analysis, field, mapping)

def load_model(build_cache: Path) -> FprimePythonModel:
	""" Load the fprime model in the given build cache

	Using the standard names of the fpp-to-json output, this function loads the model for use in Python. 
	
	Args:
		build_cache: Path to the build cache directory.
	"""
	model_load_arguments = [
		build_cache / "fpp-ast.json",
		build_cache / "fpp-loc-map.json",
		build_cache / "fpp-analysis.json",
	]
	# Validate that all required files exist and are files
	for path in model_load_arguments:
		if not path.exists():
			raise ValueError(f"Required model file {path} does not exist. Have you run fpp-to-json?")
		if not path.is_file():
			raise ValueError(f"Required model file {path} is not a file.")

	model = FprimePythonModel(*model_load_arguments)
	return model


def parse_binding_args(parser: argparse.ArgumentParser) -> None:
	"""Register the 'binding' subcommand parser.

	The binding parser takes arguments needed to autocode binding from FPP types and will trigger when the `bindings`
	subcommand is used.

	Args:
		parser: Parent ArgumentParser (typically from add_subparsers()) to register
		        the binding subcommand arguments into.
	"""
	# Positional build cache
	parser.add_argument(
		"build_cache",
		type=Path,
		help="Path to the build cache for the module.",
	)

	# Optional flag that accepts one or more translation units
	parser.add_argument(
		"--translation-units",
		metavar="FILE",
		type=Path,
		nargs="+",
		default=[],
		help="One or more translation unit paths. Default: All TUs in model.",
	)
	
	parser.add_argument(
		"--prefixes",
		metavar="PREFIX",
		type=Path,
		nargs="+",
		required=True,
		help="Prefixes used when determining module names",
	)

	# Boolean dry-run flag
	parser.add_argument(
		"--dry-run",
		action="store_true",
		help="Only print the files that would be generated.",
		default=False,
	)
	parser.add_argument(
		"--output-directory",
		type=Path,
		default=None,
		help="Output directory for generated files. Default: build cache directory.",
	)


def parse_initialization_args(parser: argparse.ArgumentParser) -> None:
	"""Register the 'initialization' subcommand parser

	The initialization parser takes arguments needed to autocode pybind11 initialization from the snippets of code
	created for the FPP components by the `bindings` subcommand.

	Args:
		parser: Parent ArgumentParser (typically from add_subparsers()) to register
		        the initialization subcommand arguments into.
	"""
	parser.add_argument(
		"--json-files",
		metavar="FILE",
		type=Path,
		nargs="+",
		required=True,
		help="One or more JSON files to merge into an initialization function",
	)
	
	parser.add_argument(
		"--header-files",
		metavar="FILE",
		type=Path,
		nargs="+",
		required=True,
		help="One or more header files to #include in the initialization file",
	)

	# Boolean dry-run flag
	parser.add_argument(
		"--dry-run",
		action="store_true",
		help="Only print the files that would be generated.",
		default=False,
	)
	parser.add_argument(
		"--output-directory",
		type=Path,
		default=None,
		help="Output directory for generated files. Default: build cache directory.",
	)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
	"""Parse command-line arguments.

	Args:
		argv: Optional list of arguments (defaults to sys.argv[1:]).

	Returns:
		argparse.Namespace containing parsed values. The namespace includes:
		  - build_cache: positional path to the build cache
		  - translation_units: list of translation unit paths (may be empty)
		  - dry_run: boolean flag indicating whether to perform side-effecting actions
	"""
	parser = argparse.ArgumentParser(
		prog="fprime-python",
		description="fprime-python autocoder",
	)

	# Create subparsers for different commands
	subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand to run")

	# Register the 'bindings' subcommand
	binding_parser = subparsers.add_parser(
		"bindings",
		help="Generate Python bindings for F´ components",
	)
	# Register the 'initialization' subcommand
	initialization_parser = subparsers.add_parser(
		"initialization",
		help="Generate Python initialization code for F´ components",
	)
	parse_binding_args(binding_parser)
	parse_initialization_args(initialization_parser)

	args = parser.parse_args(argv)
	
	# Validate build cache path
	if args.command == "bindings" and not args.build_cache.exists():
		raise ValueError(f"Build cache path {args.build_cache} does not exist.")
	if args.command == "bindings" and not args.build_cache.is_dir():
		raise ValueError(f"Build cache path {args.build_cache} is not a directory.")
	if args.output_directory is None:
		args.output_directory = args.build_cache
	if not args.output_directory.exists():
		raise ValueError(f"Output directory path {args.output_directory} does not exist.")
	if not args.output_directory.is_dir():
		raise ValueError(f"Output directory path {args.output_directory} is not a directory.")
	return args

def write_em(output_map: Dict[Path, List[str]]) -> None:
	""" Write the output map to files """
	for output_path, lines in output_map.items():
		output_path.parent.mkdir(parents=True, exist_ok=True)
		with open(output_path, "w", encoding="utf-8") as output_file:
			output_file.write("\n".join(lines))

def main(argv: List[str] | None = None) -> int:
	""" Main program. Hi Lewis!!! """
	args = parse_args(argv)

	if args.command == "bindings":
		model = load_model(args.build_cache)
		include_manager = IncludeManager(args.prefixes, model.location_map)
		visitor = AnnotatedComponentVisitor(args.output_directory, args.translation_units, model.location_map)

		output = visitor.translation_units([model.analysis, include_manager], model.ast)
	elif args.command == "initialization" and not args.dry_run:
		output = {args.output_directory / "fprime_init.cpp": get_module_lines(args.json_files, args.header_files)}
	elif args.command == "initialization":
		output = {args.output_directory / "fprime_init.cpp": []}
	else:
		assert False, f"Unreachable command branch: {args.command}"
	print(" ".join([str(output_file) for output_file in output.keys()]))
	if not args.dry_run:
		write_em(output)
	return 0


if __name__ == "__main__":
	# Exit with the returned status code from main
	raise SystemExit(main())

