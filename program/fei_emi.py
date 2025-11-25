from __future__ import annotations

"""FEI ``.emi`` reader with optional HyperSpy + RosettaSciIO support.

This module keeps the small helper API that :mod:`tem_metadata` relies on but
prefers to use the dedicated ``.emi`` decoder provided by HyperSpy together
with the RosettaSciIO plugin whenever those optional dependencies are
available.  The specialised stack already understands FEI's experimental
description tables, leading to more robust metadata extraction.  When the
libraries are missing the code gracefully falls back to the previous
latin-1/regex parser so the command line utility keeps working in minimal
environments.

.. _HyperSpy: https://hyperspy.org/
.. _RosettaSciIO: https://hyperspy.org/rosettasciio
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional, Tuple
import re
import xml.etree.ElementTree as ET

try:  # pragma: no cover - optional dependency
    import hyperspy.api as _hs_api  # type: ignore
except Exception:  # pragma: no cover - HyperSpy is optional
    _hs_api = None

try:  # pragma: no cover - ensure plugin registration when available
    import rosettasciio  # type: ignore  # noqa: F401
except Exception:  # pragma: no cover
    rosettasciio = None  # type: ignore


@dataclass(frozen=True)
class EmiLabel:
    """Represents a ``<Data>`` entry in the experimental description."""

    label: str
    value: str
    unit: str = ""


class EmiParseError(RuntimeError):
    """Raised when the ``.emi`` file cannot be interpreted."""


class EmiFile:
    """Minimal reader for FEI ``.emi`` metadata containers."""

    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        backend: Optional[_BaseBackend] = None
        if _hs_api is not None:  # pragma: no branch - simple optional path
            try:
                backend = _HyperSpyBackend(self.path)
            except Exception:
                backend = None
        if backend is None:
            backend = _TextBackend(self.path)
        self._backend = backend

    @property
    def text(self) -> str:
        return self._backend.text

    def _extract_block(self, tag: str) -> Optional[str]:
        return _extract_block(self.text, tag)

    def _experimental_description_element(self) -> Optional[ET.Element]:
        return _experimental_description_element(self.text, self.path)

    def labels(self) -> Iterable[EmiLabel]:
        return self._backend.labels()

    def get_label(self, name: str) -> Tuple[str, str]:
        return self._backend.get_label(name)

    def find_text(self, tag: str) -> str:
        return self._backend.find_text(tag)

    def raw_text(self) -> str:
        return self._backend.text


class _BaseBackend:
    """Shared interface implemented by both parsing strategies."""

    def __init__(self, path: Path):
        self.path = path

    @property
    def text(self) -> str:
        raise NotImplementedError

    def labels(self) -> Iterable[EmiLabel]:
        raise NotImplementedError

    def get_label(self, name: str) -> Tuple[str, str]:
        for entry in self.labels():
            if entry.label == name:
                return entry.value, entry.unit
        return "", ""

    def find_text(self, tag: str) -> str:
        raise NotImplementedError


class _TextBackend(_BaseBackend):
    """Original latin-1/regex based parser kept as a fallback."""

    def __init__(self, path: Path):
        super().__init__(path)
        self._data = self.path.read_bytes()
        self._text_cache: Optional[str] = None
        self._label_map: Optional[Dict[str, EmiLabel]] = None

    @property
    def text(self) -> str:
        if self._text_cache is None:
            self._text_cache = self._data.decode("latin-1", errors="ignore")
        return self._text_cache

    def labels(self) -> Iterable[EmiLabel]:
        if self._label_map is None:
            label_map: Dict[str, EmiLabel] = {}
            element = _experimental_description_element(self.text, self.path)
            if element is not None:
                for data_el in element.findall(".//Data"):
                    label = (data_el.findtext("Label") or "").strip()
                    value = (data_el.findtext("Value") or "").strip()
                    unit = (data_el.findtext("Unit") or "").strip()
                    if label and label not in label_map:
                        label_map[label] = EmiLabel(label=label, value=value, unit=unit)
            self._label_map = label_map
        return self._label_map.values()

    def find_text(self, tag: str) -> str:
        block = _extract_block(self.text, tag)
        if not block:
            return ""
        try:
            element = ET.fromstring(block)
        except ET.ParseError:
            return ""
        text = element.text or ""
        return text.strip()


class _HyperSpyBackend(_BaseBackend):  # pragma: no cover - requires optional deps
    """Wrapper that extracts label/value pairs via HyperSpy + RosettaSciIO."""

    def __init__(self, path: Path):
        if _hs_api is None:  # Defensive check, should never hit.
            raise RuntimeError("HyperSpy is not available")
        super().__init__(path)
        dataset = _hs_api.load(str(path), lazy=True, stack=False)
        if isinstance(dataset, list):
            if not dataset:
                raise EmiParseError(f"HyperSpy did not return any signals for {path}")
            dataset = dataset[0]
        self._signal = dataset
        self._original_metadata = dataset.original_metadata.as_dictionary()
        self._text_backend = _TextBackend(path)
        self._labels_cache: Optional[Tuple[EmiLabel, ...]] = None

    @property
    def text(self) -> str:
        return self._text_backend.text

    def labels(self) -> Iterable[EmiLabel]:
        if self._labels_cache is None:
            labels = list(_labels_from_metadata_dict(self._original_metadata))
            if not labels:
                labels = list(self._text_backend.labels())
            self._labels_cache = tuple(labels)
        return self._labels_cache

    def find_text(self, tag: str) -> str:
        value = _deep_find(self._original_metadata, tag)
        if value:
            return value
        return self._text_backend.find_text(tag)


def _labels_from_metadata_dict(metadata: Dict[str, object]) -> Iterator[EmiLabel]:
    """Yield :class:`EmiLabel` entries from HyperSpy metadata dictionaries."""

    exp_desc = metadata.get("ExperimentalDescription")
    if isinstance(exp_desc, dict):
        data_rows = exp_desc.get("Data") or exp_desc.get("data") or []
        if isinstance(data_rows, dict):  # Some versions use keyed dicts
            data_rows = data_rows.values()
        if isinstance(data_rows, Iterable):
            for row in data_rows:
                if not isinstance(row, dict):
                    continue
                label = str(row.get("Label", "")).strip()
                if not label:
                    continue
                value = str(row.get("Value", "")).strip()
                unit = str(row.get("Unit", "")).strip()
                yield EmiLabel(label=label, value=value, unit=unit)
    elif isinstance(exp_desc, str):
        yield from _labels_from_xml(exp_desc)


def _labels_from_xml(xml_text: str) -> Iterator[EmiLabel]:
    try:
        element = ET.fromstring(xml_text)
    except ET.ParseError:
        return iter(())
    labels: Dict[str, EmiLabel] = {}
    for data_el in element.findall(".//Data"):
        label = (data_el.findtext("Label") or "").strip()
        value = (data_el.findtext("Value") or "").strip()
        unit = (data_el.findtext("Unit") or "").strip()
        if label and label not in labels:
            labels[label] = EmiLabel(label=label, value=value, unit=unit)
    return iter(labels.values())


def _deep_find(node: object, key: str) -> str:
    """Recursively search nested dictionaries/lists for ``key``."""

    key_lower = key.lower()
    if isinstance(node, dict):
        for current_key, value in node.items():
            if isinstance(current_key, str) and current_key.lower() == key_lower:
                return _stringify(value)
            result = _deep_find(value, key)
            if result:
                return result
    elif isinstance(node, (list, tuple)):
        for item in node:
            result = _deep_find(item, key)
            if result:
                return result
    return ""


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, dict):
        for candidate in ("Value", "value", "Data", "data", "Text", "text"):
            if candidate in value:
                result = _stringify(value[candidate])
                if result:
                    return result
        return ""
    if isinstance(value, (list, tuple)):
        for item in value:
            result = _stringify(item)
            if result:
                return result
        return ""
    return str(value)


def _extract_block(text: str, tag: str) -> Optional[str]:
    pattern = re.compile(rf"<{tag}>(.*?)</{tag}>", re.IGNORECASE | re.DOTALL)
    match = pattern.search(text)
    if not match:
        return None
    content = match.group(1)
    return f"<{tag}>{content}</{tag}>"


def _experimental_description_element(text: str, path: Path) -> Optional[ET.Element]:
    block = _extract_block(text, "ExperimentalDescription")
    if not block:
        return None
    try:
        return ET.fromstring(block)
    except ET.ParseError as exc:
        raise EmiParseError(f"Failed to parse ExperimentalDescription in {path}") from exc

