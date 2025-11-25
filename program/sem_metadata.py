#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract scanning electron microscope metadata from ``.cbf`` files."""

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
DEFAULT_TEMPLATE = (
    HERE.parent
    / "templates"
    / "SEM"
    / "高通量扫描电子显微表征元数据规范 -2025 (1).json"
)


def _convert_voltage(value: str) -> float | None:
    numeric = parse_numeric(value)
    if numeric is None:
        return None
    upper = value.upper()
    if "KV" in upper or "千伏" in value:
        numeric *= 1_000.0
    return numeric


def _convert_current(value: str) -> float | None:
    numeric = parse_numeric(value)
    if numeric is None:
        return None
    upper = value.upper()
    if "KA" in upper:
        numeric *= 1_000.0
    elif "MA" in upper or "毫安" in value:
        numeric *= 1e-3
    elif "UA" in upper or "ΜA" in upper or "微安" in value:
        numeric *= 1e-6
    elif "NA" in upper or "纳安" in value:
        numeric *= 1e-9
    elif "PA" in upper or "皮安" in value:
        numeric *= 1e-12
    return numeric


def _convert_time_seconds(value: str) -> float | None:
    numeric = parse_numeric(value)
    if numeric is None:
        return None
    upper = value.upper()
    if any(unit in upper for unit in ("MS", "毫秒")):
        numeric /= 1_000.0
    elif any(unit in upper for unit in ("US", "ΜS", "微秒")):
        numeric /= 1_000_000.0
    elif any(unit in upper for unit in ("NS", "纳秒")):
        numeric /= 1_000_000_000.0
    return numeric


def _convert_temperature(value: str) -> float | None:
    numeric = parse_numeric(value)
    if numeric is None:
        return None
    upper = value.upper()
    if "℃" in value or "摄氏" in value or "°C" in upper:
        return round(numeric, 2)
    if "K" in upper:
        return round(numeric - 273.15, 2)
    return numeric


def _parse_date(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    known_formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%d %b %Y",
        "%b %d %Y",
    ]
    for fmt in known_formats:
        try:
            dt = _dt.datetime.strptime(value, fmt)
        except ValueError:
            continue
        return dt.strftime("%Y-%m-%d")
    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", value)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return value


ALIAS_MAP: Dict[str, Tuple[str, str]] = {
    "experiment name": ("top", "实验名称"),
    "experiment title": ("top", "实验名称"),
    "measurement id": ("top", "实验名称"),
    "project": ("top", "实验名称"),
    "dataset": ("top", "实验名称"),
    "sample name": ("top", "样品名称"),
    "sample": ("top", "样品名称"),
    "样品": ("top", "样品名称"),
    "样品名称": ("top", "样品名称"),
    "operator": ("top", "测试人员"),
    "user": ("top", "测试人员"),
    "测量人员": ("top", "测试人员"),
    "测试人员": ("top", "测试人员"),
    "affiliation": ("top", "测试单位"),
    "institution": ("top", "测试单位"),
    "测试单位": ("top", "测试单位"),
    "电子邮箱": ("top", "测试人员邮箱"),
    "email": ("top", "测试人员邮箱"),
    "contact": ("top", "测试人员"),
    "timestamp": ("top", "测试日期"),
    "date": ("top", "测试日期"),
    "acquisition date": ("top", "测试日期"),
    "collection date": ("top", "测试日期"),
    "测量日期": ("top", "测试日期"),
    "mgid": ("top", "MGID自定义部分"),
    "mgid 自定部分": ("top", "MGID自定义部分"),
    "mgid自定义部分": ("top", "MGID自定义部分"),
    "instrument": ("instrument", "仪器名称"),
    "instrument name": ("instrument", "仪器名称"),
    "microscope": ("instrument", "仪器名称"),
    "sem": ("instrument", "仪器名称"),
    "instrument model": ("instrument", "仪器型号"),
    "model": ("instrument", "仪器型号"),
    "microscope model": ("instrument", "仪器型号"),
    "serial": ("instrument", "仪器序列号"),
    "serial number": ("instrument", "仪器序列号"),
    "仪器序列号": ("instrument", "仪器序列号"),
    "manufacturer": ("instrument", "仪器厂牌"),
    "vendor": ("instrument", "仪器厂牌"),
    "maker": ("instrument", "仪器厂牌"),
    "仪器厂商": ("instrument", "仪器厂牌"),
    "lab": ("instrument", "仪器所属单位"),
    "laboratory": ("instrument", "仪器所属单位"),
    "所属单位": ("instrument", "仪器所属单位"),
    "address": ("instrument", "仪器所在地址"),
    "location": ("instrument", "仪器所在地址"),
    "instrument location": ("instrument", "仪器所在地址"),
    "accelerating voltage": ("beam", "加速电压"),
    "acceleration voltage": ("beam", "加速电压"),
    "beam energy": ("beam", "加速电压"),
    "高压": ("beam", "加速电压"),
    "加速电压": ("beam", "加速电压"),
    "emission current": ("beam", "发射电流"),
    "beam current": ("beam", "发射电流"),
    "probe current": ("beam", "发射电流"),
    "发射电流": ("beam", "发射电流"),
    "束斑尺寸": ("beam", "束斑尺寸"),
    "spot size": ("beam", "束斑尺寸"),
    "beam convergence": ("beam", "发射角"),
    "convergence angle": ("beam", "发射角"),
    "发射角": ("beam", "发射角"),
    "scan mode": ("measurement", "扫描模式"),
    "扫描模式": ("measurement", "扫描模式"),
    "scan type": ("measurement", "扫描模式"),
    "test mode": ("measurement", "测试模式"),
    "模式": ("measurement", "测试模式"),
    "dwell time": ("measurement", "扫描单点时长"),
    "像素驻留时间": ("measurement", "扫描单点时长"),
    "pixel time": ("measurement", "扫描单点时长"),
    "exposure time": ("measurement", "扫描单点时长"),
    "temperature": ("environment", "温度"),
    "stage temperature": ("environment", "温度"),
    "环境温度": ("environment", "温度"),
    "humidity": ("environment", "湿度"),
    "环境湿度": ("environment", "湿度"),
    "vacuum": ("environment", "镜筒真空度"),
    "pressure": ("environment", "镜筒真空度"),
    "chamber pressure": ("environment", "镜筒真空度"),
}


def _merge_value(
    metadata: MutableMapping[str, Dict[str, object]],
    section: str,
    field: str,
    raw_value: str,
) -> None:
    section_dict = metadata.setdefault(section, {})
    if field in section_dict:
        return
    value: object = raw_value.strip()
    if section == "top" and field == "测试日期":
        value = _parse_date(raw_value)
    elif section == "beam" and field == "加速电压":
        converted = _convert_voltage(raw_value)
        if converted is not None:
            value = converted
    elif section == "beam" and field == "发射电流":
        converted = _convert_current(raw_value)
        if converted is not None:
            value = converted
    elif section == "beam" and field in {"束斑尺寸", "发射角"}:
        numeric = parse_numeric(raw_value)
        if numeric is not None:
            value = numeric
    elif section == "measurement" and field == "扫描单点时长":
        converted = _convert_time_seconds(raw_value)
        if converted is not None:
            value = converted
    elif section == "environment" and field == "温度":
        converted = _convert_temperature(raw_value)
        if converted is not None:
            value = converted
    elif section == "environment" and field == "湿度":
        numeric = parse_numeric(raw_value)
        if numeric is not None:
            value = numeric
    metadata[section][field] = value
    if section == "top" and field == "测试单位":
        top_section = metadata.setdefault("top", {})
        if not str(top_section.get("测试人员单位", "")).strip():
            top_section["测试人员单位"] = value


def parse_sem_metadata(cbf_paths: Iterable[Path]) -> Dict[str, Dict[str, object]]:
    collected_keys: Dict[str, str] = {}
    for cbf_path in cbf_paths:
        header = parse_cbf_header(cbf_path)
        for raw_key, raw_value in header.items():
            normalised = normalise_key(raw_key)
            if normalised not in collected_keys:
                collected_keys[normalised] = raw_value
    metadata: Dict[str, Dict[str, object]] = {}
    for raw_key, raw_value in collected_keys.items():
        alias = ALIAS_MAP.get(raw_key)
        if not alias:
            continue
        section, field = alias
        _merge_value(metadata, section, field, raw_value)
    return metadata


def populate_template(
    template: Dict[str, object],
    metadata: Dict[str, Dict[str, object]],
    dataset_dir: Path,
    dataset_files: Iterable[Path],
    primary_file: Path,
) -> Dict[str, object]:
    filled = deepcopy(template)

    top_values = metadata.get("top", {})
    for key, value in top_values.items():
        if value not in (None, ""):
            filled[key] = value

    instrument_values = metadata.get("instrument", {})
    instrument_fields = {
        "仪器名称",
        "仪器厂牌",
        "仪器序列号",
        "仪器所属单位",
        "仪器所在地址",
        "仪器型号",
    }
    for field in instrument_fields:
        if field in instrument_values and instrument_values[field] not in (None, ""):
            filled[field] = instrument_values[field]

    beam_section = dict(filled.get("电子束", {}))
    for field in ("加速电压", "发射电流", "束斑尺寸", "发射角"):
        value = metadata.get("beam", {}).get(field)
        if value not in (None, ""):
            beam_section[field] = value
    filled["电子束"] = beam_section

    measurement_section = dict(filled.get("测量记录系统", {}))
    for field in ("测试模式", "扫描模式", "扫描单点时长"):
        value = metadata.get("measurement", {}).get(field)
        if value not in (None, ""):
            measurement_section[field] = value
    filled["测量记录系统"] = measurement_section

    environment_section = dict(filled.get("环境条件", {}))
    for field in ("温度", "湿度", "镜筒真空度"):
        value = metadata.get("environment", {}).get(field)
        if value not in (None, ""):
            environment_section[field] = value
    filled["环境条件"] = environment_section

    dataset_dir = dataset_dir.resolve()
    files = sorted(Path(p).resolve() for p in dataset_files)
    rel_primary = primary_file.resolve().relative_to(dataset_dir)
    original_files = dict(filled.get("原始文件", {}))
    original_files["表征原始数据文件"] = str(rel_primary)
    rel_listing = [
        str(path.relative_to(dataset_dir))
        for path in files
        if path.is_file() and path != primary_file.resolve()
    ]
    seen = set()
    listing_lines: List[str] = []
    for entry in [str(rel_primary)] + rel_listing:
        if entry in seen:
            continue
        seen.add(entry)
        listing_lines.append(entry)
    original_files["表征原始数据列表"] = "\n".join(listing_lines)
    filled["原始文件"] = original_files

    if "实验名称" not in filled or not str(filled.get("实验名称", "")).strip():
        filled["实验名称"] = dataset_dir.name
    if "样品名称" not in filled or not str(filled.get("样品名称", "")).strip():
        filled["样品名称"] = dataset_dir.name

    return filled


def detect_cbf_files(input_path: Path) -> Tuple[Path, List[Path]]:
    if input_path.is_file():
        if input_path.suffix.lower() != ".cbf":
            raise ValueError(f"Unsupported file type: {input_path}")
        dataset_dir = input_path.parent
        dataset_files = [p for p in dataset_dir.glob("**/*") if p.is_file()]
        return input_path, dataset_files
    if input_path.is_dir():
        cbf_files = sorted(input_path.glob("**/*.cbf"))
        if not cbf_files:
            raise FileNotFoundError(f"No .cbf file found in {input_path}")
        dataset_files = [p for p in input_path.glob("**/*") if p.is_file()]
        return cbf_files[0], dataset_files
    raise FileNotFoundError(f"{input_path} does not exist")


def generate_metadata(
    input_path: Path | str,
    *,
    template_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> Dict[str, object]:
    """Return a populated SEM template for ``input_path``."""

    target = Path(input_path).expanduser().resolve()
    primary_file, dataset_files = detect_cbf_files(target)
    dataset_list = [Path(p) for p in dataset_files]

    if output_path is not None:
        output_resolved = Path(output_path).expanduser().resolve()
        dataset_list = [p for p in dataset_list if p.resolve() != output_resolved]

    cbf_candidates = {primary_file.resolve()}
    for item in dataset_list:
        if item.suffix.lower() == ".cbf":
            cbf_candidates.add(item.resolve())

    metadata = parse_sem_metadata(sorted(cbf_candidates))
    template_file = (
        Path(template_path).expanduser().resolve()
        if template_path is not None
        else DEFAULT_TEMPLATE
    )
    template = load_template(template_file)
    return populate_template(template, metadata, primary_file.parent, dataset_list, primary_file)


def load_template(path: Path) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to a dataset directory or a .cbf file")
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help="Path to the SEM template JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional file path to save the populated template",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the generated JSON",
    )
    args = parser.parse_args()

    populated = generate_metadata(
        args.input,
        template_path=args.template,
        output_path=args.output,
    )

    json_kwargs = {"ensure_ascii": False}
    if args.pretty:
        json_kwargs["indent"] = 2
    payload = json.dumps(populated, **json_kwargs)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + ("\n" if args.pretty else ""), "utf-8")
    else:
        print(payload)


if __name__ == "__main__":  # pragma: no cover
    main()
