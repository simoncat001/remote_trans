#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Watch instrument data directories, extract metadata, and upload to the backend."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import zipfile
from dataclasses import dataclass
from urllib.parse import urljoin
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1"

from backend_client import BackendUploadClient
from config_loader import (
    CredentialConfigError,
    DEFAULT_CONFIG_PATH,
    load_config,
    load_credentials,
    load_template_id,
    resolve_config_path,
)
from metadata_cli import EXTRACTORS, Extractor
from transfer_utils import (
    DEFAULT_CONCURRENCY,
    DEFAULT_ENV,
    DEFAULT_OBJECT_PREFIX,
    DEFAULT_PART_SIZE,
    ENV_BASE_URLS,
    FirstLevelDirHandler,
    UploadContext,
    multipart_upload,
    wait_until_stable,
)
from watchdog.observers import Observer

OBJECT_PREFIX = DEFAULT_OBJECT_PREFIX
PART_SIZE = DEFAULT_PART_SIZE
CONCURRENCY = DEFAULT_CONCURRENCY
DEFAULT_TEMPLATE_ID = "1bada3ae-630f-4924-a8c5-270aaf155d90"
DEFAULT_TEMPLATE_IDS = {"tem": "40884413-9949-4590-88b3-735a63b6e8f7"}
DEFAULT_REVIEW_STATUS = "unreviewed"
QUIET_SECS = 20
POLL_INTERVAL = 3
SUPPORTED_TYPES = ("tem", "sem", "xrf", "xrd", "synchrotron")
TEMPLATES_DIR = str(Path(__file__).resolve().parent.parent / "templates")


@dataclass(frozen=True)
class RawFileConfig:
    container_key: str
    file_key: str
    listing_key: Optional[str]
    listing_is_list: bool


@dataclass(frozen=True)
class InstrumentWorkflow:
    key: str
    extractor: Extractor
    raw_config: RawFileConfig


RAW_FILE_CONFIGS: Dict[str, RawFileConfig] = {
    "tem": RawFileConfig("原始文件", "表征原始数据文件", "表征原始数据列表", False),
    "sem": RawFileConfig("原始文件", "表征原始数据文件", "表征原始数据列表", False),
    "synchrotron": RawFileConfig("原始文件", "表征原始数据文件", "表征原始数据列表", False),
    "xrf": RawFileConfig("原始文件", "主要数据文件", "原始数据列表", True),
    "xrd": RawFileConfig("原始文件", "主要数据文件", "原始数据列表", True),
}

def _build_workflows() -> Dict[str, InstrumentWorkflow]:
    workflows: Dict[str, InstrumentWorkflow] = {}
    for key in SUPPORTED_TYPES:
        extractor = EXTRACTORS.get(key)
        if extractor is None:
            raise KeyError(f"metadata_cli extractor for '{key}' not found")
        raw_cfg = RAW_FILE_CONFIGS.get(key)
        if raw_cfg is None:
            raise KeyError(f"raw file configuration for '{key}' not defined")
        workflows[key] = InstrumentWorkflow(key, extractor, raw_cfg)
    return workflows


WORKFLOWS: Dict[str, InstrumentWorkflow] = _build_workflows()


def slugify(name: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", name).strip("_")
    return safe or "dataset"


def resolve_payload_root(dataset_dir: Path) -> tuple[Path, bool]:
    preferred = dataset_dir / "Format_file"
    if preferred.is_dir():
        return preferred, True
    return dataset_dir, False


def _list_files(dataset_dir: Path, *, walk_root: Optional[Path] = None) -> tuple[List[Path], int]:
    walk_root = walk_root or dataset_dir
    files: List[Path] = []
    skipped_symlinks = 0
    for root, dirnames, filenames in os.walk(walk_root):
        root_path = Path(root)
        # 避免符号链接目录导致递归膨胀或循环
        pruned: List[str] = []
        for d in dirnames:
            if (root_path / d).is_symlink():
                skipped_symlinks += 1
            else:
                pruned.append(d)
        dirnames[:] = pruned

        for name in filenames:
            path = root_path / name
            if path.is_symlink():
                skipped_symlinks += 1
                continue
            files.append(path)
    return sorted(files), skipped_symlinks


def collect_listing(
    dataset_dir: Path, *, walk_root: Optional[Path] = None, skip: Iterable[Path] = ()
) -> List[str]:
    skip_resolved = {p.resolve() for p in skip}
    listing: List[str] = []
    files, skipped_symlinks = _list_files(dataset_dir, walk_root=walk_root)
    if skipped_symlinks:
        print(f"[ZIP] skip {skipped_symlinks} symlinked entries from listing")
    for path in files:
        resolved = path.resolve()
        if resolved in skip_resolved:
            continue
        listing.append(path.relative_to(dataset_dir).as_posix())
    return listing


def _human_size(num: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{num}B"


def create_zip(dataset_dir: Path, *, walk_root: Optional[Path] = None) -> Path:
    zip_name = f"{slugify(dataset_dir.name)}_raw_files.zip"
    zip_path = dataset_dir / zip_name
    if zip_path.exists():
        zip_path.unlink()

    # 预先扫描一次，便于输出文件数和总大小，方便判断卡顿是否来自超大文件或文件过多
    files, skipped_symlinks = _list_files(dataset_dir, walk_root=walk_root)
    total_bytes = 0
    for file_path in files:
        try:
            total_bytes += file_path.stat().st_size
        except OSError:
            # 即便 stat 失败也继续尝试压缩，其它错误会在写入时暴露
            pass

    print(
        f"[ZIP] start {zip_path.name}: {len(files)} files, total ~{_human_size(total_bytes)}"
    )
    if skipped_symlinks:
        print(f"[ZIP] skip {skipped_symlinks} symlinked entries")

    added = 0
    last_report = time.time()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            arcname = file_path.relative_to(dataset_dir).as_posix()
            try:
                zf.write(file_path, arcname)
                added += 1
            except Exception as exc:  # pragma: no cover - IO driven
                print(f"[ZIP_ERR] {arcname}: {exc}")
                raise

            # 避免看起来“卡住”，按时间节奏打印进度
            now = time.time()
            if now - last_report >= 5:
                print(f"[ZIP] {added}/{len(files)} files... ({arcname})")
                last_report = now

    print(
        f"[ZIP] done {zip_path.name}: {added} files, {_human_size(zip_path.stat().st_size)}"
    )
    return zip_path


def update_raw_file_section(
    metadata: Dict[str, object],
    config: RawFileConfig,
    zip_url: str,
    listing: List[str],
) -> None:
    container = metadata.get(config.container_key)
    if not isinstance(container, dict):
        container = {}
    container[config.file_key] = zip_url
    if config.listing_key:
        if config.listing_is_list:
            container[config.listing_key] = listing
        else:
            container[config.listing_key] = "\n".join(listing)
    metadata[config.container_key] = container


def run_metadata(extractor: Extractor, dataset_dir: Path) -> Dict[str, object]:
    if extractor.key == "tem":
        template_path = f"{TEMPLATES_DIR}/TEM/透射电子显微表征元数据规范-2025.json"
    else:
        template_path = extractor.default_template()
    return extractor.runner(dataset_dir, template_path, None)


def process_directory(dir_path: str, ctx: UploadContext, workflow: InstrumentWorkflow) -> None:
    dataset_dir = Path(dir_path)
    print(f"[READY] {dataset_dir}")

    payload_root, trimmed = resolve_payload_root(dataset_dir)
    if trimmed:
        print(f"[ZIP] only compressing {payload_root.name} under {dataset_dir}")

    try:
        metadata = run_metadata(workflow.extractor, dataset_dir)
    except Exception as exc:
        print(f"[ERROR] metadata extraction failed for {dataset_dir}: {exc}")
        return

    listing = collect_listing(dataset_dir, walk_root=payload_root)
    zip_path = create_zip(dataset_dir, walk_root=payload_root)
    try:
        zip_url = multipart_upload(
            str(zip_path),
            "application/zip",
            session=ctx.client.session,
            headers=ctx.client.auth_headers(),
            api=ctx.part_upload_url,
            object_prefix=OBJECT_PREFIX,
            part_size=PART_SIZE,
            concurrency=CONCURRENCY,
        )
    except Exception as exc:
        print(f"[ERROR] upload failed for {zip_path}: {exc}")
        return
    finally:
        if zip_path.exists():
            try:
                zip_path.unlink()
            except OSError:
                pass

    update_raw_file_section(metadata, workflow.raw_config, zip_url, listing)

    payload = {
        "template_id": ctx.template_id,
        "json_data": json.dumps(metadata, ensure_ascii=False),
        "review_status": ctx.review_status,
    }
    try:
        resp = ctx.client.session.post(
            ctx.web_submit_url,
            json=payload,
            headers=ctx.client.auth_headers(),
            timeout=30,
        )
        if resp.status_code >= 400:
            print(f"[WEB_SUBMIT_ERR] {resp.status_code}\n{resp.text}")
        resp.raise_for_status()
    except Exception as exc:
        print(f"[ERROR] web_submit failed for {dataset_dir}: {exc}")
        return

    print(f"[WEB_SUBMIT] {dataset_dir} -> {resp.status_code} {resp.text}")


def build_callback(workflow: InstrumentWorkflow) -> Callable[[str, UploadContext], None]:
    return lambda path, ctx: process_directory(path, ctx, workflow)


def process_existing(root: Path, callback: Callable[[str, UploadContext], None], ctx: UploadContext, *, quiet_secs: int, poll_interval: int) -> None:
    for subdir in sorted(root.iterdir()):
        if not subdir.is_dir():
            continue
        if wait_until_stable(str(subdir), quiet_secs, poll_interval):
            callback(str(subdir), ctx)
        else:
            print(f"[TIMEOUT] {subdir} not stable in time (initial sweep)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="Root directory to watch for new datasets")
    parser.add_argument("--type", choices=SUPPORTED_TYPES, required=True, help="Metadata extractor type")
    parser.add_argument("--quiet-secs", type=int, default=QUIET_SECS, help="Seconds of inactivity before processing")
    parser.add_argument("--poll-interval", type=int, default=POLL_INTERVAL, help="Polling interval for stability checks")
    parser.add_argument("--env", choices=sorted(ENV_BASE_URLS.keys()), default=DEFAULT_ENV, help="Backend environment preset")
    parser.add_argument("--base-url", help="Override backend base URL")
    parser.add_argument(
        "--config",
        default=None,
        help=(
            "Credential config JSON path (honors REMOTE_TRANS_CONFIG env var, "
            f"defaults to {DEFAULT_CONFIG_PATH})"
        ),
    )
    parser.add_argument(
        "--template-id",
        default=None,
        help=(
            "Template ID for web_submit payload; defaults to template_ids.<type> in the config file "
            "or built-in fallbacks"
        ),
    )
    parser.add_argument("--review-status", default=DEFAULT_REVIEW_STATUS, help="Review status for submissions")
    parser.add_argument("--process-existing", action="store_true", help="Process existing first-level directories on startup")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    workflow = WORKFLOWS[args.type]
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        parser.error(f"{root} is not a directory")

    config_path = resolve_config_path(args.config)
    try:
        config_data = load_config(config_path)
        username, password = load_credentials(config_path, config_data=config_data)
    except CredentialConfigError as exc:
        parser.error(str(exc))

    if args.base_url:
        base_url = args.base_url
        resolved_env = None
    else:
        base_url = ENV_BASE_URLS[args.env]
        resolved_env = args.env
    base_url = base_url.rstrip("/") + "/"

    client = BackendUploadClient(base_url)
    try:
        client.login(username, password)
    except Exception as exc:
        parser.error(f"login failed: {exc}")

    default_template_id = DEFAULT_TEMPLATE_IDS.get(args.type, DEFAULT_TEMPLATE_ID)
    template_id = args.template_id or load_template_id(
        args.type, default_template_id, config_path, config_data=config_data
    )

    ctx = UploadContext(
        client=client,
        part_upload_url=urljoin(client.base_url, "api/development_data/part_upload"),
        web_submit_url=urljoin(client.base_url, "api/development_data/web_submit"),
        template_id=template_id,
        review_status=args.review_status,
    )

    callback = build_callback(workflow)

    if args.process_existing:
        process_existing(root, callback, ctx, quiet_secs=args.quiet_secs, poll_interval=args.poll_interval)

    handler = FirstLevelDirHandler(
        str(root),
        args.quiet_secs,
        args.poll_interval,
        callback,
        ctx,
    )

    observer = Observer()
    observer.schedule(handler, str(root), recursive=False)
    observer.start()

    if resolved_env:
        print(
            f"[WATCHING] {root} ({args.type}) quiet={args.quiet_secs}s poll={args.poll_interval}s -> {base_url} [env={resolved_env}]"
        )
    else:
        print(
            f"[WATCHING] {root} ({args.type}) quiet={args.quiet_secs}s poll={args.poll_interval}s -> {base_url}"
        )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
