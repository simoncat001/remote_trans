#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for parsing CBF (CIF binary format) headers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

CBF_MARKER = "--CIF-BINARY-FORMAT-SECTION--"
COMMENT_PREFIX = "#"


def read_cbf_text_header(path: Path, *, chunk_size: int = 65_536) -> str:
    """Return the plain-text header that precedes the binary CBF payload."""

    marker = CBF_MARKER.encode("latin-1")
    buffer = bytearray()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            buffer.extend(chunk)
            if marker in buffer or b"\f" in chunk:
                break
    text = buffer.decode("latin-1", errors="ignore")
    for sentinel in (CBF_MARKER, "\f", "\x1a"):
        if sentinel in text:
            text = text.split(sentinel, 1)[0]
    return text


def _strip_cif_value(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    if value.startswith(";"):
        return value.lstrip(";").strip()
    if value.startswith("'") or value.startswith('"'):
        quote = value[0]
        if value.endswith(quote) and len(value) > 1:
            value = value[1:-1]
        else:
            value = value[1:]
    if "#" in value:
        value = value.split("#", 1)[0].strip()
    return value.strip()


def _split_cbf_comment(comment: str) -> Tuple[str | None, str | None]:
    comment = comment.strip()
    if not comment:
        return None, None
    for separator in (":", "=", "\t"):
        if separator not in comment:
            continue
        if separator == ":" and ": " not in comment and " :" not in comment:
            continue
        key, value = comment.split(separator, 1)
        return key.strip(), value.strip()
    parts = re.split(r"\s{2,}", comment, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    tokens = comment.split(None, 1)
    if len(tokens) == 2:
        return tokens[0].strip(), tokens[1].strip()
    return comment.strip(), ""


def parse_cbf_header(path: Path) -> Dict[str, str]:
    """Parse the textual portion of a ``.cbf`` file into a key/value map."""

    header = read_cbf_text_header(path)
    values: Dict[str, str] = {}
    current_key: str | None = None
    buffer: List[str] = []
    collecting = False
    for raw_line in header.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if raw_line.startswith(COMMENT_PREFIX):
            comment_key, comment_value = _split_cbf_comment(raw_line.lstrip(COMMENT_PREFIX))
            if comment_key:
                cleaned = _strip_cif_value(comment_value)
                if cleaned:
                    values.setdefault(comment_key.strip(), cleaned)
            continue
        if line.lower().startswith("loop_"):
            if collecting and current_key:
                text_value = "\n".join(buffer).strip()
                if text_value and text_value not in {"?", "."}:
                    values.setdefault(current_key, text_value)
            current_key = None
            buffer = []
            collecting = False
            continue
        if line.startswith("data_"):
            continue
        if line.startswith("_"):
            if collecting and current_key:
                text_value = "\n".join(buffer).strip()
                if text_value and text_value not in {"?", "."}:
                    values.setdefault(current_key, text_value)
            parts = line.split(None, 1)
            current_key = parts[0]
            buffer = []
            if len(parts) == 1:
                collecting = True
                continue
            value_part = _strip_cif_value(parts[1])
            collecting = False
            if value_part and value_part not in {"?", "."}:
                values.setdefault(current_key, value_part)
            current_key = None
            continue
        if collecting and current_key:
            if line == ";":
                text_value = "\n".join(buffer).strip()
                if text_value and text_value not in {"?", "."}:
                    values.setdefault(current_key, text_value)
                current_key = None
                buffer = []
                collecting = False
            else:
                buffer.append(raw_line.rstrip())
    if collecting and current_key:
        text_value = "\n".join(buffer).strip()
        if text_value and text_value not in {"?", "."}:
            values.setdefault(current_key, text_value)
    return values


def normalise_key(key: str) -> str:
    key = key.strip().lower()
    key = key.replace("_", " ")
    key = re.sub(r"\s+", " ", key)
    return key.strip()


_NUMERIC_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def parse_numeric(value: str) -> float | None:
    match = _NUMERIC_RE.search(value)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


__all__ = [
    "parse_cbf_header",
    "read_cbf_text_header",
    "normalise_key",
    "parse_numeric",
]
