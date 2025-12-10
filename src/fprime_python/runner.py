""" runner.py:

Helper utility for running F Ptime Python projects. This will help set up the environment, and then import and execute
the fsw_main function expected of the main deployment module.
"""
import os
import sys
from pathlib import Path

def main():
    """ Main entry point for F Prime Python runner
    
    This is used to search for the "build-artifacts" directory, set up the Python path, and then import and execute the
    "fsw_main" function from the "fsw_main" module.
    """
    current_path = Path.cwd()
    while current_path != current_path.root:
        if (current_path / "build-artifacts" / "python").is_dir():
            break
        current_path = current_path.parent
    # Check if we found the directory or if we reached the root
    if current_path == current_path.root:
        print("[ERROR] Could not find 'build-artifacts/python' directory in the current path or its parents.")
        sys.exit(1)
    sys.path.insert(0, str(current_path / "build-artifacts" / "python"))

    # Import the fsw_main module
    try:
        import fsw_main
    except ModuleNotFoundError:
        print(f"[ERROR] Could not find the \"fsw_main.py\" in {current_path / 'build-artifacts' / 'python'}.")
        sys.exit(1)
    except ImportError as e:
        print(f"[ERROR] Could not import fsw_main: {e}")
        sys.exit(1)\
    # Validate that the fsw_main function exists
    if not hasattr(fsw_main, "fsw_main"):
        print("[ERROR] The module \"fsw_main.py\" does not define \"fsw_main()\" function.")
        sys.exit(1)
    # Execute the fsw_main function
    try:
        fsw_main.fsw_main()
    except Exception as e:
        print(f"[ERROR] Error occurred running FSW: {e}")
        if os.environ.get("FPRIME_PYTHON_NO_REPL_ON_ERROR", "0") == "0":
            import code
            code.InteractiveConsole(locals=globals()).interact()
        else:
            sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()