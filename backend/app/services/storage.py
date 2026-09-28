"""Supabase Storage for CR uploads, always as the caller.

Plain HTTP against the Storage API with the caller's own JWT — the bucket's
policies (supabase/migrations/20260928150000_cr_upload_workflow.sql) are
the real boundary: a CR can only write under their own `<uid>/` folder and
read their own files; an admin can read any of them. No service-role key.
"""

from __future__ import annotations

import uuid
from typing import Optional
from urllib.parse import quote

import httpx

from ..core import config

BUCKET = "cr-uploads"


class StorageError(RuntimeError):
    pass


def _headers(token: str, extra: Optional[dict] = None) -> dict:
    return {"Authorization": f"Bearer {token}", "apikey": config.SUPABASE_ANON_KEY, **(extra or {})}


def new_path(user_id: str, extension: str) -> str:
    return f"{user_id}/{uuid.uuid4().hex}.{extension}"


def upload(token: str, path: str, data: bytes, mime_type: str) -> str:
    url = f"{config.SUPABASE_URL}/storage/v1/object/{BUCKET}/{quote(path)}"
    resp = httpx.post(url, content=data, headers=_headers(token, {"Content-Type": mime_type, "x-upsert": "false"}),
                      timeout=30.0)
    if resp.status_code >= 300:
        raise StorageError(f"upload failed ({resp.status_code})")
    return path


def signed_url(token: str, path: str, expires_in: int = 600) -> str:
    url = f"{config.SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{quote(path)}"
    resp = httpx.post(url, json={"expiresIn": expires_in}, headers=_headers(token), timeout=15.0)
    if resp.status_code >= 300:
        raise StorageError(f"could not sign ({resp.status_code})")
    signed = resp.json().get("signedURL") or resp.json().get("signedUrl")
    if not signed:
        raise StorageError("no signed URL returned")
    return f"{config.SUPABASE_URL}/storage/v1{signed}" if signed.startswith("/") else signed
