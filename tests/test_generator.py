""" Tests of the bindings generated for a small fixture model """
from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from fprime_python.autocode.__main__ import main
from fprime_python.autocode.include import IncludeManager
from fprime_python.autocode.model import load_model
from fprime_python.autocode.visitor import AnnotatedDefinitionVisitor

FIXTURES = Path(__file__).parent / "fixtures"


def generate(fixture: str, output: Path) -> Dict[str, str]:
    """ Generate the bindings of one fixture model, keyed by output file name """
    model = load_model([FIXTURES / fixture], [FIXTURES / "Config.fpp"])
    visitor = AnnotatedDefinitionVisitor(output, model.analysis, IncludeManager([FIXTURES]))
    return {path.name: contents for path, contents in visitor.generate(model).items()}


@pytest.fixture
def files(tmp_path: Path) -> Dict[str, str]:
    return generate("Model.fpp", tmp_path)


def test_array_string_element_is_length_checked(files: Dict[str, str]) -> None:
    source = files["NamesBindingAc.cpp"]
    assert "FprimePython::check_string_fits(value, array[index].getCapacity());" in source
    assert source.index("check_string_fits") < source.index("array[index] = value.c_str();")


def test_struct_string_member_setter_is_length_checked(files: Dict[str, str]) -> None:
    source = files["RecordBindingAc.cpp"]
    assert "FprimePython::check_string_fits(text, self.get_label().getCapacity());" in source
    assert "&Fixture::Record::set_label" not in source


def test_struct_inline_string_array_is_checked_before_writing(files: Dict[str, str]) -> None:
    source = files["RecordBindingAc.cpp"]
    check = "FprimePython::check_string_fits(converted[i], self.get_tags()[i].getCapacity());"
    assert check in source
    assert source.index(check) < source.index("self.get_tags()[i] = converted[i].c_str();")


def test_array_subscript_checks_both_bounds(files: Dict[str, str]) -> None:
    source = files["NamesBindingAc.cpp"]
    assert source.count("if (index < 0 || static_cast<FwSizeType>(index) >= Fixture::Names::SIZE)") == 2


def test_annotated_deployment_is_bound(files: Dict[str, str]) -> None:
    source = files["AnnotatedBindingAc.cpp"]
    assert 'm.def("setup", &Fixture::setup' in source
    assert 'm.def("teardown", &Fixture::teardown' in source
    assert '"pyComp"' in source


def test_topologies_needing_no_annotation_are_accepted(files: Dict[str, str]) -> None:
    # The fixture model also holds an unannotated deployment of C++ instances and an unannotated
    # non-deployment topology of Python instances; generating it at all shows neither is refused
    assert "PlainBindingAc.cpp" not in files
    assert "SubBindingAc.cpp" not in files
    assert "AnnotatedBindingAc.cpp" in files


def test_unannotated_deployment_of_python_components_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The command line reads the model's imports from the build cache fpp-depend leaves
    imports = tmp_path / "fpp-cache" / "stdout.txt"
    imports.parent.mkdir()
    imports.write_text(f"{FIXTURES / 'Config.fpp'}\n", encoding="utf-8")
    status = main(
        [
            "bindings",
            str(tmp_path),
            "--dry-run",
            "--output-directory",
            str(tmp_path),
            "--prefixes",
            str(FIXTURES),
            "--translation-units",
            str(FIXTURES / "Unannotated.fpp"),
        ]
    )
    assert status == 1
    error = capsys.readouterr().err
    assert "Deployment topology Fixture.Unannotated" in error
    assert "Fixture.pyComp" in error


def test_sized_string_arguments_are_checked_against_their_declared_size(files: Dict[str, str]) -> None:
    source = files["PyCompBindingAc.cpp"]
    port = "FprimePython::check_declared_size(msg, 16);"
    assert port in source
    assert source.index(port) < source.index("return self.textOut_out(portNum, msg);")
    assert "FprimePython::check_declared_size(msg, 12);" in source
    assert "return self.log_ACTIVITY_LO_Said(msg);" in source
    assert "FprimePython::check_declared_size(arg, 6);" in source
    assert "&Fixture::PyComp::textOut_out" not in source
    assert "&Fixture::PyComp::isConnected_textOut_OutputPort" in source
    internal = files["PyQueuedBindingAc.cpp"]
    assert "FprimePython::check_declared_size(msg, 5);" in internal
    assert "return self.poke_internalInterfaceInvoke(msg);" in internal


def test_sized_string_return_is_checked_against_its_declared_size(files: Dict[str, str]) -> None:
    source = files["PyComp.cpp"]
    check = "FprimePython::check_declared_size(result, 8);"
    assert check in source
    assert source.index("Fw::String result = return_value.cast<Fw::String>();") < source.index(check)
    assert source.index(check) < source.index("return result;")
