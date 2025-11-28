#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end SEM .bcf 元数据提取：拆分 → 精简 → 合并 → JSON."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from parse_bcf_metadata import BCFParser

CHUNK_COPY_BYTES = 1024 * 1024  # 1 MB
MIN_TEXT_LENGTH = 10


def _default_split_dir(input_path: Path) -> Path:
    return input_path.parent / f"{input_path.stem}_split_parts"


def _default_processed_dir(input_path: Path) -> Path:
    return input_path.parent / f"{input_path.stem}_processed_parts"


def _default_metadata_bcf_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_metadata_only{input_path.suffix}")


def _default_json_path(input_path: Path) -> Path:
    return input_path.with_name("metadata.json")


def _split_file(
    input_path: Path,
    split_dir: Path,
    *,
    parts: int,
) -> List[Path]:
    file_size = input_path.stat().st_size
    print(f"📦 正在拆分原始BCF文件：{file_size / (1024*1024):.2f} MB → {parts} 份")

    part_size = math.ceil(file_size / parts)
    chunk_paths: List[Path] = []
    stem = input_path.stem
    suffix = input_path.suffix

    with input_path.open("rb") as infile:
        part_idx = 0
        while True:
            remaining = file_size - infile.tell()
            if remaining <= 0:
                break

            current_size = min(part_size, remaining)
            part_idx += 1
            chunk_name = f"{stem}_part{part_idx:03d}{suffix}"
            chunk_path = split_dir / chunk_name
            chunk_paths.append(chunk_path)

            print(
                f"  ➤ 生成块 {part_idx} ，目标大小 {current_size / (1024*1024):.2f} MB"
            )

            with chunk_path.open("wb") as outfile:
                copied = 0
                while copied < current_size:
                    chunk = infile.read(min(CHUNK_COPY_BYTES, current_size - copied))
                    if not chunk:
                        break
                    outfile.write(chunk)
                    copied += len(chunk)

    print(f"✅ 完成拆分，共生成 {len(chunk_paths)} 个块")
    return chunk_paths


def _ensure_split_parts(
    input_path: Path,
    split_dir: Path,
    *,
    parts: int,
    force: bool,
) -> Tuple[List[Path], bool]:
    if split_dir.exists() and not force:
        existing = sorted(split_dir.glob("*.bcf"))
        if existing:
            print(f"✅ 复用已有拆分目录: {split_dir}")
            return existing, False

    if split_dir.exists():
        shutil.rmtree(split_dir)
    split_dir.mkdir(parents=True, exist_ok=True)
    return _split_file(input_path, split_dir, parts=parts), True


def _process_chunk(input_path: Path, output_path: Path) -> None:
    file_size = input_path.stat().st_size
    bytes_processed = 0

    import re

    xml_start = re.compile(br"<\?xml")
    closing_tag = None
    seen_xml = False

    with input_path.open("rb") as infile, output_path.open("wb") as outfile:
        buffer = b""
        while True:
            chunk = infile.read(CHUNK_COPY_BYTES)
            if not chunk:
                break
            buffer += chunk
            bytes_processed += len(chunk)

            pos = 0
            buffer_len = len(buffer)
            search_pos = 0
            while True:
                if not seen_xml:
                    match = xml_start.search(buffer, search_pos)
                    if match is None:
                        buffer = buffer[-MIN_TEXT_LENGTH:]
                        break
                    seen_xml = True
                    search_pos = match.start()
                    buffer = buffer[search_pos:]
                    outfile.write(b"")

                    end_tag_match = re.search(br"<([A-Za-z0-9:_-]+)[^>]*>", buffer[:4096])
                    if end_tag_match:
                        closing_tag = b"</" + end_tag_match.group(1) + b">"

                if closing_tag is None:
                    break

                end_idx = buffer.find(closing_tag)
                if end_idx == -1:
                    outfile.write(buffer)
                    buffer = b""
                    break
                end_idx += len(closing_tag)
                outfile.write(buffer[:end_idx])
                return

        outfile.write(buffer)

    print(
        f"    ↳ chunk {input_path.name} processed，保留 {(output_path.stat().st_size / max(1, file_size)) * 100:.2f}% 文本"
    )


def _ensure_processed_chunks(
    chunk_files: Iterable[Path],
    processed_dir: Path,
    *,
    force: bool,
) -> Tuple[List[Path], bool]:
    chunk_files = list(chunk_files)
    if processed_dir.exists() and not force:
        existing = sorted(processed_dir.glob("*.bcf"))
        if len(existing) == len(chunk_files):
            print(f"✅ 复用已有精简块目录: {processed_dir}")
            return existing, False

    if processed_dir.exists():
        shutil.rmtree(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)

    processed_files: List[Path] = []
    total = len(chunk_files)
    start_time = time.time()
    for idx, chunk_file in enumerate(chunk_files, 1):
        target = processed_dir / f"processed_{chunk_file.name}"
        print(f"🔧 精简块 {idx}/{total}: {chunk_file.name}")
        _process_chunk(chunk_file, target)
        processed_files.append(target)
    elapsed = time.time() - start_time
    print(f"✅ 所有块精简完成，耗时 {elapsed:.2f} 秒")
    return processed_files, True


def _ensure_metadata_only_from_chunks(
    processed_files: Iterable[Path],
    output_path: Path,
    *,
    force: bool,
) -> Tuple[Path, bool]:
    processed_files = sorted(processed_files)
    if output_path.exists() and not force:
        print(f"✅ 复用已有精简合并文件: {output_path}")
        return output_path, False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as outfile:
        for idx, processed_file in enumerate(processed_files, 1):
            print(f"🔗 合并块 {idx}/{len(processed_files)}: {processed_file.name}")
            with processed_file.open("rb") as infile:
                shutil.copyfileobj(infile, outfile, length=CHUNK_COPY_BYTES)

    print(f"✅ 生成元数据专用 BCF: {output_path}")
    return output_path, True


def _parse_and_dump(
    metadata_bcf: Path,
    json_output_path: Path,
    *,
    pretty: bool,
) -> Dict[str, object]:
    parser = BCFParser(metadata_bcf)
    metadata = parser.parse()
    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    with json_output_path.open("w", encoding="utf-8") as fp:
        json.dump(metadata, fp, ensure_ascii=False, indent=2 if pretty else None)
        if not pretty:
            fp.write("\n")
    return metadata


def _summarize(metadata: Dict[str, object]) -> Dict[str, int]:
    summary: Dict[str, int] = {}

    def _count(value: object) -> int:
        if isinstance(value, dict):
            return len(value)
        if isinstance(value, list):
            return len(value)
        return 1

    root = metadata.get("元数据")
    if isinstance(root, dict):
        if len(root) == 1:
            inner = next(iter(root.values()))
            if isinstance(inner, dict):
                for key, value in inner.items():
                    summary[key] = _count(value)
            else:
                summary[next(iter(root.keys()))] = _count(inner)
        else:
            for key, value in root.items():
                summary[key] = _count(value)
    return summary


def run_pipeline(
    input_path: Path,
    *,
    parts: int = 100,
    split_dir: Optional[Path] = None,
    processed_dir: Optional[Path] = None,
    metadata_only_path: Optional[Path] = None,
    output_json: Optional[Path] = None,
    force_split: bool = False,
    force_process: bool = False,
    force_merge: bool = False,
    cleanup_intermediate: bool = False,
    pretty: bool = True,
    show_summary: bool = True,
) -> Path:
    input_path = input_path.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"原始BCF文件不存在: {input_path}")
    if input_path.suffix.lower() != ".bcf":
        raise ValueError("输入文件必须是.bcf格式")
    if parts <= 0:
        raise ValueError("--parts 必须为正整数")

    split_dir = (
        split_dir.expanduser().resolve()
        if split_dir
        else _default_split_dir(input_path)
    )
    processed_dir = (
        processed_dir.expanduser().resolve()
        if processed_dir
        else _default_processed_dir(input_path)
    )
    metadata_only_path = (
        metadata_only_path.expanduser().resolve()
        if metadata_only_path
        else _default_metadata_bcf_path(input_path)
    )
    json_output_path = (
        output_json.expanduser().resolve()
        if output_json
        else _default_json_path(input_path)
    )

    split_files, created_split = _ensure_split_parts(
        input_path, split_dir, parts=parts, force=force_split
    )
    processed_files, created_processed = _ensure_processed_chunks(
        split_files, processed_dir, force=force_process
    )
    metadata_source, created_metadata = _ensure_metadata_only_from_chunks(
        processed_files, metadata_only_path, force=force_merge
    )

    metadata = _parse_and_dump(metadata_source, json_output_path, pretty=pretty)

    if show_summary:
        summary = _summarize(metadata)
        if summary:
            print("\n📋 元数据摘要:")
            for key, count in summary.items():
                print(f"- {key}: {count}")

    print(f"\n✅ 元数据JSON已生成: {json_output_path}")

    if cleanup_intermediate:
        if created_split and split_dir.exists():
            shutil.rmtree(split_dir)
        if created_processed and processed_dir.exists():
            shutil.rmtree(processed_dir)
        if created_metadata and metadata_source.exists():
            metadata_source.unlink()

    return json_output_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="原始的SEM .bcf文件路径")
    parser.add_argument("--output", type=Path, help="最终JSON输出文件路径")
    parser.add_argument("--metadata-only", type=Path, help="合并后的精简 .bcf 保存路径")
    parser.add_argument("--split-dir", type=Path, help="拆分块保存目录")
    parser.add_argument("--processed-dir", type=Path, help="精简块保存目录")
    parser.add_argument(
        "--parts", type=int, default=100, help="拆分的块数（默认100）"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新执行所有阶段（拆分/精简/合并）",
    )
    parser.add_argument(
        "--force-split",
        action="store_true",
        help="仅强制重新拆分原始文件",
    )
    parser.add_argument(
        "--force-process",
        action="store_true",
        help="仅强制重新精简拆分块",
    )
    parser.add_argument(
        "--force-merge",
        action="store_true",
        help="仅强制重新合并精简块",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="完成后删除本次生成的拆分/精简/合并文件",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="生成后不打印概要信息",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="输出紧凑JSON（无缩进）",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    force_split = args.force or args.force_split
    force_process = args.force or args.force_process
    force_merge = args.force or args.force_merge

    try:
        run_pipeline(
            args.input,
            parts=args.parts,
            split_dir=args.split_dir,
            processed_dir=args.processed_dir,
            metadata_only_path=args.metadata_only,
            output_json=args.output,
            force_split=force_split,
            force_process=force_process,
            force_merge=force_merge,
            cleanup_intermediate=args.cleanup,
            pretty=not args.compact,
            show_summary=not args.no_summary,
        )
    except Exception as exc:
        print(f"❌ 处理失败: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
