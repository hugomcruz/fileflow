import json
import logging
from datetime import datetime

import httpx

from app.config import settings
from app.services._retry import with_retry
from app.services.onedrive import StorageFile, _allowed_extensions

logger = logging.getLogger(__name__)

API_URL = "https://api.dropboxapi.com/2"
CONTENT_URL = "https://content.dropboxapi.com/2"

# Dropbox upload session: max 150 MiB per request; use 100 MiB chunks.
_DROPBOX_CHUNK_SIZE = 100 * 1024 * 1024


class DropboxService:
    def _headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    async def list_files(self, access_token: str, folder_path: str, file_types: list[str], recursive: bool = False) -> list[StorageFile]:
        allowed = _allowed_extensions(file_types)
        files: list[StorageFile] = []
        try:
            async def _initial_page():
                async with httpx.AsyncClient() as client:
                    r = await client.post(
                        f"{API_URL}/files/list_folder",
                        headers={**self._headers(access_token), "Content-Type": "application/json"},
                        json={"path": folder_path or "", "recursive": recursive, "limit": 2000},
                    )
                    r.raise_for_status()
                    return r

            res = await with_retry(_initial_page, f"[dropbox] list_folder {folder_path}", logger)
            body = res.json()

            while True:
                for e in body.get("entries", []):
                    if e.get(".tag") != "file":
                        continue
                    ext = e["name"].rsplit(".", 1)[-1].lower() if "." in e["name"] else ""
                    if ext not in allowed:
                        continue
                    files.append(
                        StorageFile(
                            id=e["id"],
                            name=e["name"],
                            path=e["path_lower"],
                            size=e.get("size", 0),
                            modified_at=datetime.fromisoformat(e["server_modified"].replace("Z", "+00:00"))
                            if e.get("server_modified")
                            else None,
                        )
                    )

                if not body.get("has_more"):
                    break

                _cursor = body["cursor"]

                async def _next_page(_c=_cursor):
                    async with httpx.AsyncClient() as client:
                        r = await client.post(
                            f"{API_URL}/files/list_folder/continue",
                            headers={**self._headers(access_token), "Content-Type": "application/json"},
                            json={"cursor": _c},
                        )
                        r.raise_for_status()
                        return r

                res = await with_retry(_next_page, f"[dropbox] list_folder/continue {folder_path}", logger)
                body = res.json()

        except Exception:
            logger.exception("Dropbox listFiles error: %s", folder_path)
        return files

    async def download_file(self, access_token: str, _item_id: str, file_path: str) -> bytes:
        async def _fetch():
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{CONTENT_URL}/files/download",
                    headers={
                        **self._headers(access_token),
                        "Dropbox-API-Arg": json.dumps({"path": file_path}),
                        "Content-Type": "",
                    },
                )
                r.raise_for_status()
                return r

        res = await with_retry(_fetch, f"[dropbox] download {file_path}", logger)
        return res.content

    async def download_if_exists(self, access_token: str, path: str) -> bytes | None:
        async def _fetch():
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{CONTENT_URL}/files/download",
                    headers={
                        **self._headers(access_token),
                        "Dropbox-API-Arg": json.dumps({"path": path}),
                        "Content-Type": "",
                    },
                )
                if r.status_code in (404, 409):  # path/not_found
                    return None
                r.raise_for_status()
                return r

        res = await with_retry(_fetch, f"[dropbox] download_if_exists {path}", logger)
        if res is None:
            return None
        return res.content

    async def upload_file(self, access_token: str, target_path: str, data: bytes) -> None:
        threshold = settings.multipart_upload_threshold_mb * 1024 * 1024
        logger.debug("[dropbox] upload %d bytes → %s", len(data), target_path)
        if len(data) <= threshold:
            await self._upload_simple(access_token, target_path, data)
        else:
            await self._upload_session(access_token, target_path, data)

    async def _upload_simple(self, access_token: str, target_path: str, data: bytes) -> None:
        timeout = httpx.Timeout(connect=10.0, read=60.0, write=300.0, pool=10.0)

        async def _post():
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    f"{CONTENT_URL}/files/upload",
                    headers={
                        **self._headers(access_token),
                        "Content-Type": "application/octet-stream",
                        "Dropbox-API-Arg": json.dumps({
                            "path": target_path,
                            "mode": "add",
                            "autorename": True,
                            "mute": False,
                        }),
                    },
                    content=data,
                )
                r.raise_for_status()
                return r

        res = await with_retry(_post, f"[dropbox] upload {target_path}", logger)
        logger.debug("[dropbox] upload complete → %s (status %s)", target_path, res.status_code)

    async def _upload_session(self, access_token: str, target_path: str, data: bytes) -> None:
        """Use a Dropbox upload session for large files."""
        total = len(data)
        logger.debug("[dropbox] starting upload session for %d bytes → %s", total, target_path)
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=300.0, pool=10.0)

        # 1. Start session with the first chunk
        first_chunk = data[:_DROPBOX_CHUNK_SIZE]

        async def _start(_fc=first_chunk):
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    f"{CONTENT_URL}/files/upload_session/start",
                    headers={
                        **self._headers(access_token),
                        "Content-Type": "application/octet-stream",
                        "Dropbox-API-Arg": json.dumps({"close": False}),
                    },
                    content=_fc,
                )
                r.raise_for_status()
                return r

        res = await with_retry(_start, "[dropbox] upload_session/start", logger)
        session_id = res.json()["session_id"]
        offset = len(first_chunk)
        logger.debug("[dropbox] session started id=%s offset=%d", session_id, offset)

        # 2. Append middle chunks
        while offset + _DROPBOX_CHUNK_SIZE < total:
            chunk = data[offset : offset + _DROPBOX_CHUNK_SIZE]

            async def _append(_sid=session_id, _off=offset, _c=chunk):
                async with httpx.AsyncClient(timeout=timeout) as client:
                    r = await client.post(
                        f"{CONTENT_URL}/files/upload_session/append_v2",
                        headers={
                            **self._headers(access_token),
                            "Content-Type": "application/octet-stream",
                            "Dropbox-API-Arg": json.dumps({
                                "cursor": {"session_id": _sid, "offset": _off},
                                "close": False,
                            }),
                        },
                        content=_c,
                    )
                    r.raise_for_status()
                    return r

            await with_retry(_append, f"[dropbox] append offset={offset}", logger)
            offset += len(chunk)
            logger.debug("[dropbox] appended chunk, offset=%d/%d", offset, total)

        # 3. Finish with remaining bytes (may be empty if total is multiple of chunk size)
        last_chunk = data[offset:]

        async def _finish(_sid=session_id, _off=offset, _lc=last_chunk):
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    f"{CONTENT_URL}/files/upload_session/finish",
                    headers={
                        **self._headers(access_token),
                        "Content-Type": "application/octet-stream",
                        "Dropbox-API-Arg": json.dumps({
                            "cursor": {"session_id": _sid, "offset": _off},
                            "commit": {
                                "path": target_path,
                                "mode": "add",
                                "autorename": True,
                                "mute": False,
                            },
                        }),
                    },
                    content=_lc,
                )
                r.raise_for_status()
                return r

        res = await with_retry(_finish, "[dropbox] upload_session/finish", logger)
        logger.debug("[dropbox] upload session complete → %s (status %s)", target_path, res.status_code)

    async def delete_file(self, access_token: str, _item_id: str, file_path: str) -> None:
        async def _post():
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{API_URL}/files/delete_v2",
                    headers={**self._headers(access_token), "Content-Type": "application/json"},
                    json={"path": file_path},
                )
                r.raise_for_status()
                return r

        await with_retry(_post, f"[dropbox] delete {file_path}", logger)

    async def is_folder_empty(self, access_token: str, folder_path: str) -> bool:
        """Return True if the folder exists and contains no children."""
        async def _post():
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{API_URL}/files/list_folder",
                    headers={**self._headers(access_token), "Content-Type": "application/json"},
                    json={"path": folder_path, "limit": 1},
                )
                if r.status_code in (409,):  # path/not_found or not a folder
                    return None
                r.raise_for_status()
                return r

        res = await with_retry(_post, f"[dropbox] is_folder_empty {folder_path}", logger)
        if res is None:
            return False
        return len(res.json().get("entries", [])) == 0

    async def delete_folder(self, access_token: str, folder_path: str) -> None:
        """Delete a folder by its path."""
        async def _post():
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{API_URL}/files/delete_v2",
                    headers={**self._headers(access_token), "Content-Type": "application/json"},
                    json={"path": folder_path},
                )
                if r.status_code == 409:  # ignore not_found
                    return None
                r.raise_for_status()
                return r

        await with_retry(_post, f"[dropbox] delete_folder {folder_path}", logger)


dropbox_service = DropboxService()
