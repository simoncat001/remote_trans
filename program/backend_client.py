"""Authenticated upload helpers for the development-data backend.

This module provides three helpers:
* ``login`` – obtain an access token by calling the FastAPI ``/api/token`` endpoint.
* ``upload_small_file`` – send small files through the direct upload endpoint.
* ``upload_large_file`` – stream large files through the multipart upload workflow.

All requests share the same ``requests.Session`` so the caller can reuse
connections across multiple uploads.  Each helper raises ``RuntimeError`` when an
unexpected status code or response payload is returned.
"""

from __future__ import annotations

import math
import mimetypes
import os
from typing import Dict, Optional

import requests


DEFAULT_CHUNK_SIZE = 16 * 1024 * 1024  # 16 MiB, matches backend default


class BackendUploadClient:
    """Encapsulates authentication and upload helpers for the backend service."""

    def __init__(self, base_url: str):
        if not base_url:
            raise ValueError("base_url must be provided")
        # Normalise with trailing slash so ``_join`` works reliably.
        self._base_url = base_url.rstrip("/") + "/"
        self._session = requests.Session()
        self._access_token: Optional[str] = None

    @property
    def session(self) -> requests.Session:
        """Return the underlying :class:`requests.Session` instance."""

        return self._session

    @property
    def base_url(self) -> str:
        """Return the normalised service base URL."""

        return self._base_url

    # ------------------------------------------------------------------
    def _join(self, path: str) -> str:
        path = path.lstrip("/")
        return f"{self._base_url}{path}"

    def _headers(self) -> Dict[str, str]:
        if not self._access_token:
            raise RuntimeError("login must be called before making authenticated requests")
        return {"Authorization": f"Bearer {self._access_token}"}

    def auth_headers(self) -> Dict[str, str]:
        """Return a copy of the current ``Authorization`` header mapping."""

        return dict(self._headers())

    # ------------------------------------------------------------------
    def login(self, username: str, password: str) -> Dict[str, str]:
        """Authenticate the user and cache the access token.

        Parameters
        ----------
        username: str
            Username registered in the backend system.
        password: str
            Corresponding password.

        Returns
        -------
        Dict[str, str]
            The token payload returned by ``/api/token`` (access & refresh token).
        """

        data = {
            "username": username,
            "password": password,
            "grant_type": "password",
        }
        resp = self._session.post(self._join("api/token"), data=data, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"login failed: HTTP {resp.status_code}: {resp.text}")
        payload = resp.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("login response missing access_token")
        self._access_token = token
        return payload

    # ------------------------------------------------------------------
    def upload_small_file(self, file_path: str) -> Dict[str, str]:
        """Upload a small file directly via ``/api/development_data/upload_file``.

        The backend stores the file in MinIO and returns the object key together
        with the download proxy URL.  The file is read into memory once – this
        endpoint should therefore only be used for small payloads.
        """

        if not os.path.isfile(file_path):
            raise FileNotFoundError(file_path)

        filename = os.path.basename(file_path)
        content_type, _ = mimetypes.guess_type(filename)
        content_type = content_type or "application/octet-stream"

        with open(file_path, "rb") as fh:
            files = {"file": (filename, fh, content_type)}
            resp = self._session.post(
                self._join("api/development_data/upload_file"),
                headers=self._headers(),
                files=files,
                timeout=300,
            )

        if resp.status_code != 200:
            raise RuntimeError(f"small file upload failed: HTTP {resp.status_code}: {resp.text}")
        return resp.json()

    # ------------------------------------------------------------------
    def upload_large_file(
        self,
        file_path: str,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> Dict[str, str]:
        """Upload a large file using the backend's multipart workflow.

        Steps:
        1. Initialise a multipart session via ``/api/development_data/init_multipart``.
        2. Stream each chunk through ``/api/development_data/upload_part_direct``.
        3. Finalise the upload with ``/api/development_data/complete_multipart``.
        """

        if not os.path.isfile(file_path):
            raise FileNotFoundError(file_path)
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")

        filename = os.path.basename(file_path)
        content_type, _ = mimetypes.guess_type(filename)
        content_type = content_type or "application/octet-stream"

        # Step 1 – initialise session
        init_resp = self._session.post(
            self._join("api/development_data/init_multipart"),
            headers=self._headers(),
            data={"filename": filename, "content_type": content_type},
            timeout=60,
        )
        if init_resp.status_code != 200:
            raise RuntimeError(
                f"init multipart failed: HTTP {init_resp.status_code}: {init_resp.text}"
            )
        init_payload = init_resp.json()
        upload_session = init_payload.get("upload_session")
        if not upload_session:
            raise RuntimeError("init response missing upload_session")

        # Step 2 – upload parts
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise RuntimeError("cannot upload empty file")
        total_parts = max(1, math.ceil(file_size / chunk_size))
        with open(file_path, "rb") as fh:
            for part_number in range(1, total_parts + 1):
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                files = {"file": (filename, chunk, content_type)}
                data = {
                    "part_number": str(part_number),
                    "total_parts": str(total_parts),
                    "upload_session": upload_session,
                }
                part_resp = self._session.post(
                    self._join("api/development_data/upload_part_direct"),
                    headers=self._headers(),
                    data=data,
                    files=files,
                    timeout=600,
                )
                if part_resp.status_code != 200:
                    raise RuntimeError(
                        f"upload part {part_number} failed: HTTP {part_resp.status_code}: {part_resp.text}"
                    )

        # Step 3 – complete upload
        complete_resp = self._session.post(
            self._join("api/development_data/complete_multipart"),
            headers=self._headers(),
            data={"upload_session": upload_session},
            timeout=120,
        )
        if complete_resp.status_code != 200:
            raise RuntimeError(
                f"complete multipart failed: HTTP {complete_resp.status_code}: {complete_resp.text}"
            )
        return complete_resp.json()


__all__ = ["BackendUploadClient", "DEFAULT_CHUNK_SIZE"]
