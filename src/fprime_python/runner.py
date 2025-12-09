""" runner.py:

Helper utility for running F Ptime Python projects. This will help set up the environment, and then import and execute
the fsw_main function expected of the main deployment module.
"""
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

    # Import and execute the fsw_main function from the fsw_main module
    from fsw_main import fsw_main
    fsw_main()

if __name__ == "__main__":
    main()