from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple


DEFAULT_SUPPORTED_AXES = ("x", "y")
DEFAULT_MAX4_XY_BOUNDS = (0.0, 325.0, 0.0, 325.0)


@dataclass(frozen=True)
class PrinterLimits:
    kinematics: Optional[str] = None
    max_velocity: Optional[float] = None
    max_accel: Optional[float] = None
    max_z_velocity: Optional[float] = None
    max_z_accel: Optional[float] = None
    square_corner_velocity: Optional[float] = None


@dataclass(frozen=True)
class ResonanceTesterConfig:
    accel_chip: Optional[str] = None
    accel_per_hz: Optional[float] = None
    max_smoothing: Optional[float] = None
    probe_points: Tuple[Tuple[float, float, float], ...] = ()

    @property
    def primary_probe_point(self) -> Optional[Tuple[float, float, float]]:
        return self.probe_points[0] if self.probe_points else None


@dataclass(frozen=True)
class Lis2dwConfig:
    section: str = "lis2dw"
    axes_map: Optional[str] = None
    cs_pin: Optional[str] = None
    spi_bus: Optional[str] = None
    spi_speed: Optional[int] = None

    @property
    def accelerometer_identity(self) -> str:
        return self.section


@dataclass(frozen=True)
class InputShaperConfig:
    shaper_type_x: Optional[str] = None
    shaper_freq_x: Optional[float] = None
    shaper_type_y: Optional[str] = None
    shaper_freq_y: Optional[float] = None
    damping_ratio_x: Optional[float] = None
    damping_ratio_y: Optional[float] = None


@dataclass(frozen=True)
class MotorMetadata:
    axis: str
    section: str
    run_current: Optional[float] = None
    hold_current: Optional[float] = None
    home_current: Optional[float] = None
    microsteps: Optional[int] = None
    raw_fields: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Max4ConfigSummary:
    printer: PrinterLimits = field(default_factory=PrinterLimits)
    resonance_tester: ResonanceTesterConfig = field(default_factory=ResonanceTesterConfig)
    lis2dw: Lis2dwConfig = field(default_factory=Lis2dwConfig)
    input_shaper: InputShaperConfig = field(default_factory=InputShaperConfig)
    motors: Mapping[str, MotorMetadata] = field(default_factory=dict)
    raw_sections: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    supported_axes: Tuple[str, str] = DEFAULT_SUPPORTED_AXES
    xy_bounds: Tuple[float, float, float, float] = DEFAULT_MAX4_XY_BOUNDS

    @property
    def axes_map(self) -> Optional[str]:
        return self.lis2dw.axes_map

    @property
    def accelerometer_identity(self) -> str:
        if self.resonance_tester.accel_chip:
            return self.resonance_tester.accel_chip
        return self.lis2dw.accelerometer_identity


def parse_max4_config(source: str | Path) -> Max4ConfigSummary:
    text = Path(source).read_text() if isinstance(source, Path) else source
    sections = _parse_klipper_ini(text)
    return Max4ConfigSummary(
        printer=_parse_printer(sections.get("printer", {})),
        resonance_tester=_parse_resonance_tester(sections.get("resonance_tester", {})),
        lis2dw=_parse_lis2dw(sections),
        input_shaper=_parse_input_shaper(sections.get("input_shaper", {})),
        motors=_parse_closed_loop_motors(sections),
        raw_sections=sections,
        xy_bounds=_parse_xy_bounds(sections),
    )


def _parse_klipper_ini(text: str) -> Dict[str, Dict[str, str]]:
    sections: Dict[str, Dict[str, str]] = {}
    current: Optional[str] = None
    for raw_line in text.splitlines():
        line = _strip_comment(raw_line).strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip().lower()
            sections.setdefault(current, {})
            continue
        if current is None:
            continue
        if ":" in line:
            key, value = line.split(":", 1)
        elif "=" in line:
            key, value = line.split("=", 1)
        else:
            continue
        sections[current][key.strip().lower()] = value.strip()
    return sections


def _strip_comment(line: str) -> str:
    for marker in ("#", ";"):
        index = line.find(marker)
        if index >= 0:
            line = line[:index]
    return line


def _parse_printer(data: Mapping[str, str]) -> PrinterLimits:
    return PrinterLimits(
        kinematics=data.get("kinematics"),
        max_velocity=_float(data.get("max_velocity")),
        max_accel=_float(data.get("max_accel")),
        max_z_velocity=_float(data.get("max_z_velocity")),
        max_z_accel=_float(data.get("max_z_accel")),
        square_corner_velocity=_float(data.get("square_corner_velocity")),
    )


def _parse_resonance_tester(data: Mapping[str, str]) -> ResonanceTesterConfig:
    return ResonanceTesterConfig(
        accel_chip=data.get("accel_chip"),
        accel_per_hz=_float(data.get("accel_per_hz")),
        max_smoothing=_float(data.get("max_smoothing")),
        probe_points=tuple(_parse_probe_points(data.get("probe_points"))),
    )


def _parse_lis2dw(sections: Mapping[str, Mapping[str, str]]) -> Lis2dwConfig:
    section_name = next((name for name in sections if name == "lis2dw" or name.startswith("lis2dw ")), "lis2dw")
    data = sections.get(section_name, {})
    return Lis2dwConfig(
        section=section_name,
        axes_map=data.get("axes_map"),
        cs_pin=data.get("cs_pin"),
        spi_bus=data.get("spi_bus"),
        spi_speed=_int(data.get("spi_speed")),
    )


def _parse_input_shaper(data: Mapping[str, str]) -> InputShaperConfig:
    return InputShaperConfig(
        shaper_type_x=data.get("shaper_type_x"),
        shaper_freq_x=_float(data.get("shaper_freq_x")),
        shaper_type_y=data.get("shaper_type_y"),
        shaper_freq_y=_float(data.get("shaper_freq_y")),
        damping_ratio_x=_float(data.get("damping_ratio_x")),
        damping_ratio_y=_float(data.get("damping_ratio_y")),
    )


def _parse_closed_loop_motors(sections: Mapping[str, Mapping[str, str]]) -> Dict[str, MotorMetadata]:
    motors: Dict[str, MotorMetadata] = {}
    for axis in ("x", "y"):
        section = f"closed_loop {axis}"
        data = sections.get(section)
        if data is None:
            continue
        motors[axis] = MotorMetadata(
            axis=axis,
            section=section,
            run_current=_first_float(data, ("run_current", "current", "driver_sgthrs_current")),
            hold_current=_first_float(data, ("hold_current", "idle_current")),
            home_current=_first_float(data, ("home_current", "homing_current")),
            microsteps=_first_int(data, ("microsteps", "microstep")),
            raw_fields=dict(data),
        )
    return motors


def _parse_xy_bounds(sections: Mapping[str, Mapping[str, str]]) -> Tuple[float, float, float, float]:
    x = sections.get("stepper_x", {})
    y = sections.get("stepper_y", {})
    return (
        _float(x.get("position_min"), DEFAULT_MAX4_XY_BOUNDS[0]),
        _float(x.get("position_max"), DEFAULT_MAX4_XY_BOUNDS[1]),
        _float(y.get("position_min"), DEFAULT_MAX4_XY_BOUNDS[2]),
        _float(y.get("position_max"), DEFAULT_MAX4_XY_BOUNDS[3]),
    )


def _parse_probe_points(value: Optional[str]) -> Iterable[Tuple[float, float, float]]:
    if not value:
        return ()
    points: List[Tuple[float, float, float]] = []
    normalized = value.replace("\n", ";")
    for part in normalized.split(";"):
        numbers = [_float(piece.strip()) for piece in part.split(",") if piece.strip()]
        if len(numbers) >= 3 and all(number is not None for number in numbers[:3]):
            points.append((float(numbers[0]), float(numbers[1]), float(numbers[2])))
    return tuple(points)


def _first_float(data: Mapping[str, str], keys: Iterable[str]) -> Optional[float]:
    for key in keys:
        value = _float(data.get(key))
        if value is not None:
            return value
    return None


def _first_int(data: Mapping[str, str], keys: Iterable[str]) -> Optional[int]:
    for key in keys:
        value = _int(data.get(key))
        if value is not None:
            return value
    return None


def _float(value: Optional[str], default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _int(value: Optional[str], default: Optional[int] = None) -> Optional[int]:
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except ValueError:
        return default
