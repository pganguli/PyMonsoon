"""Tests for the parts of PyMonsoon that do not need a Power Monitor attached.

UnitTests/HVPM_tests.py is upstream's suite and needs hardware, so nothing in it runs
in CI or on a laptop. That left the arithmetic untested -- and the arithmetic is where
this package had been quietly broken for years. Every test below covers a defect that
was actually present, or pins behaviour a caller now depends on.
"""

import csv
import inspect
import pathlib
from typing import Any

import pytest

from Monsoon import LVPM
from Monsoon import Operations as op
from Monsoon.calibrationData import calibrationData
from Monsoon.sampleEngine import SampleEngine, channels, triggers


class FakeMonsoon:
    """Just enough of an LVPM for SampleEngine.__init__ to complete.

    SampleEngine reads five scaling attributes off the device at construction and
    otherwise talks to it only while sampling, so a plain object is enough to reach
    the CSV and trigger logic.
    """

    fineThreshold = 64000
    auxFineThreshold = 30000
    mainvoltageScale = 4
    usbVoltageScale = 2


def make_engine() -> SampleEngine:
    return SampleEngine(FakeMonsoon())


def priv(engine: SampleEngine, name: str) -> Any:  # noqa: ANN401
    """Read a name-mangled private of SampleEngine.

    Any is unavoidable and is why these three carry a noqa: the values crossing
    this boundary are engine internals of a dozen different types, and naming them
    would pin details of an implementation these tests exist to be independent of.

    Going through getattr rather than spelling _SampleEngine__x inline keeps the
    mangling in one place, and keeps a type checker from reporting every access as an
    unresolved attribute -- which it is, statically; the name only exists at runtime.
    """
    return getattr(engine, f"_SampleEngine__{name}")


def set_priv(engine: SampleEngine, name: str, value: Any) -> None:  # noqa: ANN401
    setattr(engine, f"_SampleEngine__{name}", value)


def call_priv(engine: SampleEngine, name: str, *args: Any) -> Any:  # noqa: ANN401
    return getattr(engine, f"_SampleEngine__{name}")(*args)


# --- calibrationData ---------------------------------------------------------


def test_not_calibrated_until_every_channel_has_a_full_window() -> None:
    cal = calibrationData(calsToKeep=3)
    assert not cal.calibrated()
    for _ in range(3):
        cal.addRefCal(100, True)
        cal.addZeroCal(10, True)
    # Coarse is complete; fine has had nothing.
    assert not cal.calibrated()
    for _ in range(3):
        cal.addRefCal(200, False)
        cal.addZeroCal(20, False)
    assert cal.calibrated()


def test_reading_calibration_before_it_is_ready_raises() -> None:
    """Rather than returning a plausible average of the zeros it was seeded with,
    which would scale every sample in the capture by a wrong constant."""
    cal = calibrationData(calsToKeep=2)
    with pytest.raises(ValueError):
        cal.getRefCal(True)


def test_calibration_averages_the_window() -> None:
    cal = calibrationData(calsToKeep=2)
    for value in (10, 20):
        cal.addRefCal(value, True)
        cal.addZeroCal(value, True)
        cal.addRefCal(value, False)
        cal.addZeroCal(value, False)
    assert cal.getRefCal(True) == 15
    assert cal.getZeroCal(False) == 15


def test_zero_readings_are_ignored_rather_than_averaged_in() -> None:
    """addRefCal/addZeroCal skip 0. A zero is a packet that had no calibration in it,
    not a calibration measurement of zero, and averaging it in would drag the
    reference down."""
    cal = calibrationData(calsToKeep=2)
    for _ in range(4):
        cal.addRefCal(0, True)
    assert not cal.calibrated()


# --- LVPM conversions --------------------------------------------------------


def test_amps_and_raw_round_trip() -> None:
    monsoon = LVPM.Monsoon.__new__(LVPM.Monsoon)
    for amps in (0.0, 1.0, 4.0, 8.0):
        raw = monsoon.raw_from_amps(amps)
        assert monsoon.amps_from_raw(raw) == pytest.approx(amps)


def test_amps_from_raw_saturates_at_the_top_of_the_dac() -> None:
    monsoon = LVPM.Monsoon.__new__(LVPM.Monsoon)
    assert monsoon.amps_from_raw(1023) == pytest.approx(0.0)
    assert monsoon.amps_from_raw(5000) == monsoon.amps_from_raw(1023)


def test_current_limit_setters_reach_the_protocol() -> None:
    """Regression: both called self.__raw_from_amps(), which name-mangles to a method
    that does not exist, so every call raised AttributeError and the limit was never
    applied. A caller that believed it had protected the device under test had not."""
    sent = []

    class RecordingProtocol:
        def sendCommand(self, operation: int, value: float) -> None:
            sent.append((operation, value))

    monsoon = LVPM.Monsoon.__new__(LVPM.Monsoon)
    monsoon.Protocol = RecordingProtocol()

    monsoon.setRunTimeCurrentLimit(2.0)
    monsoon.setPowerUpCurrentLimit(4.0)

    assert [operation for operation, _ in sent] == [
        op.OpCodes.SetRunCurrentLimit,
        op.OpCodes.SetPowerUpCurrentLimit,
    ]
    # 2 A of an 8 A range is three quarters of the way up an inverted 0-1023 scale.
    assert sent[0][1] == pytest.approx(1023 * 0.75)
    assert sent[1][1] == pytest.approx(1023 * 0.5)


@pytest.mark.parametrize("volts", [2.0, 4.56, 5.0, -1.0])
def test_setvout_rejects_values_outside_the_lvpm_range(volts: float) -> None:
    """The LVPM's regulator covers 2.01-4.55 V. Accepting a value outside it would
    leave the rail at whatever it was, so a capture would be of the wrong supply."""
    monsoon = LVPM.Monsoon.__new__(LVPM.Monsoon)
    monsoon.Protocol = None  # never reached; a pass would raise AttributeError instead
    with pytest.raises(Exception, match="Invalid Voltage"):
        monsoon.setVout(volts)


def test_setvout_accepts_zero_as_off() -> None:
    sent = []

    class RecordingProtocol:
        def sendCommand(self, operation: int, value: float) -> None:
            sent.append((operation, value))

    monsoon = LVPM.Monsoon.__new__(LVPM.Monsoon)
    monsoon.Protocol = RecordingProtocol()
    monsoon.setVout(0)
    assert sent == [(op.OpCodes.setMainVoltage, 0)]


# --- CSV output --------------------------------------------------------------


def read_back(engine: SampleEngine, tmp_path: pathlib.Path) -> list[list[str]]:
    engine.disableCSVOutput()
    with open(tmp_path / "out.csv", newline="") as handle:
        return list(csv.reader(handle))


def test_csv_values_are_numbers_not_numpy_reprs(tmp_path: pathlib.Path) -> None:
    """Regression: values were written with repr(). Current and voltage samples are
    numpy scalars, and NumPy 2 changed their repr, so every row came out as
    'np.float64(1.234)' -- an unparseable file produced without any complaint."""
    import numpy as np

    engine = make_engine()
    engine.enableCSVOutput(str(tmp_path / "out.csv"))
    engine.outputCSVHeaders()
    set_priv(engine, "timeStamps", [[np.float64(0.5)]])
    set_priv(engine, "mainCurrent", [[np.float64(1.25)]])
    set_priv(engine, "mainVoltage", [[np.float64(3.0)]])
    call_priv(engine, "outputToCSV")

    rows = read_back(engine, tmp_path)
    assert rows[0] == ["Time(s)", "Main(mA)", "Main Voltage(V)"]
    assert rows[1] == ["0.5", "1.25", "3.0"]
    assert all(float(cell) == float(cell) for cell in rows[1])


def test_csv_has_no_trailing_empty_column(tmp_path: pathlib.Path) -> None:
    """Every row used to end in a comma, so a reader saw a fourth, always-empty
    field and a header one column narrower than the data."""
    engine = make_engine()
    engine.enableCSVOutput(str(tmp_path / "out.csv"))
    engine.outputCSVHeaders()
    set_priv(engine, "timeStamps", [[0.0, 1.0]])
    set_priv(engine, "mainCurrent", [[1.0, 2.0]])
    set_priv(engine, "mainVoltage", [[3.0, 3.0]])
    call_priv(engine, "outputToCSV")

    rows = read_back(engine, tmp_path)
    assert all(len(row) == len(rows[0]) for row in rows)


def test_every_sample_handed_over_is_written(tmp_path: pathlib.Path) -> None:
    """Regression: __getMeasurement has already applied `granularity` by the time
    samples reach __outputToCSV, and that method divided by it a second time --
    writing len/granularity of the already-thinned rows and dropping the rest. At
    granularity=10 about 1% survived rather than 10%. __arrangeSamples clears its
    lists as it hands them over, so what is not written here is gone."""
    engine = make_engine()
    set_priv(engine, "granularity", 10)
    engine.enableCSVOutput(str(tmp_path / "out.csv"))
    engine.outputCSVHeaders()
    set_priv(engine, "timeStamps", [[float(i) for i in range(20)]])
    set_priv(engine, "mainCurrent", [[float(i) for i in range(20)]])
    set_priv(engine, "mainVoltage", [[3.0] * 20])
    call_priv(engine, "outputToCSV")

    rows = read_back(engine, tmp_path)
    assert len(rows) == 21  # header plus 20 samples


def test_disabled_channels_are_absent_from_both_header_and_rows(
    tmp_path: pathlib.Path,
) -> None:
    engine = make_engine()
    engine.disableChannel(channels.MainVoltage)
    engine.enableCSVOutput(str(tmp_path / "out.csv"))
    engine.outputCSVHeaders()

    engine.disableCSVOutput()
    with open(tmp_path / "out.csv", newline="") as handle:
        header = next(csv.reader(handle))
    assert header == ["Time(s)", "Main(mA)"]


def test_headers_do_not_need_a_file_to_have_been_opened_twice(
    tmp_path: pathlib.Path,
) -> None:
    """enableCSVOutput builds the writer; a second enable on the same engine must
    not leave the first file handle dangling."""
    engine = make_engine()
    engine.enableCSVOutput(str(tmp_path / "first.csv"))
    first = priv(engine, "f")
    engine.disableCSVOutput()
    assert first.closed
    assert priv(engine, "csv") is None


# --- stop trigger ------------------------------------------------------------


def test_sample_limit_compares_by_value_not_identity() -> None:
    """Regression: `is not SAMPLECOUNT_INFINITE`. 0xFFFFFFFF is far outside CPython's
    small-integer cache, so identity held only when the caller passed that very
    object through -- and stopped holding the moment the limit came from arithmetic,
    a config file or a command line."""
    engine = make_engine()
    set_priv(engine, "granularity", 1)
    # Equal to SAMPLECOUNT_INFINITE, but a distinct object.
    set_priv(engine, "sampleLimit", int("4294967295"))
    set_priv(engine, "sampleCount", 10**9)
    call_priv(engine, "evalStopTrigger", [0.0])
    assert not priv(engine, "stopTriggerSet")


def test_a_finite_sample_limit_still_stops() -> None:
    engine = make_engine()
    set_priv(engine, "granularity", 1)
    set_priv(engine, "sampleLimit", 100)
    set_priv(engine, "sampleCount", 100)
    call_priv(engine, "evalStopTrigger", [0.0])
    assert priv(engine, "stopTriggerSet")


# --- capture health ----------------------------------------------------------


def test_dropped_count_keeps_the_high_water_mark() -> None:
    """self.dropped is overwritten by every packet, so at the end of a capture it
    reports whatever the last one said. A caller asking whether any samples were lost
    cannot answer that from a value reset thousands of times."""
    engine = make_engine()
    call_priv(
        engine,
        "processPacket",
        [
            [0, 0, 0],
            [7, 0, 0],
            [2, 0, 0],
        ],
    )
    assert engine.dropped == 2
    assert engine.droppedCount == 7


def test_error_state_is_readable_and_set_by_the_packet_flag() -> None:
    engine = make_engine()
    assert engine.errorState is False
    call_priv(engine, "processPacket", [[0, 0x10, 0]])
    assert engine.errorState is True


def test_reset_clears_per_capture_health() -> None:
    """Without this a second run on the same engine inherits the first one's verdict,
    and a clean capture is reported as having dropped samples."""
    engine = make_engine()
    call_priv(engine, "processPacket", [[5, 0x10, 0]])
    assert engine.errorState and engine.droppedCount == 5
    call_priv(engine, "Reset")
    assert engine.errorState is False
    assert engine.droppedCount == 0


# --- trigger predicates ------------------------------------------------------


def test_trigger_predicates() -> None:
    assert triggers.GREATER_THAN(2, 1)
    assert not triggers.GREATER_THAN(1, 2)
    assert triggers.LESS_THAN(1, 2)
    assert not triggers.LESS_THAN(2, 1)


def test_channel_indices_line_up_with_channel_names() -> None:
    """getSamples() returns a list indexed by sampleEngine.channels, so a name added
    out of order would silently mislabel a column."""
    engine = make_engine()
    names = priv(engine, "channelnames")
    assert names[channels.timeStamp].startswith("Time")
    assert names[channels.MainCurrent] == "Main(mA)"
    assert names[channels.MainVoltage] == "Main Voltage(V)"


def test_timestamp_column_is_labelled_in_seconds() -> None:
    """It carries time.time() deltas. Upstream called it Time(ms), which is wrong by
    a factor of a thousand for anyone who trusted the header."""
    engine = make_engine()
    assert priv(engine, "channelnames")[channels.timeStamp] == "Time(s)"


def test_module_imports_without_scipy() -> None:
    """scipy was declared as a dependency and imported at the top of sampleEngine,
    but never called. Dropping it removes a large compiled dependency from a package
    whose only job here is to read a USB device."""
    sourcefile = inspect.getsourcefile(SampleEngine)
    assert sourcefile is not None
    assert "scipy" not in pathlib.Path(sourcefile).read_text()
