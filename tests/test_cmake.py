""" Tests of target/fprime_python.cmake, run against a stand-in project: see tests/cmake/CMakeLists.txt """
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List

import pytest

CMAKE_DIR = Path(__file__).parent.parent / "cmake"
PROJECT = Path(__file__).parent / "cmake"

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

    def build(self) -> None:
        subprocess.run(["cmake", "--build", str(self.build_dir)], capture_output=True, text=True, check=True)


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
