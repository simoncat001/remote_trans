#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for directory monitoring and authenticated uploads."""

from __future__ import annotations

import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import requests
from watchdog.events import FileSystemEvent, FileSystemEventHandler

from backend_client import BackendUploadClient

# ---------------------------------------------------------------------------
# Environment & upload defaults shared across transfer scripts
# ---------------------------------------------------------------------------
ENV_BASE_URLS = {
    "dev": "https://test.mgsdb.sjtu.edu.cn/",
    "prod": "https://mgsdb.sjtu.edu.cn/",
    "local": "http://127.0.0.1:8000/",
}
DEFAULT_ENV = "dev"
DEFAULT_BASE_URL = ENV_BASE_URLS[DEFAULT_ENV]
DEFAULT_OBJECT_PREFIX = "devdata"
DEFAULT_PART_SIZE = 16 * 1024 * 1024
DEFAULT_CONCURRENCY = 8


@dataclass
class UploadContext:
    """Parameters required to talk to the backend upload API."""

    client: BackendUploadClient
    part_upload_url: str
    web_submit_url: str
    template_id: str
    review_status: str


# ---------------------------------------------------------------------------
# Multipart upload helpers (mirrors backend's MinIO integration)
# ---------------------------------------------------------------------------
def _api_post(
    session: requests.Session,
    api: str,
    data: Dict[str, str],
    *,
    headers: Optional[Dict[str, str]] = None,
    files: Optional[Dict[str, object]] = None,
    timeout: int = 180,
) -> Dict[str, object]:
    resp = session.post(api, data=data, files=files, headers=headers or None, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _init_upload(
    session: requests.Session,
    headers: Dict[str, str],
    file_path: str,
    content_type: str,
    object_prefix: str,
    api: str,
) -> Tuple[str, str]:
    payload = {
        "op": "init",
        "filename": os.path.basename(file_path),
        "content_type": content_type,
        "object_prefix": object_prefix,
    }
    resp = _api_post(session, api, payload, headers=headers)
    session_id = resp.get("session_id")
    key = resp.get("key")
    if not session_id or not key:
        raise RuntimeError("multipart init response missing session_id/key")
    return str(session_id), str(key)


def _sign_parts(
    session: requests.Session,
    headers: Dict[str, str],
    session_id: str,
    parts: Iterable[int],
    api: str,
) -> Dict[int, str]:
    unique_parts = sorted(set(int(p) for p in parts))
    if not unique_parts:
        return {}
    ranges: List[Tuple[int, int]] = []
    start = end = unique_parts[0]
    for pn in unique_parts[1:]:
        if pn == end + 1:
            end = pn
        else:
            ranges.append((start, end))
            start = end = pn
    ranges.append((start, end))
    expr = ",".join(f"{a}-{b}" if a != b else f"{a}" for a, b in ranges)
    resp = _api_post(
        session,
        api,
        {"op": "sign", "session_id": session_id, "part_numbers": expr},
        headers=headers,
    )
    return {int(item["part_number"]): item["url"] for item in resp.get("parts", [])}


def _list_uploaded(
    session: requests.Session,
    headers: Dict[str, str],
    session_id: str,
    api: str,
) -> Dict[int, str]:
    resp = _api_post(session, api, {"op": "list", "session_id": session_id}, headers=headers)
    return {int(p["PartNumber"]): p["ETag"].strip('"') for p in resp.get("parts", [])}


def _complete_upload(
    session: requests.Session,
    headers: Dict[str, str],
    session_id: str,
    pn_etags: Iterable[Tuple[int, str]],
    api: str,
) -> Dict[str, object]:
    parts = [
        {"PartNumber": pn, "ETag": etag}
        for pn, etag in sorted(pn_etags, key=lambda item: item[0])
    ]
    payload = {"op": "complete", "session_id": session_id, "parts_json": json.dumps({"parts": parts})}
    return _api_post(session, api, payload, headers=headers)


def _plan_parts(file_size: int, part_size: int) -> List[Tuple[int, int, int]]:
    total = max(1, math.ceil(file_size / part_size))
    return [
        (idx + 1, idx * part_size, min(part_size, file_size - idx * part_size))
        for idx in range(total)
    ]


def _put_part(url: str, path: str, offset: int, size: int, pn: int, *, max_retry: int = 5) -> str:
    last_exc: Optional[Exception] = None
    for attempt in range(max_retry):
        try:
            with open(path, "rb") as fh:
                fh.seek(offset)
                chunk = fh.read(size)
            resp = requests.put(url, data=chunk, timeout=600)
            if resp.status_code // 100 != 2:
                raise RuntimeError(f"HTTP {resp.status_code}")
            etag = resp.headers.get("ETag")
            if not etag:
                for key, value in resp.headers.items():
                    if key.lower() == "etag":
                        etag = value
                        break
            if not etag:
                raise RuntimeError("missing ETag in PUT response")
            return etag.strip('"')
        except Exception as exc:  # pragma: no cover - retry loop
            last_exc = exc
            time.sleep(0.8 * (2 ** attempt))
    raise RuntimeError(f"upload part {pn} failed: {last_exc}")


def multipart_upload(
    file_path: str,
    content_type: str,
    *,
    session: requests.Session,
    headers: Dict[str, str],
    api: str,
    object_prefix: str = DEFAULT_OBJECT_PREFIX,
    part_size: int = DEFAULT_PART_SIZE,
    concurrency: int = DEFAULT_CONCURRENCY,
    resume: bool = True,
) -> str:
    size = os.path.getsize(file_path)
    if size <= 0:
        raise RuntimeError("cannot upload empty file")
    if part_size < 5 * 1024 * 1024:
        raise RuntimeError("part_size must be at least 5 MiB")

    session_id, key = _init_upload(session, headers, file_path, content_type, object_prefix, api)
    print(f"[init] {os.path.basename(file_path)} session={session_id} key={key}")

    plan = _plan_parts(size, part_size)
    done_map = _list_uploaded(session, headers, session_id, api) if resume else {}
    to_upload = [pn for pn, _, _ in plan if pn not in done_map]

    if to_upload:
        urls = _sign_parts(session, headers, session_id, to_upload, api)
        results: Dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_map = {
                executor.submit(_put_part, urls[pn], file_path, offset, chunk_size, pn): pn
                for pn, offset, chunk_size in plan
                if pn in to_upload
            }
            completed = 0
            for future in as_completed(future_map):
                pn = future_map[future]
                etag = future.result()
                results[pn] = etag
                completed += 1
                if completed % 10 == 0 or completed == len(future_map):
                    print(f"[upload] {completed}/{len(future_map)} parts")
        done_map.update(results)
    else:
        print("[resume] all parts already uploaded")

    ordered = [(pn, done_map[pn]) for pn, _, _ in plan]
    resp = _complete_upload(session, headers, session_id, ordered, api)
    url = resp.get("url")
    if not url:
        raise RuntimeError("multipart complete response missing url")
    print(f"[complete] {os.path.basename(file_path)} -> {url}")
    return str(url)


# ---------------------------------------------------------------------------
# Directory stabilisation helpers
# ---------------------------------------------------------------------------
def snapshot_tree(path: str) -> List[Tuple[str, int, int]]:
    snapshot: List[Tuple[str, int, int]] = []
    for dirpath, _, filenames in os.walk(path):
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                stat = os.stat(full)
            except FileNotFoundError:
                continue
            rel = os.path.relpath(full, path)
            snapshot.append((rel, stat.st_size, int(stat.st_mtime)))
    snapshot.sort()
    return snapshot


def wait_until_stable(
    path: str,
    quiet_secs: int,
    poll_interval: int,
    *,
    max_wait_secs: int = 3600,
) -> bool:
    start = time.time()
    previous = snapshot_tree(path)
    stable_for = 0
    while True:
        time.sleep(poll_interval)
        current = snapshot_tree(path)
        if current == previous:
            stable_for += poll_interval
        else:
            stable_for = 0
            previous = current
        if stable_for >= quiet_secs:
            return True
        if time.time() - start > max_wait_secs:
            return False


class FirstLevelDirHandler(FileSystemEventHandler):
    """Watch for first-level directory creation and trigger a callback."""

    def __init__(
        self,
        root: str,
        quiet_secs: int,
        poll_interval: int,
        callback: Callable[[str, UploadContext], None],
        ctx: UploadContext,
    ) -> None:
        super().__init__()
        self.root = os.path.abspath(root)
        self.quiet_secs = quiet_secs
        self.poll_interval = poll_interval
        self.callback = callback
        self.ctx = ctx
        self._pending: set[str] = set()

    def _is_first_level_subdir(self, path: str) -> bool:
        abs_path = os.path.abspath(path)
        parent = os.path.dirname(abs_path)
        return os.path.isdir(abs_path) and os.path.samefile(parent, self.root)

    def on_created(self, event: FileSystemEvent) -> None:  # pragma: no cover - filesystem driven
        if not event.is_directory:
            return
        subdir = os.path.abspath(event.src_path)
        if not self._is_first_level_subdir(subdir):
            return
        if subdir in self._pending:
            return
        self._pending.add(subdir)
        print(f"[CREATE] first-level dir: {subdir}")

        def worker() -> None:
            ok = wait_until_stable(subdir, self.quiet_secs, self.poll_interval)
            try:
                if ok:
                    self.callback(subdir, self.ctx)
                else:
                    print(f"[TIMEOUT] {subdir} not stable in time")
            finally:
                self._pending.discard(subdir)

        threading.Thread(target=worker, daemon=True).start()


__all__ = [
    "ENV_BASE_URLS",
    "DEFAULT_ENV",
    "DEFAULT_BASE_URL",
    "DEFAULT_OBJECT_PREFIX",
    "DEFAULT_PART_SIZE",
    "DEFAULT_CONCURRENCY",
    "UploadContext",
    "multipart_upload",
    "snapshot_tree",
    "wait_until_stable",
    "FirstLevelDirHandler",
]
