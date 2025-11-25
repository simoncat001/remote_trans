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
DEFAULT_REVIEW_STATUS = "unreviewed"
QUIET_SECS = 20
POLL_INTERVAL = 3
SUPPORTED_TYPES = ("tem", "sem", "xrf", "xrd", "synchrotron")


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


def collect_listing(dataset_dir: Path, *, skip: Iterable[Path] = ()) -> List[str]:
    skip_resolved = {p.resolve() for p in skip}
    listing: List[str] = []
    for path in sorted(dataset_dir.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in skip_resolved:
            continue
        listing.append(path.relative_to(dataset_dir).as_posix())
    return listing


def create_zip(dataset_dir: Path) -> Path:
    zip_name = f"{slugify(dataset_dir.name)}_raw_files.zip"
    zip_path = dataset_dir / zip_name
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(dataset_dir.rglob("*")):
            if not file_path.is_file():
                continue
            arcname = file_path.relative_to(dataset_dir).as_posix()
            zf.write(file_path, arcname)
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
    template_path = extractor.default_template()
    return extractor.runner(dataset_dir, template_path, None)


def process_directory(dir_path: str, ctx: UploadContext, workflow: InstrumentWorkflow) -> None:
    dataset_dir = Path(dir_path)
    print(f"[READY] {dataset_dir}")

    try:
        metadata = run_metadata(workflow.extractor, dataset_dir)
    except Exception as exc:
        print(f"[ERROR] metadata extraction failed for {dataset_dir}: {exc}")
        return

    listing = collect_listing(dataset_dir)
    zip_path = create_zip(dataset_dir)
    zip_uploaded = False
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
        zip_uploaded = True
    except Exception as exc:
        print(f"[ERROR] upload failed for {zip_path}: {exc}")
        return
    finally:
        if zip_uploaded and zip_path.exists():
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
    parser.add_argument("--username", help="Backend login username (or set UPLOAD_USERNAME env var)")
    parser.add_argument("--password", help="Backend login password (or set UPLOAD_PASSWORD env var)")
    parser.add_argument("--template-id", default=DEFAULT_TEMPLATE_ID, help="Template ID for web_submit payload")
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

    username = args.username or os.environ.get("UPLOAD_USERNAME")
    password = args.password or os.environ.get("UPLOAD_PASSWORD")
    if not username or not password:
        parser.error("--username/--password or UPLOAD_USERNAME/UPLOAD_PASSWORD must be provided")

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

    ctx = UploadContext(
        client=client,
        part_upload_url=urljoin(client.base_url, "api/development_data/part_upload"),
        web_submit_url=urljoin(client.base_url, "api/development_data/web_submit"),
        template_id=args.template_id,
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
