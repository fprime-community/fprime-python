
"""fprime-python:

An autocoder that is used to generate Python bindings for F Prime components. This module provides two
subcommands:
 - bindings: Generate Python bindings for F Prime types and components that have the @fprime-python
   annotation
 - initialization: Generate the pybind11 module initialization code that ties together the generated
   bindings
"""
from __future__ import annotations


import argparse
import sys
from pathlib import Path
from typing import Dict, List


from .cpp_types import UnsupportedTypeError
from .include import IncludeError, IncludeManager
from .model import IMPORT_LIST_PATH, SOURCE_LIST_PATH, ModelError, load_model, read_path_list
from .view import UnsupportedModelError
from .pybind11_generator import INIT_FILE_BASE, render_module_file
from .visitor import AnnotatedDefinitionVisitor


def parse_binding_args(parser: argparse.ArgumentParser) -> None:
	"""Register the 'bindings' subcommand parser.

	The binding parser takes arguments needed to autocode bindings from FPP types and will trigger when
	the `bindings` subcommand is used.

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
		help=f"One or more translation unit paths. Default: those listed in the build cache's"
		     f" {SOURCE_LIST_PATH}.",
	)

	# Optional flag that accepts the rest of the FPP model
	parser.add_argument(
		"--imports",
		metavar="FILE",
		type=Path,
		nargs="+",
		default=[],
		help=f"FPP files the translation units depend on. Default: those listed in the build cache's"
		     f" {IMPORT_LIST_PATH.as_posix()}.",
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

	The initialization parser takes arguments needed to autocode pybind11 initialization from the snippets
	of code created for the FPP components by the `bindings` subcommand.

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
		required=True,
		help="Output directory for the generated initialization file.",
	)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
	"""Parse command-line arguments.

	Args:
		argv: Optional list of arguments (defaults to sys.argv[1:]).

	Returns:
		argparse.Namespace containing parsed values. The namespace includes:
		  - build_cache: positional path to the build cache
		  - translation_units: list of translation unit paths (may be empty)
		  - imports: list of paths to the rest of the FPP model (may be empty)
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

	# Validate the build cache, and default the output directory to it. Only the bindings subcommand has a
	# build cache: the initialization subcommand works from files it is handed, so it requires the flag.
	if args.command == "bindings":
		if not args.build_cache.exists():
			parser.error(f"Build cache path {args.build_cache} does not exist.")
		if not args.build_cache.is_dir():
			parser.error(f"Build cache path {args.build_cache} is not a directory.")
		if args.output_directory is None:
			args.output_directory = args.build_cache
	if not args.output_directory.exists():
		parser.error(f"Output directory path {args.output_directory} does not exist.")
	if not args.output_directory.is_dir():
		parser.error(f"Output directory path {args.output_directory} is not a directory.")
	return args


def write_em(output_map: Dict[Path, str]) -> None:
	""" Write the output map to files """
	for output_path, contents in output_map.items():
		output_path.parent.mkdir(parents=True, exist_ok=True)
		with open(output_path, "w", encoding="utf-8") as output_file:
			output_file.write(contents)


def generate_bindings(args: argparse.Namespace) -> Dict[Path, str]:
	""" Generate the bindings for one module

	The FPP files making up the model default to the lists F Prime's FPP autocoder leaves in the module's
	build cache: its own translation units, and the transitive closure of everything they reference.

	Args:
		args: Parsed arguments of the `bindings` subcommand
	Returns:
		A mapping of output path to file contents
	"""
	sources = args.translation_units or read_path_list(args.build_cache / SOURCE_LIST_PATH)
	imports = args.imports or read_path_list(args.build_cache / IMPORT_LIST_PATH)
	model = load_model(sources, imports)
	include_manager = IncludeManager(args.prefixes)
	visitor = AnnotatedDefinitionVisitor(
		args.output_directory, model.analysis, include_manager
	)
	return visitor.generate(model)


def main(argv: List[str] | None = None) -> int:
	""" Main program. Hi Lewis!!! """
	args = parse_args(argv)

	if args.command == "bindings":
		# These are all "your model or your build is not what this tool needs" failures, and are the ones
		# a user is expected to hit. A traceback would only bury them in the build log.
		try:
			output = generate_bindings(args)
		except (ModelError, IncludeError, UnsupportedTypeError, UnsupportedModelError) as error:
			print(f"[ERROR] {error}", file=sys.stderr)
			return 1
	elif args.command == "initialization":
		init_file = args.output_directory / f"{INIT_FILE_BASE}.cpp"
		# A dry run only reports the file name, so the model is not needed to produce it
		contents = "" if args.dry_run else render_module_file(args.json_files, args.header_files)
		output = {init_file: contents}
	else:
		assert False, f"Unreachable command branch: {args.command}"
	print(" ".join([str(output_file) for output_file in output.keys()]))
	if not args.dry_run:
		write_em(output)
	return 0


if __name__ == "__main__":
	# Exit with the returned status code from main
	raise SystemExit(main())
