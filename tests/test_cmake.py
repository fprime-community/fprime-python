""" Tests of target/fprime_python.cmake, run against a stand-in project: see tests/cmake/CMakeLists.txt """
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

CMAKE_DIR = Path(__file__).parent.parent / "cmake"
PROJECT = Path(__file__).parent / "cmake"
HOOK_PROJECT = Path(__file__).parent / "cmake_hook"

pytestmark = pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake is not installed")


class Project:
    """ A copy of the stand-in project, since a build writes templates back into its source directory """

    def __init__(self, root: Path) -> None:
        self.source = root / "source"
        self.build_dir = root / "build"
        self.installed = self.build_dir / "install" / "python"
        shutil.copytree(PROJECT, self.source)

    def configure(self, deployments: List[str]) -> str:
        """ Configure with the deployments registered in the order given

        Returns the output of CMake with whitespace collapsed, as CMake wraps the text of its warnings.
        """
        result = subprocess.run(
            ["cmake", "-S", str(self.source), "-B", str(self.build_dir),
             f"-DFPRIME_PYTHON_CMAKE_DIR={CMAKE_DIR}", f"-DTEST_DEPLOYMENTS={';'.join(deployments)}"],
            capture_output=True, text=True, check=True,
        )
        return " ".join((result.stdout + result.stderr).split())

    def build(self, target: str = "all") -> None:
        subprocess.run(
            ["cmake", "--build", str(self.build_dir), "--target", target], capture_output=True, text=True, check=True
        )


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return Project(tmp_path)


@pytest.mark.parametrize("deployments", [["Cpp", "Py"], ["Py", "Cpp"]])
def test_fprime_py_is_built_for_the_python_deployment_in_any_order(project: Project, deployments: List[str]) -> None:
    output = project.configure(deployments)
    assert "RESULT fprime_py built for Py" in output
    assert "Skipping deployment 'Cpp': no '@ fprime-python' topology" in output


def test_only_the_python_deployment_links_the_python_library(project: Project) -> None:
    output = project.configure(["Cpp", "Py"])
    assert "RESULT Py links pybind11::embed" in output
    assert "RESULT Cpp links LINKED-NOTFOUND" in output


def test_cpp_only_project_builds_no_python_module(project: Project) -> None:
    output = project.configure(["Cpp"])
    assert "RESULT fprime_py not built" in output
    project.build()
    assert not project.installed.exists()


def test_second_python_deployment_is_skipped_with_a_warning(project: Project) -> None:
    output = project.configure(["Py", "Py2"])
    assert "RESULT fprime_py built for Py" in output
    assert "Skipping Python deployment 'Py2': fprime_py is already built for 'Py'" in output
    assert "RESULT Py2 links LINKED-NOTFOUND" in output


def test_building_only_the_deployment_installs(project: Project) -> None:
    project.configure(["Cpp", "Py"])
    project.build("Py")
    assert (project.installed / "Component.py").read_text() == "VERSION = 1\n"
    assert list(project.installed.glob("*fprime_py*"))


def test_python_edit_is_installed_without_relinking(project: Project) -> None:
    project.configure(["Py"])
    project.build()
    installed = project.installed / "Component.py"
    module = next(project.installed.glob("*fprime_py*"))
    assert installed.read_text() == "VERSION = 1\n"
    linked = module.stat().st_mtime_ns

    (project.source / "Component.py").write_text("VERSION = 2\n")
    project.build()
    assert installed.read_text() == "VERSION = 2\n"
    assert module.stat().st_mtime_ns == linked


def test_template_is_copied_to_the_source_directory_but_not_installed(project: Project) -> None:
    project.configure(["Py"])
    project.build()
    assert (project.source / "Component.template.py").read_text() == "# template\n"
    assert not (project.installed / "Component.template.py").exists()


def configure_hook(tmp_path: Path, python: str, *options: str) -> subprocess.CompletedProcess:
    """ Configure a project that includes FprimePython.cmake, finding pybind11 with the interpreter given """
    return subprocess.run(
        ["cmake", "-S", str(HOOK_PROJECT), "-B", str(tmp_path / "build"), f"-DFPRIME_PYTHON_CMAKE_DIR={CMAKE_DIR}",
         f"-DPYTHON={python}", *options],
        capture_output=True, text=True, check=False,
    )


def test_hook_registers_the_target_and_position_independent_code(tmp_path: Path) -> None:
    pytest.importorskip("pybind11")
    result = configure_hook(tmp_path, sys.executable)
    assert result.returncode == 0, result.stderr
    assert "RESULT registered target/fprime_python" in result.stdout
    assert "RESULT position independent ON" in result.stdout


def test_hook_names_the_fix_when_pybind11_is_not_installed(tmp_path: Path) -> None:
    # An "interpreter" that fails as one without pybind11 does
    result = configure_hook(tmp_path, shutil.which("false") or "false")
    assert result.returncode != 0
    assert "Install fprime-python into the Python environment used to build" in " ".join(result.stderr.split())


def test_hook_does_nothing_in_a_sub_build(tmp_path: Path) -> None:
    result = configure_hook(tmp_path, shutil.which("false") or "false", "-DFPRIME_SUB_BUILD_TARGETS=target/sub")
    assert result.returncode == 0, result.stderr
    assert "RESULT registered" not in result.stdout
