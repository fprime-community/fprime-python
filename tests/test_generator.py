""" Tests of the bindings generated for a small fixture model """
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pytest

from fprime_python.autocode.__main__ import main
from fprime_python.autocode.include import IncludeManager
from fprime_python.autocode.model import load_model
from fprime_python.autocode.view import UnsupportedModelError
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
    log = "static_cast<FwSizeType>(FW_LOG_STRING_MAX_SIZE)"
    tlm = "static_cast<FwSizeType>(FW_TLM_STRING_MAX_SIZE)"
    assert f"FprimePython::check_declared_size(msg, FW_MIN({log}, static_cast<FwSizeType>(12)));" in source
    assert "return self.log_ACTIVITY_LO_Said(msg);" in source
    unsized = "static_cast<FwSizeType>(FW_FIXED_LENGTH_STRING_SIZE)"
    assert f"FprimePython::check_declared_size(msg, FW_MIN({log}, {unsized}));" in source
    assert "return self.log_ACTIVITY_LO_Spoke(msg);" in source
    channel = f"FprimePython::check_declared_size(arg, FW_MIN({tlm}, static_cast<FwSizeType>(6)));"
    assert channel in source
    assert source.index(channel) < source.index("self.tlmWrite_Last(arg, _tlmTime);")
    assert f"FprimePython::check_declared_size(arg, FW_MIN({tlm}, {unsized}));" in source
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


@pytest.fixture
def hooks(tmp_path: Path) -> Dict[str, str]:
    return generate("Hooks.fpp", tmp_path)


def test_overflow_hooks_are_forwarded_into_python(hooks: Dict[str, str]) -> None:
    header = hooks["PyHooks.hpp"]
    assert "//! Overflow hook for command DO" in header
    assert "void textIn_overflowHook(" in header
    assert "void poke_overflowHook(const Fw::InternalInterfaceString& note) override;" in header
    assert "void DO_cmdOverflowHook(" in header
    source = hooks["PyHooks.cpp"]
    calls = [
        'm_self.attr("textIn_overflowHook")(portNum, note);',
        'm_self.attr("poke_overflowHook")(note);',
        # A command's hook gets the opcode and sequence number, not the command's arguments
        'm_self.attr("DO_cmdOverflowHook")(opCode, cmdSeq);',
    ]
    for call in calls:
        # The hook runs on the caller's thread, so it must take the GIL itself before calling Python
        body = source[source.rindex("PyHooks ::", 0, source.index(call)):source.index(call)]
        assert "pybind11::gil_scoped_acquire acquired{};" in body


def test_missing_overflow_hooks_are_reported_at_init(hooks: Dict[str, str]) -> None:
    source = hooks["PyHooks.cpp"]
    init = source[source.index('.attr("_init_ac")(this);'):source.index("PyHooksComponentBase::init(")]
    for hook in ("textIn_overflowHook", "poke_overflowHook", "DO_cmdOverflowHook"):
        check = init[init.index(f'if (!pybind11::hasattr(pybind11::type::of(this->m_self), "{hook}")) {{'):]
        check = check[:check.index("}")]
        assert "this->m_self = pybind11::none();" in check
        assert f'throw pybind11::attribute_error("PyHooks does not implement overflow hook {hook}");' in check


def test_overflow_hooks_get_python_stubs(hooks: Dict[str, str]) -> None:
    template = hooks["PyHooks.template.py"]
    assert "def textIn_overflowHook(self, portNum, note):" in template
    assert "def poke_overflowHook(self, note):" in template
    assert '""" Handle the DO command overflow hook """' in template
    start = template.index("def DO_cmdOverflowHook(self, opCode, cmdSeq):")
    end = template.find("\n    def ", start)
    hook = template[start:end if end != -1 else len(template)]
    assert "self.cmdResponse_out(opCode, cmdSeq, fprime_py.Fw.CmdResponse(fprime_py.Fw.CmdResponse.T.BUSY))" in hook


def test_members_without_hook_get_no_overflow_hook(files: Dict[str, str], hooks: Dict[str, str]) -> None:
    assert "dropIn_overflowHook" not in hooks["PyHooks.cpp"]
    assert "PLAIN_cmdOverflowHook" not in hooks["PyHooks.cpp"]
    assert "PLAIN_cmdOverflowHook" not in hooks["PyHooks.template.py"]
    assert "overflowHook" not in files["PyQueued.cpp"]
    assert "overflowHook" not in files["PyQueued.template.py"]


@pytest.fixture
def machines(tmp_path: Path) -> Dict[str, str]:
    return generate("StateMachines.fpp", tmp_path)


def handler_body(source: str, call: str) -> str:
    """ The text of the generated handler definition leading up to a call it makes """
    return source[source.rindex(" ::", 0, source.index(call)):source.index(call)]


def test_state_machine_actions_and_guards_are_declared(machines: Dict[str, str]) -> None:
    header = machines["PySm.hpp"]
    assert (
        "void Fixture_Blinker_action_store(\n"
        "          SmId smId, //!< The state machine id\n"
        "          Fixture_Blinker::Signal signal, //!< The signal\n"
        "          U32 value\n"
        "      ) override;"
    ) in header
    assert "void Fixture_Blinker_action_reset(" in header
    # A guard is const and answers with a bool, as F Prime declares it
    assert (
        "bool Fixture_Blinker_guard_allow(\n"
        "          SmId smId, //!< The state machine id\n"
        "          Fixture_Blinker::Signal signal, //!< The signal\n"
        "          U32 value\n"
        "      ) const override;"
    ) in header
    # A machine defined inside the component is named as F Prime names it, with the component folded in
    assert "void Fixture_PySm_Local_action_note(" in header
    # Two instances of one machine share its handlers
    assert header.count("Fixture_Blinker_action_store(") == 1


def test_state_machine_handlers_are_forwarded_into_python(machines: Dict[str, str]) -> None:
    source = machines["PySm.cpp"]
    calls = [
        'm_self.attr("Fixture_Blinker_action_store")(smId, signal, value);',
        'm_self.attr("Fixture_Blinker_action_reset")(smId, signal);',
        'm_self.attr("Fixture_PySm_Local_action_note")(smId, signal);',
        'pybind11::object return_value = m_self.attr("Fixture_Blinker_guard_allow")(smId, signal, value);',
    ]
    for call in calls:
        assert "pybind11::gil_scoped_acquire acquired{};" in handler_body(source, call)
    assert "bool PySm ::\n    Fixture_Blinker_guard_allow(" in source
    guard = source[source.index('attr("Fixture_Blinker_guard_allow")'):]
    guard = guard[:guard.index("\n  }")]
    # Anything but a bool is refused rather than converted, None included
    assert "if (!pybind11::isinstance<pybind11::bool_>(return_value)) {" in guard
    assert 'throw pybind11::type_error("PySm.Fixture_Blinker_guard_allow must return a bool");' in guard
    assert "return return_value.cast<bool>();" in guard


def test_missing_state_machine_handlers_are_reported_at_init(machines: Dict[str, str]) -> None:
    source = machines["PySm.cpp"]
    init = source[source.index('.attr("_init_ac")(this);'):source.index("PySmComponentBase::init(")]
    expected = [
        ("action", "Fixture_Blinker_action_store"),
        ("action", "Fixture_Blinker_action_reset"),
        ("guard", "Fixture_Blinker_guard_allow"),
        ("action", "Fixture_PySm_Local_action_note"),
    ]
    for kind, handler in expected:
        check = init[init.index(f'if (!pybind11::hasattr(pybind11::type::of(this->m_self), "{handler}")) {{'):]
        check = check[:check.index("}")]
        assert "this->m_self = pybind11::none();" in check
        assert f'throw pybind11::attribute_error("PySm does not implement state machine {kind} {handler}");' in check


def test_state_machine_handlers_get_python_stubs(machines: Dict[str, str]) -> None:
    template = machines["PySm.template.py"]
    assert "def Fixture_Blinker_action_store(self, smId, signal, value):" in template
    assert "def Fixture_Blinker_action_reset(self, smId, signal):" in template
    assert "def Fixture_PySm_Local_action_note(self, smId, signal):" in template
    start = template.index("def Fixture_Blinker_guard_allow(self, smId, signal, value):")
    guard = template[start:template.index("\n    def ", start)]
    assert "returning a bool. Returning False (this stub) blocks the transition" in guard
    assert "return False" in guard


def test_state_machine_instance_methods_are_bound(machines: Dict[str, str]) -> None:
    header = machines["PySm.hpp"]
    binding = machines["PySmBindingAc.cpp"]
    for instance in ("first", "second"):
        for method in ("getState", "sendSignal_advance", "sendSignal_back", "sendSignal_rename"):
            assert f"using PySmComponentBase::{instance}_{method};" in header
        assert f'.def("{instance}_getState", &Fixture::PySm::{instance}_getState)' in binding
        assert f'.def("{instance}_sendSignal_advance", &Fixture::PySm::{instance}_sendSignal_advance)' in binding
        # A sized string signal is checked against its declared size before F Prime serializes it
        assert (
            f'.def("{instance}_sendSignal_rename", [](Fixture::PySm& self, const Fw::StringBase& value) {{\n'
            "          FprimePython::check_declared_size(value, 8);\n"
            f"          return self.{instance}_sendSignal_rename(value);\n"
            "      })"
        ) in binding
    assert '.def("loc_sendSignal_go", &Fixture::PySm::loc_sendSignal_go)' in binding


def test_state_machine_ids_are_bound_in_the_component(files: Dict[str, str], machines: Dict[str, str]) -> None:
    assert "using PySmComponentBase::SmId;" in machines["PySm.hpp"]
    binding = machines["PySmBindingAc.cpp"]
    assert 'pybind11::class_<Fixture::PySm> component(m, "PySm");' in binding
    assert (
        'pybind11::native_enum<Fixture::PySm::SmId>(component, "SmId", "enum.Enum")\n'
        '      .value("first", Fixture::PySm::SmId::first)\n'
        '      .value("loc", Fixture::PySm::SmId::loc)\n'
        '      .value("second", Fixture::PySm::SmId::second)\n'
        "      .finalize();"
    ) in binding
    assert "#include <pybind11/native_enum.h>" in binding
    # Components without state machines are bound as before
    assert "SmId" not in files["PyQueuedBindingAc.cpp"]
    assert 'pybind11::class_<Fixture::PyQueued>(m, "PyQueued")' in files["PyQueuedBindingAc.cpp"]


def test_state_machine_states_and_signals_are_bound_once_per_machine(machines: Dict[str, str]) -> None:
    binding = machines["BlinkerStateMachineBindingAc.cpp"]
    assert '#include "BlinkerStateMachineAc.hpp"' in binding
    assert "void init_Fixture_Blinker_StateMachine(pybind11::module_& m) {" in binding
    assert 'pybind11::class_<Fixture::Blinker_State> enumeration(m, "Blinker_State");' in binding
    assert (
        'pybind11::native_enum<Fixture::Blinker_State::T>(enumeration, "T", "enum.Enum")\n'
        '      .value("__FPRIME_UNINITIALIZED", Fixture::Blinker_State::__FPRIME_UNINITIALIZED)\n'
        '      .value("BUSY", Fixture::Blinker_State::BUSY)\n'
        '      .value("IDLE", Fixture::Blinker_State::IDLE)\n'
        "      .export_values()\n"
        "      .finalize();"
    ) in binding
    # The initial-transition signal is bound too: an action on the initial transition receives it
    signal = "Fixture::BlinkerStateMachineBase::Signal"
    assert (
        f'pybind11::native_enum<{signal}>(m, "Blinker_Signal", "enum.Enum")\n'
        f'      .value("__FPRIME_INITIAL_TRANSITION", {signal}::__FPRIME_INITIAL_TRANSITION)\n'
        f'      .value("advance", {signal}::advance)\n'
        f'      .value("back", {signal}::back)\n'
        f'      .value("rename", {signal}::rename)\n'
        "      .finalize();"
    ) in binding
    assert json.loads(machines["BlinkerStateMachineBinding.json"]) == {
        "Fixture": "(void) init_Fixture_Blinker_StateMachine(fprime_Fixture);"
    }
    # Two instances and two components share Blinker, and it is still registered exactly once
    registrations = [
        name for name, contents in machines.items() if '"Blinker_State"' in contents or '"Blinker_Signal"' in contents
    ]
    assert registrations == ["BlinkerStateMachineBindingAc.cpp"]
    # An external machine has nothing to bind
    assert not [name for name in machines if name.startswith("Outside")]


def test_nested_state_machine_is_bound_under_its_module(machines: Dict[str, str]) -> None:
    binding = machines["PySm_LocalStateMachineBindingAc.cpp"]
    assert '#include "PySm_LocalStateMachineAc.hpp"' in binding
    assert 'pybind11::class_<Fixture::PySm_Local_State> enumeration(m, "PySm_Local_State");' in binding
    assert 'pybind11::native_enum<Fixture::PySm_LocalStateMachineBase::Signal>(m, "PySm_Local_Signal"' in binding
    assert json.loads(machines["PySm_LocalStateMachineBinding.json"]) == {
        "Fixture": "(void) init_Fixture_PySm_Local_StateMachine(fprime_Fixture);"
    }


def test_state_machine_defined_elsewhere_is_not_bound_again(tmp_path: Path) -> None:
    model = load_model(
        [FIXTURES / "SmShared.fpp"], [FIXTURES / "Config.fpp", FIXTURES / "StateMachines.fpp"]
    )
    visitor = AnnotatedDefinitionVisitor(tmp_path, model.analysis, IncludeManager([FIXTURES]))
    files = {path.name: contents for path, contents in visitor.generate(model).items()}
    assert "void Fixture_Blinker_action_store(" in files["PyElsewhere.hpp"]
    assert not [name for name in files if "StateMachineBinding" in name]


def test_external_state_machine_instance_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedModelError) as error:
        generate("SmExternal.fpp", tmp_path)
    message = str(error.value)
    assert "Component Fixture.PyExternal has state machine instance ext of external state machine" in message
    assert "hand-written C++ interface Fixture::Outside_Interface, not in the model" in message


def test_state_machine_instance_with_hook_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedModelError) as error:
        generate("SmHook.fpp", tmp_path)
    message = str(error.value)
    assert "Component Fixture.PySmHook has state machine instance toggle with 'hook' queue-full behavior" in message
    assert (
        "toggle_stateMachineOverflowHook takes the signal as a raw FwEnumStoreType and its value as a raw serial buffer"
    ) in message


def test_state_machine_values_follow_f_prime_parameter_spelling(machines: Dict[str, str]) -> None:
    header = machines["PyWide.hpp"]
    # F Prime passes a value by value only when its declared type is primitive: an alias of U32 goes by reference
    assert (
        "void Fixture_Wide_action_onCount(\n"
        "          SmId smId, //!< The state machine id\n"
        "          Fixture_Wide::Signal signal, //!< The signal\n"
        "          const Fixture::Count& value\n"
        "      ) override;"
    ) in header
    assert "          const Fixture::Mode& value\n      ) override;" in header
    assert "          const Fixture::Pair& value\n      ) override;" in header
    assert "          const Fw::StringBase& value\n      ) override;" in header
    assert "          const Fixture::Count& value\n      ) const override;" in header
    assert "          const Fixture::Mode& value\n      ) const override;" in header
    assert "Fixture::Count value" not in header


def test_state_machine_with_nested_states_and_choice_is_bound(machines: Dict[str, str]) -> None:
    binding = machines["WideStateMachineBindingAc.cpp"]
    for state in ("__FPRIME_UNINITIALIZED", "LAST", "OUTER_INNER"):
        assert f'.value("{state}", Fixture::Wide_State::{state})' in binding
    # Signals are bound in the order of their values, which F Prime assigns by name
    signal = "Fixture::WideStateMachineBase::Signal"
    names = ["__FPRIME_INITIAL_TRANSITION", "count", "hop", "label", "mode", "pair"]
    assert "".join(f'      .value("{name}", {signal}::{name})\n' for name in names) in binding
    assert "void Fixture_Wide_guard_checkCount(" not in machines["PyWide.hpp"]
    assert "bool Fixture_Wide_guard_checkCount(" in machines["PyWide.hpp"]


def test_blocking_state_machine_signals_release_the_gil(machines: Dict[str, str]) -> None:
    binding = machines["PyWideBindingAc.cpp"]
    release = "pybind11::call_guard<pybind11::gil_scoped_release>()"
    assert f'.def("wide_sendSignal_hop", &Fixture::PyWide::wide_sendSignal_hop, {release})' in binding
    assert f'.def("wide_sendSignal_count", &Fixture::PyWide::wide_sendSignal_count, {release})' in binding
    # A string is checked while the GIL is still held, then the GIL is released for the send
    assert (
        '.def("wide_sendSignal_label", [](Fixture::PyWide& self, const Fw::StringBase& value) {\n'
        "          FprimePython::check_declared_size(value, FW_FIXED_LENGTH_STRING_SIZE);\n"
        "          pybind11::gil_scoped_release released{};\n"
        "          return self.wide_sendSignal_label(value);\n"
    ) in binding
    # Instances that do not block keep the GIL
    assert "gil_scoped_release" not in machines["PySmBindingAc.cpp"]


def test_unbound_external_state_machines_get_no_bindings(machines: Dict[str, str]) -> None:
    assert not [name for name in machines if name.startswith(("Outside", "PyWide_Hidden", "Hidden"))]


def test_state_machine_defined_in_another_component_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedModelError) as error:
        generate("SmForeign.fpp", tmp_path)
    message = str(error.value)
    assert (
        "Component Fixture.PyForeign has state machine instance borrowed of state machine Fixture.Owner.Inner"
    ) in message
    assert "which is defined inside another component" in message


def test_data_products_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedModelError, match="Component Fixture.PyProducts has data products"):
        generate("SmProducts.fpp", tmp_path)
