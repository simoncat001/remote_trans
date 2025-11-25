#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract XRD metadata from data folders and populate the JSON template."""

from __future__ import annotations

import argparse
import configparser
import datetime as _dt
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Dict, Iterable, List, MutableMapping, Tuple

from cbf_utils import normalise_key, parse_numeric

HERE = Path(__file__).resolve().parent
TEMPLATE_DIR = HERE.parent / "templates" / "XRD"

METADATA_KEYWORDS = (
    "meta",
    "info",
    "config",
    "parameter",
    "header",
    "log",
    "note",
)
RAW_KEYWORDS = (
    "scan",
    "pattern",
    "profile",
    "intensity",
    "xrd",
    "diffraction",
    "data",
)
RAW_EXTENSIONS = {
    ".xy",
    ".xrdml",
    ".rd",
    ".raw",
    ".uxd",
    ".gda",
    ".dat",
    ".ras",
    ".gfrm",
}
GFRM_HEADER_LIMIT = 131072  # Read the first 128 KiB for textual header metadata
TEXT_EXTENSIONS = {".txt", ".csv"}

KEY_ALIASES: Dict[str, str] = {
    "experiment": "experiment_name",
    "experiment name": "experiment_name",
    "experiment title": "experiment_name",
    "measurement name": "experiment_name",
    "scan title": "experiment_name",
    "title": "experiment_name",
    "project": "experiment_name",
    "测量名称": "experiment_name",
    "实验名称": "experiment_name",
    "仪器名称": "instrument_name",
    "instrument": "instrument_name",
    "instrument name": "instrument_name",
    "设备名称": "instrument_name",
    "仪器型号": "instrument_model",
    "instrument model": "instrument_model",
    "model": "instrument_model",
    "仪器厂牌": "instrument_manufacturer",
    "厂牌": "instrument_manufacturer",
    "manufacturer": "instrument_manufacturer",
    "instrument manufacturer": "instrument_manufacturer",
    "仪器序列号": "instrument_serial",
    "serial": "instrument_serial",
    "serial number": "instrument_serial",
    "instrument serial": "instrument_serial",
    "instrument organisation": "instrument_organisation",
    "instrument organization": "instrument_organisation",
    "仪器所属单位": "instrument_organisation",
    "facility": "instrument_organisation",
    "facility name": "instrument_organisation",
    "laboratory": "instrument_organisation",
    "lab": "instrument_organisation",
    "instrument location": "instrument_location",
    "仪器所在地址": "instrument_location",
    "address": "instrument_location",
    "location": "instrument_location",
    "测试单位": "affiliation",
    "measurement organisation": "affiliation",
    "operator organisation": "affiliation",
    "operator organization": "affiliation",
    "organisation": "affiliation",
    "organization": "affiliation",
    "operator": "operator",
    "operator name": "operator",
    "user": "operator",
    "测量人员": "operator",
    "测试人员": "operator",
    "测试人员单位": "operator_affiliation",
    "operator affiliation": "operator_affiliation",
    "user affiliation": "operator_affiliation",
    "operator company": "operator_affiliation",
    "operator email": "operator_email",
    "email": "operator_email",
    "mail": "operator_email",
    "contact": "operator_email",
    "测试人员邮箱": "operator_email",
    "样品名称": "sample_name",
    "sample": "sample_name",
    "sample name": "sample_name",
    "specimen": "sample_name",
    "样品编号": "sample_id",
    "sample id": "sample_id",
    "specimen id": "sample_id",
    "样品描述": "sample_description",
    "sample description": "sample_description",
    "comment sample": "sample_description",
    "样品制备方法": "sample_preparation",
    "sample preparation": "sample_preparation",
    "sample prep": "sample_preparation",
    "mgid": "mgid",
    "mgid自定义部分": "mgid",
    "样品mgid": "sample_mgid",
    "关联样品mgid": "sample_mgid",
    "sample mgid": "sample_mgid",
    "timestamp": "timestamp",
    "date": "timestamp",
    "start time": "timestamp",
    "start timestamp": "timestamp",
    "collection date": "timestamp",
    "测量日期": "timestamp",
    "scan mode": "scan_mode",
    "measurement mode": "scan_mode",
    "扫描模式": "scan_mode",
    "scan type": "scan_mode",
    "scantype": "scan_mode",
    "start angle": "scan_start_angle",
    "scan start angle": "scan_start_angle",
    "2theta start": "scan_start_angle",
    "starting angle": "scan_start_angle",
    "起始角": "scan_start_angle",
    "起始2theta": "scan_start_angle",
    "end angle": "scan_end_angle",
    "scan end angle": "scan_end_angle",
    "2theta end": "scan_end_angle",
    "终止角": "scan_end_angle",
    "停止角": "scan_end_angle",
    "range": "scan_range",
    "scan range": "scan_range",
    "2theta range": "scan_range",
    "step": "scan_step",
    "step size": "scan_step",
    "stepsize": "scan_step",
    "step width": "scan_step",
    "步长": "scan_step",
    "data step": "scan_step",
    "scan speed": "scan_speed",
    "scan rate": "scan_speed",
    "扫描速度": "scan_speed",
    "exposure time": "exposure_time",
    "time per step": "exposure_time",
    "count time": "exposure_time",
    "dwell time": "exposure_time",
    "曝光时间": "exposure_time",
    "scan repetitions": "scan_repeats",
    "scan repeat": "scan_repeats",
    "扫描次数": "scan_repeats",
    "revolutions": "scan_repeats",
    "scans": "scan_repeats",
    "x ray source": "source_type",
    "x-ray source": "source_type",
    "x ray source type": "source_type",
    "source type": "source_type",
    "x ray target": "source_target",
    "靶材": "source_target",
    "target": "source_target",
    "source target": "source_target",
    "wavelength": "source_wavelength",
    "波长": "source_wavelength",
    "λ": "source_wavelength",
    "incident angle": "incident_angle",
    "入射角": "incident_angle",
    "tube voltage": "source_voltage",
    "accelerating voltage": "source_voltage",
    "voltage": "source_voltage",
    "管电压": "source_voltage",
    "generator voltage": "source_voltage",
    "gen voltage": "source_voltage",
    "gen volt": "source_voltage",
    "genvol": "source_voltage",
    "generator volt": "source_voltage",
    "generator kv": "source_voltage",
    "tube current": "source_current",
    "current": "source_current",
    "管电流": "source_current",
    "generator current": "source_current",
    "gen current": "source_current",
    "gencur": "source_current",
    "gen cur": "source_current",
    "detector": "detector_name",
    "detector name": "detector_name",
    "探测器名称": "detector_name",
    "detector model": "detector_model",
    "探测器型号": "detector_model",
    "detector type": "detector_type",
    "探测器类型": "detector_type",
    "detector distance": "detector_distance",
    "探测器距离": "detector_distance",
    "detector resolution": "detector_resolution",
    "探测器分辨率": "detector_resolution",
    "temperature": "environment_temperature",
    "环境温度": "environment_temperature",
    "ambient temperature": "environment_temperature",
    "humidity": "environment_humidity",
    "环境湿度": "environment_humidity",
    "atmosphere": "environment_atmosphere",
    "环境气氛": "environment_atmosphere",
    "notes": "notes",
    "note": "notes",
    "comment": "notes",
    "备注": "notes",
    "data file": "raw_primary",
    "primary file": "raw_primary",
    "主要数据文件": "raw_primary",
    "原始数据文件": "raw_primary",
}

FIELD_PATH_MAP: Dict[str, Tuple[str, ...]] = {
    "mgid": ("MGID自定义部分",),
    "experiment_name": ("实验名称",),
    "instrument_name": ("仪器名称",),
    "instrument_manufacturer": ("仪器厂牌",),
    "instrument_model": ("仪器型号",),
    "instrument_serial": ("仪器序列号",),
    "instrument_organisation": ("仪器所属单位",),
    "instrument_location": ("仪器所在地址",),
    "affiliation": ("测试单位",),
    "operator": ("测试人员",),
    "operator_affiliation": ("测试人员单位",),
    "operator_email": ("测试人员邮箱",),
    "sample_name": ("样品名称",),
    "sample_id": ("样品编号",),
    "sample_preparation": ("样品制备方法",),
    "sample_description": ("样品描述",),
    "timestamp": ("测试日期",),
    "source_type": ("X射线源", "X射线源类型"),
    "source_target": ("X射线源", "靶材"),
    "source_voltage": ("X射线源", "管电压"),
    "source_current": ("X射线源", "管电流"),
    "source_wavelength": ("X射线源", "波长"),
    "incident_angle": ("X射线源", "入射角"),
    "scan_mode": ("测量参数", "扫描模式"),
    "scan_start_angle": ("测量参数", "扫描起始角(°)"),
    "scan_end_angle": ("测量参数", "扫描终止角(°)"),
    "scan_step": ("测量参数", "步长(°)"),
    "scan_speed": ("测量参数", "扫描速度(°/min)"),
    "exposure_time": ("测量参数", "曝光时间(s)"),
    "scan_repeats": ("测量参数", "扫描次数"),
    "detector_name": ("探测器", "探测器名称"),
    "detector_model": ("探测器", "探测器型号"),
    "detector_type": ("探测器", "探测器类型"),
    "detector_distance": ("探测器", "探测器距离(mm)"),
    "detector_resolution": ("探测器", "探测器分辨率(°)"),
    "environment_temperature": ("环境条件", "温度(K)"),
    "environment_humidity": ("环境条件", "湿度(%)"),
    "environment_atmosphere": ("环境条件", "环境气氛"),
    "notes": ("备注",),
    "raw_primary": ("原始文件", "主要数据文件"),
    "raw_listing": ("原始文件", "原始数据列表"),
}

RANGE_RE = re.compile(
    r"(?P<start>[-+]?\d*\.?\d+)\s*(?:°|deg|degree|degrees)?\s*(?:-|to|–|—|~|至|→)\s*(?P<end>[-+]?\d*\.?\d+)",
    re.IGNORECASE,
)
DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y.%m.%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
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
            "No template JSON found under remote_trans/templates/XRD"
        )
    return candidates[0]


def _load_template(path: Path) -> MutableMapping[str, object]:
    return json.loads(path.read_text("utf-8"))


def _normalise_date(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    for fmt in DATE_FORMATS:
        try:
            parsed = _dt.datetime.strptime(value, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", value)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return value


def _discover_files(dataset: Path) -> Tuple[List[Path], List[Path]]:
    if dataset.is_file():
        meta = [dataset]
        raw = [dataset] if dataset.suffix.lower() in RAW_EXTENSIONS else []
        return meta, raw

    metadata_files: List[Path] = []
    raw_files: List[Path] = []
    for file in sorted(dataset.rglob("*")):
        if not file.is_file():
            continue
        suffix = file.suffix.lower()
        lower_name = file.name.lower()
        if suffix in {".json", ".ini"}:
            metadata_files.append(file)
            continue
        if suffix == ".gfrm":
            metadata_files.append(file)
            raw_files.append(file)
            continue
        if suffix in TEXT_EXTENSIONS:
            if any(keyword in lower_name for keyword in METADATA_KEYWORDS):
                metadata_files.append(file)
                continue
        if suffix in RAW_EXTENSIONS or any(keyword in lower_name for keyword in RAW_KEYWORDS):
            raw_files.append(file)
            continue
        if suffix in TEXT_EXTENSIONS and not metadata_files:
            # Fallback: keep as potential metadata file
            metadata_files.append(file)
    # Ensure unique and sorted
    metadata_files = sorted(dict.fromkeys(metadata_files))
    raw_files = sorted(dict.fromkeys(raw_files))
    return metadata_files, raw_files


def _flatten_json(payload: MutableMapping[str, object], prefix: Tuple[str, ...] = ()) -> Dict[str, str]:
    flattened: Dict[str, str] = {}
    for key, value in payload.items():
        new_prefix = prefix + (str(key),)
        if isinstance(value, MutableMapping):
            flattened.update(_flatten_json(value, new_prefix))
        else:
            joined = " ".join(new_prefix)
            flattened[joined] = str(value)
    return flattened


def _parse_text_pairs(text: str) -> Dict[str, str]:
    text = text or ""
    values: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "//", ";")):
            continue
        line = line.replace("：", ":").replace("＝", "=")
        if "," in line and line.count(",") == 1 and ":" not in line and "=" not in line:
            head, tail = [part.strip() for part in line.split(",", 1)]
            if head and tail:
                values.setdefault(head, tail)
                continue
        for sep in (":", "=", "\t"):
            if sep in line:
                key, val = line.split(sep, 1)
                key = key.strip()
                val = val.strip()
                if key:
                    values.setdefault(key, val)
                break
        else:
            parts = re.split(r"\s{2,}", line)
            if len(parts) == 2:
                key, val = parts
                if key.strip():
                    values.setdefault(key.strip(), val.strip())
    return values


def _parse_gfrm_metadata(path: Path) -> Dict[str, str]:
    with path.open("rb") as handle:
        header_bytes = handle.read(GFRM_HEADER_LIMIT)
    try:
        text = header_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = header_bytes.decode("latin-1", errors="ignore")
    cleaned_lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip().strip("\x00")
        if not line:
            continue
        upper = line.upper()
        if "END" in upper and "HEADER" in upper:
            break
        line = re.sub(r"[\x00-\x1F\x7F]+", " ", line)
        cleaned = line.strip()
        if cleaned:
            cleaned_lines.append(cleaned)
    return _parse_text_pairs("\n".join(cleaned_lines))


def _parse_metadata_file(path: Path) -> Dict[str, str]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text("utf-8"))
        if isinstance(data, MutableMapping):
            return _flatten_json(data)
        raise ValueError(f"Unsupported JSON structure in {path}")
    if suffix == ".ini":
        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")
        values: Dict[str, str] = {}
        for section in parser.sections():
            for key, value in parser.items(section):
                values[f"{section} {key}"] = value
        return values
    if suffix == ".gfrm":
        return _parse_gfrm_metadata(path)
    text = path.read_text("utf-8", errors="ignore")
    return _parse_text_pairs(text)


def _canonicalise_pairs(pairs: Dict[str, str]) -> Dict[str, str]:
    canonical: Dict[str, str] = {}
    for raw_key, raw_value in pairs.items():
        norm_key = normalise_key(raw_key)
        mapped = KEY_ALIASES.get(norm_key)
        if not mapped:
            continue
        canonical[mapped] = raw_value.strip()
    return canonical


def _parse_range(value: str) -> Tuple[float | None, float | None]:
    match = RANGE_RE.search(value)
    if not match:
        return None, None
    start = parse_numeric(match.group("start"))
    end = parse_numeric(match.group("end"))
    return start, end


def _convert_voltage(value: str) -> float | None:
    numeric = parse_numeric(value)
    if numeric is None:
        return None
    lower = value.lower()
    if "mv" in lower or "兆伏" in lower:
        return numeric * 1000.0
    if "kv" in lower or "千伏" in lower:
        return numeric
    if "v" in lower or "伏" in lower:
        return numeric / 1000.0
    return numeric


def _convert_current(value: str) -> float | None:
    numeric = parse_numeric(value)
    if numeric is None:
        return None
    lower = value.lower()
    if "ka" in lower or "千安" in lower:
        return numeric * 1000.0
    if "a" in lower and "ma" not in lower:
        return numeric * 1000.0
    if "µa" in lower or "μa" in lower or "ua" in lower or "微安" in lower:
        return numeric / 1000.0
    if "na" in lower or "纳安" in lower:
        return numeric / 1_000_000.0
    return numeric


def _convert_wavelength(value: str) -> float | None:
    numeric = parse_numeric(value)
    if numeric is None:
        return None
    lower = value.lower()
    if "nm" in lower or "纳米" in lower:
        return numeric * 10.0
    if "pm" in lower or "皮米" in lower:
        return numeric * 0.01
    return numeric


def _convert_speed(value: str) -> float | None:
    numeric = parse_numeric(value)
    if numeric is None:
        return None
    lower = value.lower()
    if "deg/s" in lower or "°/s" in lower or "度/秒" in lower:
        return numeric * 60.0
    if "rad/s" in lower:
        return numeric * 180.0 / 3.141592653589793 * 60.0
    if "rad/min" in lower:
        return numeric * 180.0 / 3.141592653589793
    return numeric


def _convert_time(value: str) -> float | None:
    numeric = parse_numeric(value)
    if numeric is None:
        return None
    lower = value.lower()
    if "ms" in lower or "毫秒" in lower:
        return numeric / 1000.0
    if "µs" in lower or "μs" in lower or "us" in lower or "微秒" in lower:
        return numeric / 1_000_000.0
    if "min" in lower or "分钟" in lower:
        return numeric * 60.0
    return numeric


def _convert_temperature(value: str) -> float | None:
    numeric = parse_numeric(value)
    if numeric is None:
        return None
    lower = value.lower()
    if "°c" in lower or "摄氏" in lower or " c" in lower:
        return numeric + 273.15
    if "k" in lower:
        return numeric
    if "°f" in lower or "华氏" in lower:
        return (numeric - 32.0) * 5.0 / 9.0 + 273.15
    return numeric


def _convert_humidity(value: str) -> float | None:
    numeric = parse_numeric(value)
    if numeric is None:
        return None
    lower = value.lower()
    if "%" in lower or "％" in lower:
        return numeric
    if numeric <= 1:
        return numeric * 100.0
    return numeric


def _format_file_uri(path: Path) -> str:
    return f"file:{path.resolve().as_posix()}"


def _merge_metadata(dataset: Path, metadata_files: Iterable[Path]) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    for meta in metadata_files:
        try:
            parsed = _parse_metadata_file(meta)
        except Exception:
            continue
        canonical = _canonicalise_pairs(parsed)
        merged.update(canonical)
    return merged


def _transform_values(values: Dict[str, str]) -> Dict[str, object]:
    transformed: Dict[str, object] = {}
    for key, value in values.items():
        if key == "timestamp":
            transformed[key] = _normalise_date(value)
        elif key == "scan_range":
            start, end = _parse_range(value)
            if start is not None:
                transformed.setdefault("scan_start_angle", start)
            if end is not None:
                transformed.setdefault("scan_end_angle", end)
        elif key == "source_voltage":
            converted = _convert_voltage(value)
            if converted is not None:
                transformed[key] = round(converted, 6)
        elif key == "source_current":
            converted = _convert_current(value)
            if converted is not None:
                transformed[key] = round(converted, 6)
        elif key == "source_wavelength":
            converted = _convert_wavelength(value)
            if converted is not None:
                transformed[key] = round(converted, 6)
        elif key == "scan_speed":
            converted = _convert_speed(value)
            if converted is not None:
                transformed[key] = round(converted, 6)
        elif key == "exposure_time":
            converted = _convert_time(value)
            if converted is not None:
                transformed[key] = round(converted, 6)
        elif key == "environment_temperature":
            converted = _convert_temperature(value)
            if converted is not None:
                transformed[key] = round(converted, 6)
        elif key == "environment_humidity":
            converted = _convert_humidity(value)
            if converted is not None:
                transformed[key] = round(converted, 6)
        elif key == "scan_step":
            numeric = parse_numeric(value)
            if numeric is not None:
                transformed[key] = round(numeric, 6)
        elif key in {"scan_start_angle", "scan_end_angle", "incident_angle", "detector_distance", "detector_resolution"}:
            numeric = parse_numeric(value)
            if numeric is not None:
                transformed[key] = round(numeric, 6)
        elif key == "scan_repeats":
            numeric = parse_numeric(value)
            if numeric is not None:
                transformed[key] = int(round(numeric))
        elif key == "sample_mgid":
            transformed[key] = [item.strip() for item in re.split(r"[,;\s]+", value) if item.strip()]
        elif key == "raw_primary":
            transformed[key] = value
        else:
            transformed[key] = value.strip()
    return transformed


def _apply_measurement_files(dataset: Path, values: Dict[str, object], raw_files: Iterable[Path]) -> None:
    file_list = sorted({file.resolve() for file in raw_files if file.is_file()})
    if not file_list:
        return
    uris = [_format_file_uri(path) for path in file_list]
    values.setdefault("raw_listing", uris)
    root = dataset if dataset.is_dir() else dataset.parent
    if "raw_primary" in values and values["raw_primary"]:
        raw_primary_value = Path(str(values["raw_primary"]))
        primary_path = raw_primary_value
        if not raw_primary_value.is_absolute():
            primary_path = (root / raw_primary_value).resolve()
        if primary_path.is_file():
            values["raw_primary"] = _format_file_uri(primary_path)
        else:
            values["raw_primary"] = _format_file_uri(file_list[0])
    else:
        values["raw_primary"] = _format_file_uri(file_list[0])
        values.setdefault("raw_listing", uris)


def _set_field(payload: MutableMapping[str, object], path: Tuple[str, ...], value: object) -> None:
    if value is None:
        return
    current: MutableMapping[str, object] = payload
    for key in path[:-1]:
        next_value = current.get(key)
        if not isinstance(next_value, MutableMapping):
            next_value = {}
            current[key] = next_value
        current = next_value
    last = path[-1]
    existing = current.get(last)
    if isinstance(existing, list):
        if isinstance(value, list):
            current[last] = value
        else:
            current[last] = [value]
    else:
        current[last] = value


def populate_template(
    dataset: Path,
    template: MutableMapping[str, object],
    values: Dict[str, object],
) -> MutableMapping[str, object]:
    populated = deepcopy(template)
    for key, value in values.items():
        if key == "sample_mgid":
            if value:
                _set_field(populated, ("关联样品MGID",), value)
            continue
        path = FIELD_PATH_MAP.get(key)
        if not path:
            continue
        if key == "raw_listing" and isinstance(value, list):
            _set_field(populated, path, value)
            continue
        if key == "raw_primary" and isinstance(value, str):
            _set_field(populated, path, value)
            continue
        _set_field(populated, path, value)
    return populated


def generate_metadata(
    input_path: Path,
    *,
    template_path: Path | None = None,
    output_path: Path | None = None,
) -> MutableMapping[str, object]:
    dataset = input_path.expanduser().resolve()
    template_file = _resolve_template(template_path)
    template = _load_template(template_file)
    metadata_files, raw_files = _discover_files(dataset)
    merged_pairs = _merge_metadata(dataset, metadata_files)
    values = _transform_values(merged_pairs)
    _apply_measurement_files(dataset, values, raw_files)
    populated = populate_template(dataset, template, values)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(populated, ensure_ascii=False, indent=2), "utf-8")
    return populated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Dataset directory or metadata file")
    parser.add_argument("--template", type=Path, help="Override the template JSON path")
    parser.add_argument("--output", type=Path, help="Write populated JSON to this path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print to stdout")
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    dataset = args.input
    output_path = args.output
    result = generate_metadata(dataset, template_path=args.template, output_path=output_path)
    if output_path is None:
        if args.pretty:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
