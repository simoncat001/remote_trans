#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified entry point for extracting instrument metadata templates."""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional


@dataclass(frozen=True)
class Extractor:
    """Description of a metadata extractor."""

    key: str
    description: str
    default_template: Callable[[], Path]
    runner: Callable[[Path, Optional[Path], Optional[Path]], Dict[str, object]]


def _load_module(name: str):
    """Import ``remote_trans.program.<name>`` (or the script next to us)."""

    package = __package__
    if package:
        return importlib.import_module(f".{name}", package)
    return importlib.import_module(name)


def _tem_default_template() -> Path:
    module = _load_module("tem_metadata")
    return Path(module.DEFAULT_TEMPLATE)


def _tem_runner(
    input_path: Path, template: Optional[Path], output_path: Optional[Path]
) -> Dict[str, object]:
    module = _load_module("tem_metadata")
    return module.generate_metadata(
        input_path,
        template_path=template,
        output_path=output_path,
    )


def _sem_default_template() -> Path:
    module = _load_module("sem_metadata")
    return Path(module.DEFAULT_TEMPLATE)


def _sem_runner(
    input_path: Path, template: Optional[Path], output_path: Optional[Path]
) -> Dict[str, object]:
    module = _load_module("sem_metadata")
    return module.generate_metadata(
        input_path,
        template_path=template,
        output_path=output_path,
    )


def _synch_default_template() -> Path:
    module = _load_module("synchrotron_metadata")
    return Path(module.DEFAULT_TEMPLATE)


def _synch_runner(
    input_path: Path, template: Optional[Path], output_path: Optional[Path]
) -> Dict[str, object]:
    module = _load_module("synchrotron_metadata")
    return module.generate_metadata(
        input_path,
        template_path=template,
        output_path=output_path,
    )


def _xrf_default_template() -> Path:
    module = _load_module("xrf_metadata")
    return module._resolve_template(None)  # type: ignore[attr-defined]


def _xrf_runner(
    input_path: Path, template: Optional[Path], output_path: Optional[Path]
) -> Dict[str, object]:
    module = _load_module("xrf_metadata")
    return module.generate_metadata(
        input_path,
        template_path=template,
        output_path=output_path,
    )


def _xrd_default_template() -> Path:
    module = _load_module("xrd_metadata")
    return module._resolve_template(None)  # type: ignore[attr-defined]


def _xrd_runner(
    input_path: Path, template: Optional[Path], output_path: Optional[Path]
) -> Dict[str, object]:
    module = _load_module("xrd_metadata")
    return module.generate_metadata(
        input_path,
        template_path=template,
        output_path=output_path,
    )


EXTRACTORS: Dict[str, Extractor] = {
    "tem": Extractor(
        key="tem",
        description="Transmission electron microscopy (.emi)",
        default_template=_tem_default_template,
        runner=_tem_runner,
    ),
    "sem": Extractor(
        key="sem",
        description="Scanning electron microscopy (.cbf)",
        default_template=_sem_default_template,
        runner=_sem_runner,
    ),
    "synchrotron": Extractor(
        key="synchrotron",
        description="Synchrotron radiation beamline drops",
        default_template=_synch_default_template,
        runner=_synch_runner,
    ),
    "xrf": Extractor(
        key="xrf",
        description="High-throughput XRF scans (.cbf)",
        default_template=_xrf_default_template,
        runner=_xrf_runner,
    ),
    "xrd": Extractor(
        key="xrd",
        description="High-throughput XRD scans (.xrdml/.xy/.gfrm)",
        default_template=_xrd_default_template,
        runner=_xrd_runner,
    ),
}


def _detect_type(target: Path) -> Optional[str]:
    """Best-effort dataset type detection."""

    if target.is_file():
        suffix = target.suffix.lower()
        if suffix == ".emi":
            return "tem"
        if suffix == ".cbf":
            return None
        if suffix in {".xrdml", ".xy", ".uxd", ".rd", ".raw", ".gfrm"}:
            return "xrd"
    else:
        emi = next(target.rglob("*.emi"), None)
        if emi is not None:
            return "tem"
        cbf = next(target.rglob("*.cbf"), None)
        if cbf is not None:
            return None
        for pattern in ("*.xrdml", "*.xy", "*.uxd", "*.rd", "*.raw", "*.gfrm"):
            xrd_file = next(target.rglob(pattern), None)
            if xrd_file is not None:
                return "xrd"
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?", help="Dataset directory or file")
    parser.add_argument(
        "--type",
        choices=sorted(EXTRACTORS),
        help="Explicitly select the metadata extractor",
    )
    parser.add_argument("--template", type=Path, help="Override the template JSON path")
    parser.add_argument("--output", type=Path, help="Write JSON output to this file")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the JSON output")
    parser.add_argument(
        "--list-types",
        action="store_true",
        help="Show the supported dataset types and exit",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_types:
        for key in sorted(EXTRACTORS):
            extractor = EXTRACTORS[key]
            print(f"{key:>12}  {extractor.description}")
        return 0

    if args.input is None:
        parser.error("the following arguments are required: input")

    dataset_path = args.input.expanduser().resolve()
    dataset_type = args.type
    if dataset_type is None:
        dataset_type = _detect_type(dataset_path)
        if dataset_type is None:
            parser.error(
                "Unable to detect dataset type automatically; please specify --type"
            )

    extractor = EXTRACTORS[dataset_type]
    if args.template:
        template_path = args.template.expanduser().resolve()
        if not template_path.is_file():
            parser.error(f"Template '{template_path}' does not exist")
    else:
        template_path = extractor.default_template()

    output_path = args.output.expanduser().resolve() if args.output else None
    populated = extractor.runner(dataset_path, template_path, output_path)

    json_kwargs = {"ensure_ascii": False}
    if args.pretty:
        json_kwargs["indent"] = 2
    payload = json.dumps(populated, **json_kwargs)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + ("\n" if args.pretty else ""), "utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
