#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract metadata for the TEM template from FEI ``.emi`` files.

The script reads the TEM template JSON shipped with the repository and tries
to populate the fields that can be inferred from the metadata stored in the
``.emi`` file that accompanies the raw data.  Whenever HyperSpy together with
the RosettaSciIO plugin is available we use that specialised decoder to read
the experimental description tables.  Otherwise we fall back to a small
built-in parser that pulls the same information directly from the ``.emi``
container so the CLI keeps working without optional dependencies.

Only a subset of the template fields can be filled from the information that is
present in the demo data set.  For fields where there is no direct mapping we
leave the default value from the template untouched.

Usage
-----

.. code-block:: bash

    python tem_metadata.py \
        remote_trans/data/TEM/"Format 1_ES vision&SER file" \
        --template ../templates/TEM/透射电子显微表征元数据规范-2025.json \
        --pretty

The script accepts either a directory (it will pick the first ``.emi`` file in
it) or the path to a concrete ``.emi`` file.  The populated template is printed
as JSON or saved with ``--output``.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

try:
    from .fei_emi import EmiFile
except ImportError:  # pragma: no cover - allows running as a script
    from fei_emi import EmiFile

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = HERE.parent / "templates" / "TEM" / "透射电子显微表征元数据规范-2025.json"

def _normalise_unit(unit: str) -> str:
    unit = unit.strip()
    if not unit:
        return unit
    replacements = {
        "um": "μm",
        "uA": "μA",
        "ua": "μA",
        "deg": "°",
    }
    return replacements.get(unit, unit)


def _format_value_with_unit(value: str, unit: str) -> str:
    value = value.strip()
    unit = _normalise_unit(unit)
    return f"{value} {unit}".strip() if value else ""


def _parse_float(value: str) -> Optional[float]:
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        value = value.replace(",", "")
        try:
            return float(value)
        except ValueError:
            return None


def _parse_acquire_date(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    known_formats = ["%a %b %d %H:%M:%S %Y", "%Y-%m-%d", "%Y/%m/%d", "%d %b %Y"]
    for fmt in known_formats:
        try:
            dt = _dt.datetime.strptime(value, fmt)
        except ValueError:
            continue
        else:
            return dt.strftime("%Y-%m-%d")
    # Try to extract an ISO date from the string
    match = re.search(r"(20\d{2})[-/](\d{2})[-/](\d{2})", value)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month}-{day}"
    return value


def _derive_scan_mode(mode: str) -> str:
    if not mode:
        return ""
    mode_upper = mode.upper()
    if "STEM" in mode_upper:
        return "STEM"
    if "TEM" in mode_upper:
        return "TEM"
    if "DIFF" in mode_upper:
        return "Diffraction"
    return mode.split()[0]


def parse_emi_metadata(emi_path: Path) -> Dict[str, object]:
    emi = EmiFile(emi_path)

    def label_entry(name: str) -> Tuple[str, str]:
        return emi.get_label(name)

    microscope_name, _ = label_entry("Microscope")
    user_name, _ = label_entry("User")
    mode_value, _ = label_entry("Mode")
    magnification_value, magnification_unit = label_entry("Magnification")
    camera_length_value, camera_length_unit = label_entry("Camera length")
    emission_value, emission_unit = label_entry("Emission")
    spot_size_value, _ = label_entry("Spot size")
    c2_value, c2_unit = label_entry("C2 Aperture")
    c1_value, c1_unit = label_entry("C1 Aperture")

    accelerating_voltage = _parse_float(emi.find_text("AcceleratingVoltage"))
    if accelerating_voltage is None:
        high_tension_value, high_tension_unit = label_entry("High tension")
        hv = _parse_float(high_tension_value)
        if hv is not None:
            if high_tension_unit.lower() == "kv":
                accelerating_voltage = hv * 1000.0
            else:
                accelerating_voltage = hv

    emission_current = _parse_float(emission_value)
    spot_size = _parse_float(spot_size_value)
    dwell_time = _parse_float(emi.find_text("DwellTimePath"))
    frame_time = _parse_float(emi.find_text("FrameTime"))
    magnification_str = _format_value_with_unit(magnification_value, magnification_unit)
    camera_length_str = _format_value_with_unit(camera_length_value, camera_length_unit)
    c2_aperture = _format_value_with_unit(c2_value, c2_unit)
    c1_aperture = _format_value_with_unit(c1_value, c1_unit)

    acquire_date = _parse_acquire_date(emi.find_text("AcquireDate"))
    manufacturer = emi.find_text("Manufacturer")

    metadata = {
        "microscope_name": microscope_name.strip(),
        "user": user_name.strip(),
        "mode": mode_value.strip(),
        "scan_mode": _derive_scan_mode(mode_value.strip()),
        "magnification": magnification_str,
        "camera_length": camera_length_str,
        "emission_current": emission_current,
        "emission_unit": _normalise_unit(emission_unit),
        "spot_size": spot_size,
        "accelerating_voltage": accelerating_voltage,
        "dwell_time": dwell_time,
        "frame_time": frame_time,
        "c2_aperture": c2_aperture,
        "c1_aperture": c1_aperture,
        "acquire_date": acquire_date,
        "manufacturer": manufacturer.strip(),
    }
    return metadata


def _update_if_value(target: Dict[str, object], key: str, value: object) -> None:
    if value not in (None, ""):
        target[key] = value


def populate_template(template: Dict[str, object], metadata: Dict[str, object], dataset_files: Iterable[Path]) -> Dict[str, object]:
    filled = deepcopy(template)

    _update_if_value(filled, "仪器名称", metadata.get("microscope_name", ""))
    _update_if_value(filled, "仪器厂牌", metadata.get("manufacturer", ""))
    _update_if_value(filled, "测试日期", metadata.get("acquire_date", ""))
    _update_if_value(filled, "测试人员", metadata.get("user", ""))

    beam = dict(filled.get("电子束", {}))
    if metadata.get("accelerating_voltage") is not None:
        beam["加速电压"] = metadata["accelerating_voltage"]
    if metadata.get("emission_current") is not None:
        beam["发射电流"] = metadata["emission_current"]
    if metadata.get("spot_size") is not None:
        beam["束斑尺寸"] = metadata["spot_size"]
    filled["电子束"] = beam

    optics = dict(filled.get("光路", {}))
    condenser = dict(optics.get("聚光镜", {}))
    if metadata.get("c2_aperture"):
        condenser["聚光镜光阑型号"] = metadata["c2_aperture"]
    if metadata.get("c1_aperture"):
        condenser.setdefault("备注", "")
        remark = condenser["备注"].strip()
        extra = f"C1 Aperture {metadata['c1_aperture']}".strip()
        condenser["备注"] = extra if not remark else f"{remark}; {extra}"
    optics["聚光镜"] = condenser

    objective = dict(optics.get("物镜", {}))
    if metadata.get("magnification"):
        objective["物镜放大倍率"] = metadata["magnification"]
    optics["物镜"] = objective
    filled["光路"] = optics

    measurement = dict(filled.get("测量记录系统", {}))
    _update_if_value(measurement, "测试模式", metadata.get("mode", ""))
    _update_if_value(measurement, "扫描模式", metadata.get("scan_mode", ""))
    if metadata.get("dwell_time") is not None:
        measurement["扫描单点时长"] = metadata["dwell_time"]
    if metadata.get("camera_length"):
        measurement["相机常数"] = metadata["camera_length"]
    if metadata.get("frame_time") is not None and measurement.get("测试模式"):
        measurement.setdefault("备注", "")
        remark = measurement["备注"].strip()
        frame_txt = f"FrameTime={metadata['frame_time']} s"
        measurement["备注"] = frame_txt if not remark else f"{remark}; {frame_txt}"
    filled["测量记录系统"] = measurement

    paths = sorted(Path(p) for p in dataset_files)
    original_files = dict(filled.get("原始文件", {}))
    if paths:
        primary = next((p.name for p in paths if p.suffix.lower() == ".emi"), paths[0].name)
        original_files["表征原始数据文件"] = primary
        original_files["表征原始数据列表"] = "\n".join(p.name for p in paths)
    filled["原始文件"] = original_files

    return filled


def detect_emi_file(input_path: Path) -> Tuple[Path, Iterable[Path]]:
    if input_path.is_file():
        if input_path.suffix.lower() != ".emi":
            raise ValueError(f"Unsupported file type: {input_path}")
        dataset_dir = input_path.parent
        dataset_files = [p for p in dataset_dir.iterdir() if p.is_file()]
        return input_path, dataset_files

    if input_path.is_dir():
        emi_files = sorted(input_path.glob("*.emi"))
        if not emi_files:
            raise FileNotFoundError(f"No .emi file found in {input_path}")
        dataset_files = [p for p in input_path.iterdir() if p.is_file()]
        return emi_files[0], dataset_files

    raise FileNotFoundError(f"{input_path} does not exist")


def generate_metadata(
    input_path: Path | str,
    *,
    template_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> Dict[str, object]:
    """Return a populated TEM template for ``input_path``."""

    target = Path(input_path).expanduser().resolve()
    emi_file, dataset_files = detect_emi_file(target)
    dataset_file_list = [Path(p) for p in dataset_files]

    if output_path is not None:
        output_resolved = Path(output_path).expanduser().resolve()
        dataset_file_list = [
            p for p in dataset_file_list if p.resolve() != output_resolved
        ]

    template_file = (
        Path(template_path).expanduser().resolve()
        if template_path is not None
        else DEFAULT_TEMPLATE
    )
    with template_file.open("r", encoding="utf-8") as fh:
        template_data = json.load(fh)

    metadata = parse_emi_metadata(emi_file)
    populated = populate_template(template_data, metadata, dataset_file_list)

    # ``populate_template`` already clones the template, so we simply return
    # the filled mapping.
    return populated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        help="Directory that contains the TEM data or the path to a .emi file",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help="Path to the TEM metadata template (JSON)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the populated template to this file instead of stdout",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON with indentation",
    )
    args = parser.parse_args()

    filled = generate_metadata(
        args.input,
        template_path=args.template,
        output_path=args.output,
    )
    json_text = json.dumps(filled, ensure_ascii=False, indent=2 if args.pretty else None)

    if args.output:
        args.output.write_text(json_text + ("\n" if args.pretty else ""), encoding="utf-8")
    else:
        print(json_text)


if __name__ == "__main__":
    main()
