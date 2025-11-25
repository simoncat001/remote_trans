#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract XRF metadata from ``.cbf`` files and populate the template."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Dict, Iterable, List, MutableMapping, Tuple

from cbf_utils import normalise_key, parse_cbf_header, parse_numeric

HERE = Path(__file__).resolve().parent
TEMPLATE_DIR = HERE.parent / "templates" / "XRF"
ENERGY_RANGE_RE = re.compile(
    r"(?P<start>[-+]?\d*\.?\d+)(?:\s*(?P<unit>ke?v|me?v|e?v|千e?v|千电子伏|电子伏|mev|kev))?"
    r"\s*(?:-|to|–|—|~|至|→|\s+)\s*(?P<end>[-+]?\d*\.?\d+)"
    r"(?:\s*(?P<unit2>ke?v|me?v|e?v|千e?v|千电子伏|电子伏|mev|kev))?",
    re.IGNORECASE,
)

HEADER_ALIASES: Dict[str, str] = {
    "experiment name": "experiment_name",
    "experiment title": "experiment_name",
    "title": "experiment_name",
    "scan title": "experiment_name",
    "project": "experiment_name",
    "dataset": "experiment_name",
    "sample": "sample_name",
    "sample name": "sample_name",
    "specimen": "sample_name",
    "样品": "sample_name",
    "样品名称": "sample_name",
    "样品编号": "sample_id",
    "sample id": "sample_id",
    "sample code": "sample_id",
    "sample description": "sample_description",
    "comment sample": "sample_description",
    "operator": "operator",
    "user": "operator",
    "collected by": "operator",
    "采集人员": "operator",
    "测试人员": "operator",
    "institution": "affiliation",
    "affiliation": "affiliation",
    "facility": "affiliation",
    "beamline": "affiliation",
    "测试单位": "affiliation",
    "user affiliation": "operator_affiliation",
    "operator affiliation": "operator_affiliation",
    "测试人员单位": "operator_affiliation",
    "用户单位": "operator_affiliation",
    "email": "operator_email",
    "邮箱": "operator_email",
    "contact": "operator_email",
    "timestamp": "timestamp",
    "date": "timestamp",
    "collection date": "timestamp",
    "acquisition date": "timestamp",
    "start time": "timestamp",
    "测量日期": "timestamp",
    "mgid": "mgid",
    "样品mgid": "sample_mgid",
    "sample mgid": "sample_mgid",
    "instrument": "instrument_name",
    "instrument name": "instrument_name",
    "equipment": "instrument_name",
    "仪器名称": "instrument_name",
    "diffrn source": "instrument_name",
    "diffrn measurement device": "instrument_name",
    "instrument model": "instrument_model",
    "model": "instrument_model",
    "仪器型号": "instrument_model",
    "diffrn source type": "source_type",
    "diffrn source target": "source_target",
    "diffrn radiation type": "source_type",
    "instrument manufacturer": "instrument_manufacturer",
    "manufacturer": "instrument_manufacturer",
    "vendor": "instrument_manufacturer",
    "仪器厂牌": "instrument_manufacturer",
    "instrument serial": "instrument_serial",
    "serial": "instrument_serial",
    "serial number": "instrument_serial",
    "仪器序列号": "instrument_serial",
    "lab": "instrument_organisation",
    "laboratory": "instrument_organisation",
    "仪器所属单位": "instrument_organisation",
    "address": "instrument_location",
    "location": "instrument_location",
    "仪器所在地址": "instrument_location",
    "x ray source": "source_type",
    "x-ray source": "source_type",
    "source": "source_type",
    "source type": "source_type",
    "source target": "source_target",
    "target": "source_target",
    "靶材": "source_target",
    "tube voltage": "beam_voltage",
    "accelerating voltage": "beam_voltage",
    "beam voltage": "beam_voltage",
    "高压": "beam_voltage",
    "管电压": "beam_voltage",
    "tube current": "beam_current",
    "beam current": "beam_current",
    "probe current": "beam_current",
    "管电流": "beam_current",
    "spot size": "beam_spot",
    "beam spot": "beam_spot",
    "光斑尺寸": "beam_spot",
    "incident angle": "incident_angle",
    "takeoff angle": "incident_angle",
    "入射角": "incident_angle",
    "wavelength": "beam_wavelength",
    "radiation wavelength": "beam_wavelength",
    "波长": "beam_wavelength",
    "diffrn radiation wavelength": "beam_wavelength",
    "incident energy": "beam_energy",
    "beam energy": "beam_energy",
    "energy": "beam_energy",
    "能量": "beam_energy",
    "xray energy": "beam_energy",
    "diffrn measurement incident beam energy": "beam_energy",
    "energy min": "scan_start_energy",
    "energy max": "scan_end_energy",
    "incident energy min": "scan_start_energy",
    "incident energy max": "scan_end_energy",
    "scan energy min": "scan_start_energy",
    "scan energy max": "scan_end_energy",
    "detector": "detector_name",
    "detector name": "detector_name",
    "diffrn detector": "detector_name",
    "detector model": "detector_model",
    "diffrn detector id": "detector_model",
    "detector type": "detector_type",
    "diffrn detector type": "detector_type",
    "detector distance": "detector_distance",
    "distance": "detector_distance",
    "diffrn detector distance": "detector_distance",
    "detector resolution": "detector_resolution",
    "energy resolution": "detector_resolution",
    "diffrn detector resolution": "detector_resolution",
    "count rate": "detector_count_rate",
    "计数率": "detector_count_rate",
    "diffrn detector count rate": "detector_count_rate",
    "exposure time": "exposure_time",
    "integration time": "exposure_time",
    "acquisition time": "exposure_time",
    "曝光时间": "exposure_time",
    "diffrn measurement exposure time": "exposure_time",
    "scan repetitions": "scan_repeats",
    "scan repeats": "scan_repeats",
    "scan count": "scan_repeats",
    "扫描次数": "scan_repeats",
    "scan mode": "scan_mode",
    "扫描方式": "scan_mode",
    "diffrn measurement method": "scan_mode",
    "calibration": "calibration",
    "校准": "calibration",
    "energy step": "scan_step",
    "步长": "scan_step",
    "temperature": "environment_temperature",
    "环境温度": "environment_temperature",
    "diffrn measurement ambient temperature": "environment_temperature",
    "humidity": "environment_humidity",
    "环境湿度": "environment_humidity",
    "diffrn measurement ambient humidity": "environment_humidity",
    "atmosphere": "environment_atmosphere",
    "环境气氛": "environment_atmosphere",
    "diffrn measurement atmosphere": "environment_atmosphere",
    "备注": "notes",
    "comment": "notes",
    "note": "notes",
}

FIELD_PATH_MAP: Dict[str, Tuple[str, ...]] = {
    "mgid": ("MGID自定义部分",),
    "experiment_name": ("实验名称",),
    "sample_name": ("样品名称",),
    "sample_id": ("样品编号",),
    "sample_description": ("样品描述",),
    "sample_mgid": ("关联样品MGID",),
    "operator": ("测试人员",),
    "affiliation": ("测试单位",),
    "operator_affiliation": ("测试人员单位",),
    "operator_email": ("测试人员邮箱",),
    "instrument_name": ("仪器名称",),
    "instrument_model": ("仪器型号",),
    "instrument_manufacturer": ("仪器厂牌",),
    "instrument_serial": ("仪器序列号",),
    "instrument_organisation": ("仪器所属单位",),
    "instrument_location": ("仪器所在地址",),
    "timestamp": ("测试日期",),
    "source_type": ("X射线源", "X射线源类型"),
    "source_target": ("X射线源", "靶材"),
    "beam_voltage": ("X射线源", "管电压"),
    "beam_current": ("X射线源", "管电流"),
    "beam_spot": ("X射线源", "光斑尺寸"),
    "beam_energy": ("X射线源", "入射能量"),
    "beam_wavelength": ("X射线源", "入射波长"),
    "incident_angle": ("X射线源", "入射角"),
    "detector_name": ("探测器", "探测器名称"),
    "detector_model": ("探测器", "探测器型号"),
    "detector_type": ("探测器", "探测器类型"),
    "detector_distance": ("探测器", "探测器距离"),
    "detector_resolution": ("探测器", "探测器能量分辨率"),
    "detector_count_rate": ("探测器", "计数率"),
    "scan_start_energy": ("测量参数", "能量起始"),
    "scan_end_energy": ("测量参数", "能量终止"),
    "scan_step": ("测量参数", "能量步长"),
    "exposure_time": ("测量参数", "曝光时间"),
    "scan_repeats": ("测量参数", "扫描次数"),
    "scan_mode": ("测量参数", "扫描方式"),
    "calibration": ("测量参数", "校准方式"),
    "environment_temperature": ("环境条件", "温度"),
    "environment_humidity": ("环境条件", "湿度"),
    "environment_atmosphere": ("环境条件", "环境气氛"),
    "notes": ("备注",),
    "raw_primary": ("原始文件", "主要数据文件"),
    "raw_listing": ("原始文件", "原始数据列表"),
}

ENERGY_RANGE_KEYS = (
    "energy range",
    "scan energy range",
    "incident energy range",
    "energy span",
)


def _resolve_template(path: str | Path | None) -> Path:
    if path is not None:
        template_path = Path(path).expanduser().resolve()
        if not template_path.is_file():
            raise FileNotFoundError(f"Template '{template_path}' does not exist")
        return template_path
    candidates = sorted(TEMPLATE_DIR.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(
            "No template JSON found under remote_trans/templates/XRF"
        )
    return candidates[0]


def _normalise_date(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    patterns = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%d %b %Y",
        "%b %d %Y",
    ]
    for fmt in patterns:
        try:
            return _dt.datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", value)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return value


def _format_voltage(value: str) -> str:
    numeric = parse_numeric(value)
    if numeric is None:
        return value.strip()
    upper = value.upper()
    if "MV" in upper or "兆伏" in value:
        return f"{numeric:.6g} MV"
    if "KV" in upper or "千伏" in value:
        return f"{numeric:.6g} kV"
    if "V" in upper or "伏" in value:
        return f"{numeric:.6g} V"
    return f"{numeric:.6g} V"


def _format_current(value: str) -> str:
    numeric = parse_numeric(value)
    if numeric is None:
        return value.strip()
    upper = value.upper()
    if "KA" in upper or "千安" in value:
        return f"{numeric:.6g} kA"
    if "MA" in upper or "毫安" in value:
        return f"{numeric:.6g} mA"
    if "UA" in upper or "ΜA" in upper or "微安" in value:
        return f"{numeric:.6g} µA"
    if "NA" in upper or "纳安" in value:
        return f"{numeric:.6g} nA"
    if "PA" in upper or "皮安" in value:
        return f"{numeric:.6g} pA"
    if "A" in upper:
        return f"{numeric:.6g} A"
    return f"{numeric:.6g} A"


def _format_time(value: str) -> str:
    numeric = parse_numeric(value)
    if numeric is None:
        return value.strip()
    upper = value.upper()
    if "MS" in upper or "毫秒" in value:
        numeric /= 1_000.0
    elif any(unit in upper for unit in ("US", "ΜS", "微秒")):
        numeric /= 1_000_000.0
    elif any(unit in upper for unit in ("NS", "纳秒")):
        numeric /= 1_000_000_000.0
    return f"{numeric:.6g} s"


def _format_angle(value: str) -> str:
    numeric = parse_numeric(value)
    if numeric is None:
        return value.strip()
    upper = value.upper()
    if "RAD" in upper:
        numeric = numeric * 180.0 / 3.141592653589793
    return f"{numeric:.6g} °"


def _format_temperature(value: str) -> str:
    numeric = parse_numeric(value)
    if numeric is None:
        return value.strip()
    upper = value.upper()
    if "K" in upper and "°" not in upper and "摄氏" not in value:
        numeric -= 273.15
    return f"{numeric:.6g} °C"


def _format_humidity(value: str) -> str:
    numeric = parse_numeric(value)
    if numeric is None:
        return value.strip()
    return f"{numeric:.6g} %"


def _format_energy(value: str) -> str:
    numeric = parse_numeric(value)
    if numeric is None:
        return value.strip()
    upper = value.upper()
    if "MEV" in upper:
        return f"{numeric:.6g} MeV"
    if "KEV" in upper or "千电子伏" in value:
        return f"{numeric:.6g} keV"
    if "EV" in upper or "电子伏" in value:
        return f"{numeric:.6g} eV"
    if "J" in upper:
        return f"{numeric:.6g} J"
    return f"{numeric:.6g} eV"


def _format_wavelength(value: str) -> str:
    numeric = parse_numeric(value)
    if numeric is None:
        return value.strip()
    upper = value.upper()
    if "NM" in upper:
        return f"{numeric:.6g} nm"
    if any(unit in upper for unit in ("Å", "ANG")):
        return f"{numeric:.6g} Å"
    if any(unit in upper for unit in ("MM", "毫米")):
        return f"{numeric:.6g} mm"
    if any(unit in upper for unit in ("UM", "ΜM", "微米")):
        return f"{numeric:.6g} µm"
    return value.strip()


def _format_length(value: str) -> str:
    numeric = parse_numeric(value)
    if numeric is None:
        return value.strip()
    upper = value.upper()
    if any(unit in upper for unit in ("MM", "毫米")):
        return f"{numeric:.6g} mm"
    if any(unit in upper for unit in ("CM", "厘米")):
        return f"{numeric:.6g} cm"
    if any(unit in upper for unit in ("UM", "ΜM", "微米")):
        return f"{numeric:.6g} µm"
    if any(unit in upper for unit in ("NM", "纳米")):
        return f"{numeric:.6g} nm"
    return value.strip()


VALUE_CONVERTERS = {
    "timestamp": _normalise_date,
    "beam_voltage": _format_voltage,
    "beam_current": _format_current,
    "beam_spot": _format_length,
    "beam_energy": _format_energy,
    "beam_wavelength": _format_wavelength,
    "incident_angle": _format_angle,
    "detector_distance": _format_length,
    "detector_resolution": _format_energy,
    "detector_count_rate": lambda v: v.strip(),
    "scan_step": _format_energy,
    "exposure_time": _format_time,
    "scan_repeats": lambda v: int(val) if (val := parse_numeric(v)) is not None else v.strip(),
    "environment_temperature": _format_temperature,
    "environment_humidity": _format_humidity,
    "environment_atmosphere": lambda v: v.strip(),
    "notes": lambda v: v.strip(),
}


def _parse_energy_range(value: str) -> Tuple[str, str] | None:
    match = ENERGY_RANGE_RE.search(value)
    if not match:
        return None
    start = float(match.group("start"))
    end = float(match.group("end"))
    unit = match.group("unit") or match.group("unit2") or "keV"
    unit = unit.lower()
    if unit.startswith("me"):
        suffix = "MeV"
    elif unit.startswith("k") or "千" in unit:
        suffix = "keV"
    elif unit.startswith("e"):
        suffix = "eV"
    else:
        suffix = "keV"
    return f"{start:.6g} {suffix}", f"{end:.6g} {suffix}"


def _coerce_value(key: str, raw: str):
    converter = VALUE_CONVERTERS.get(key)
    if not converter:
        return raw.strip()
    try:
        return converter(raw)
    except Exception:
        return raw.strip()


def extract_metadata(cbf_path: Path) -> Dict[str, object]:
    header = parse_cbf_header(cbf_path)
    metadata: Dict[str, object] = {}
    items = [(normalise_key(k), v) for k, v in header.items()]
    for normalised, value in items:
        canonical = HEADER_ALIASES.get(normalised)
        if not canonical:
            continue
        if canonical in metadata:
            continue
        coerced = _coerce_value(canonical, value)
        metadata[canonical] = coerced
    for normalised, value in items:
        if any(key in normalised for key in ENERGY_RANGE_KEYS):
            if "scan_start_energy" not in metadata and "scan_end_energy" not in metadata:
                parsed = _parse_energy_range(value)
                if parsed:
                    metadata["scan_start_energy"], metadata["scan_end_energy"] = parsed
        if "step" in normalised and "energy" in normalised and "scan_step" not in metadata:
            metadata["scan_step"] = _coerce_value("scan_step", value)
    return metadata


def _set_nested_if_exists(data: MutableMapping[str, object], path: Tuple[str, ...], value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    current: MutableMapping[str, object] | None = data
    for key in path[:-1]:
        child = current.get(key) if isinstance(current, MutableMapping) else None
        if not isinstance(child, MutableMapping):
            return False
        current = child
    last = path[-1]
    if not isinstance(current, MutableMapping) or last not in current:
        return False
    target = current[last]
    if isinstance(target, list) and not isinstance(value, list):
        current[last] = [value]
    else:
        current[last] = value
    return True


def build_output(
    template: Dict[str, object],
    metadata: Dict[str, object],
    dataset_root: Path,
    primary_cbf: Path,
    *,
    raw_listing: List[str],
) -> Dict[str, object]:
    populated = deepcopy(template)
    default_name = dataset_root.name
    metadata.setdefault("experiment_name", metadata.get("sample_name", default_name))
    metadata.setdefault("sample_name", default_name)
    metadata.setdefault("raw_primary", primary_cbf.relative_to(dataset_root).as_posix())
    metadata.setdefault("raw_listing", raw_listing)
    for key, value in metadata.items():
        path = FIELD_PATH_MAP.get(key)
        if not path:
            continue
        _set_nested_if_exists(populated, path, value)
    return populated


def locate_dataset(target: Path) -> Tuple[Path, Path]:
    if target.is_dir():
        cbf_files = sorted(target.rglob("*.cbf"))
        if not cbf_files:
            raise FileNotFoundError(f"No .cbf files found under {target}")
        primary = next((p for p in cbf_files if "master" in p.name.lower()), cbf_files[0])
        return target, primary
    if target.suffix.lower() != ".cbf":
        raise ValueError("Provide a directory or a .cbf file")
    return target.parent, target


def build_listing(dataset_root: Path, *, skip: Iterable[Path] = ()) -> List[str]:
    skip_resolved = {p.resolve() for p in skip}
    listing: List[str] = []
    for path in sorted(dataset_root.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in skip_resolved:
            continue
        listing.append(path.relative_to(dataset_root).as_posix())
    return listing


def generate_metadata(
    input_path: Path | str,
    *,
    template_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> Dict[str, object]:
    """Return a populated XRF template for ``input_path``."""

    target = Path(input_path).expanduser().resolve()
    dataset_root, primary = locate_dataset(target)

    skip_paths: List[Path] = []
    if output_path is not None:
        output_resolved = Path(output_path).expanduser().resolve()
        if _is_relative_to(output_resolved, dataset_root):
            skip_paths.append(output_resolved)

    raw_listing = build_listing(dataset_root, skip=skip_paths)
    metadata = extract_metadata(primary)
    template_file = _resolve_template(template_path)
    template = json.loads(template_file.read_text("utf-8"))
    return build_output(template, metadata, dataset_root, primary, raw_listing=raw_listing)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Populate the XRF template using metadata parsed from .cbf files."
    )
    parser.add_argument("path", help="Dataset directory or .cbf file")
    parser.add_argument(
        "--template",
        help="Optional template JSON path. Defaults to the first JSON in templates/XRF",
    )
    parser.add_argument("--output", help="Write the populated template to this path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the JSON output")
    return parser.parse_args(argv)


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    output_path = Path(args.output).expanduser().resolve() if args.output else None
    populated = generate_metadata(
        args.path,
        template_path=args.template,
        output_path=output_path,
    )
    json_kwargs = {"ensure_ascii": False}
    if args.pretty:
        json_kwargs["indent"] = 2
    payload = json.dumps(populated, **json_kwargs)
    if args.output:
        Path(args.output).expanduser().write_text(payload + ("\n" if args.pretty else ""), "utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
