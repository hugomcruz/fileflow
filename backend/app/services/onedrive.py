import logging
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

import httpx

from app.config import settings
from app.services._retry import with_retry

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"

# Graph upload sessions require chunk size to be a multiple of 320 KiB.
# 10 MiB = 32 × 320 KiB.
_GRAPH_CHUNK_SIZE = 10 * 1024 * 1024

PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "heic", "heif", "tiff", "tif", "webp", "raw", "cr2", "nef", "arw", "dng"}
VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "m4v", "wmv", "flv", "webm", "3gp", "mts", "m2ts"}


@dataclass
class StorageFile:
    id: str
    name: str
    path: str
    size: int
    mime_type: str | None = None
    modified_at: datetime | None = None


def _allowed_extensions(file_types: list[str]) -> set[str]:
    exts: set[str] = set()
    if "photos" in file_types or "both" in file_types:
        exts |= PHOTO_EXTENSIONS
    if "videos" in file_types or "both" in file_types:
        exts |= VIDEO_EXTENSIONS
    return exts


class OneDriveService:
    def _headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    async def list_files(self, access_token: str, folder_path: str, file_types: list[str], recursive: bool = False) -> list[StorageFile]:
        allowed = _allowed_extensions(file_types)
        files: list[StorageFile] = []
        folders_to_visit = [folder_path]
        logger.debug("[onedrive] list_files path=%s recursive=%s file_types=%s", folder_path, recursive, file_types)

        while folders_to_visit:
            current = folders_to_visit.pop()
            encoded = quote(current.strip("/"), safe="/")
            url: str | None = f"{GRAPH}/me/drive/root:/{encoded}:/children"
            params: dict = {"$select": "id,name,size,file,folder,lastModifiedDateTime", "$top": 1000}
            logger.debug("[onedrive] GET children: %s", current)

            try:
                while url:
                    _url, _params = url, dict(params) if params else {}

                    async def _fetch_page(_u=_url, _p=_params):
                        async with httpx.AsyncClient() as _c:
                            _r = await _c.get(_u, headers=self._headers(access_token), params=_p)
                            logger.debug("[onedrive] GET %s → status %s", _u.split("?")[0], _r.status_code)
                            _r.raise_for_status()
                            return _r

                    res = await with_retry(_fetch_page, f"[onedrive] list_files page {current}", logger)
                    body = res.json()
                    items = body.get("value", [])
                    params = {}  # params only needed for first request; next link carries them

                    for item in items:
                        if recursive and item.get("folder"):
                            # Queue subfolder for processing
                            sub_path = f"{current.rstrip('/')}/{item['name']}"
                            folders_to_visit.append(sub_path)
                            continue
                        if not item.get("file"):
                            continue
                        ext = item["name"].rsplit(".", 1)[-1].lower() if "." in item["name"] else ""
                        if ext not in allowed:
                            continue
                        files.append(
                            StorageFile(
                                id=item["id"],
                                name=item["name"],
                                path=f"{current}/{item['name']}",
                                size=item.get("size", 0),
                                mime_type=item.get("file", {}).get("mimeType"),
                                modified_at=datetime.fromisoformat(item["lastModifiedDateTime"].replace("Z", "+00:00"))
                                if item.get("lastModifiedDateTime")
                                else None,
                            )
                        )

                    url = body.get("@odata.nextLink")  # follow pagination
            except Exception:
                logger.exception("OneDrive listFiles error: %s", current)

        logger.debug("[onedrive] list_files done: %d file(s) found under %s", len(files), folder_path)
        return files

    async def download_file(self, access_token: str, item_id: str, _path: str) -> bytes:
        url = f"{GRAPH}/me/drive/items/{item_id}/content"
        logger.debug("[onedrive] download item_id=%s path=%s", item_id, _path)

        async def _fetch():
            async with httpx.AsyncClient(follow_redirects=True) as client:
                r = await client.get(url, headers=self._headers(access_token))
                r.raise_for_status()
                return r

        res = await with_retry(_fetch, f"[onedrive] download {_path}", logger)
        logger.debug("[onedrive] download complete: %d bytes for %s", len(res.content), _path)
        return res.content

    async def download_if_exists(self, access_token: str, path: str) -> bytes | None:
        encoded = quote(path.strip("/"), safe="/")
        url = f"{GRAPH}/me/drive/root:/{encoded}:/content"
        logger.debug("[onedrive] download_if_exists path=%s", path)

        async def _fetch():
            async with httpx.AsyncClient(follow_redirects=True) as client:
                r = await client.get(url, headers=self._headers(access_token))
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r

        res = await with_retry(_fetch, f"[onedrive] download_if_exists {path}", logger)
        if res is None:
            logger.debug("[onedrive] not found (404): %s", path)
            return None
        logger.debug("[onedrive] found: %d bytes for %s", len(res.content), path)
        return res.content

    async def upload_file(self, access_token: str, target_path: str, data: bytes) -> None:
        threshold = settings.multipart_upload_threshold_mb * 1024 * 1024
        logger.debug("[onedrive] upload %d bytes → %s", len(data), target_path)
        if len(data) <= threshold:
            await self._upload_simple(access_token, target_path, data)
        else:
            await self._upload_session(access_token, target_path, data)

    async def _upload_simple(self, access_token: str, target_path: str, data: bytes) -> None:
        encoded = quote(target_path.strip("/"), safe="/")
        url = f"{GRAPH}/me/drive/root:/{encoded}:/content"
        timeout = httpx.Timeout(connect=10.0, read=60.0, write=300.0, pool=10.0)

        async def _put():
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.put(
                    url,
                    headers={**self._headers(access_token), "Content-Type": "application/octet-stream"},
                    content=data,
                )
                r.raise_for_status()
                return r

        res = await with_retry(_put, f"[onedrive] upload {target_path}", logger)
        logger.debug("[onedrive] upload complete → %s (status %s)", target_path, res.status_code)

    async def _upload_session(self, access_token: str, target_path: str, data: bytes) -> None:
        """Use a Graph upload session for large files (avoids timeout on big uploads)."""
        encoded = quote(target_path.strip("/"), safe="/")
        session_url = f"{GRAPH}/me/drive/root:/{encoded}:/createUploadSession"
        total = len(data)
        logger.debug("[onedrive] starting upload session for %d bytes → %s", total, target_path)
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=300.0, pool=10.0)

        # 1. Create upload session
        async def _create_session():
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    session_url,
                    headers={**self._headers(access_token), "Content-Type": "application/json"},
                    json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
                )
                r.raise_for_status()
                return r

        res = await with_retry(_create_session, f"[onedrive] createUploadSession {target_path}", logger)
        upload_url = res.json()["uploadUrl"]
        logger.debug("[onedrive] upload session created")

        # 2. Upload chunks (upload_url is pre-authenticated; no Authorization header)
        offset = 0
        while offset < total:
            end = min(offset + _GRAPH_CHUNK_SIZE, total) - 1
            chunk = data[offset : end + 1]

            async def _put_chunk(_u=upload_url, _o=offset, _e=end, _c=chunk, _t=total):
                async with httpx.AsyncClient(timeout=timeout) as client:
                    r = await client.put(
                        _u,
                        headers={
                            "Content-Length": str(len(_c)),
                            "Content-Range": f"bytes {_o}-{_e}/{_t}",
                            "Content-Type": "application/octet-stream",
                        },
                        content=_c,
                    )
                    if r.status_code not in (200, 201, 202):
                        r.raise_for_status()
                    return r

            res = await with_retry(_put_chunk, f"[onedrive] chunk {offset}-{end}/{total}", logger)
            logger.debug(
                "[onedrive] chunk bytes %d-%d/%d uploaded (status %s)",
                offset, end, total, res.status_code,
            )
            offset = end + 1

        logger.debug("[onedrive] upload session complete → %s", target_path)

    async def delete_file(self, access_token: str, item_id: str, _path: str) -> None:
        url = f"{GRAPH}/me/drive/items/{item_id}"
        logger.debug("[onedrive] delete item_id=%s path=%s", item_id, _path)

        async def _delete():
            async with httpx.AsyncClient() as client:
                r = await client.delete(url, headers=self._headers(access_token))
                r.raise_for_status()
                return r

        res = await with_retry(_delete, f"[onedrive] delete {_path}", logger)
        logger.debug("[onedrive] delete complete: %s (status %s)", _path, res.status_code)

    async def is_folder_empty(self, access_token: str, folder_path: str) -> bool:
        """Return True if the folder exists and contains no children."""
        encoded = quote(folder_path.strip("/"), safe="/")
        url = f"{GRAPH}/me/drive/root:/{encoded}:/children"
        logger.debug("[onedrive] is_folder_empty path=%s", folder_path)

        async def _fetch():
            async with httpx.AsyncClient() as client:
                r = await client.get(url, headers=self._headers(access_token), params={"$select": "id", "$top": 1})
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r

        res = await with_retry(_fetch, f"[onedrive] is_folder_empty {folder_path}", logger)
        if res is None:
            logger.debug("[onedrive] folder not found (404): %s → treating as not empty", folder_path)
            return False
        empty = len(res.json().get("value", [])) == 0
        logger.debug("[onedrive] folder %s is %s", folder_path, "empty" if empty else "not empty")
        return empty

    async def delete_folder(self, access_token: str, folder_path: str) -> None:
        """Delete a folder by its path (uses the item endpoint via path)."""
        encoded = quote(folder_path.strip("/"), safe="/")
        url = f"{GRAPH}/me/drive/root:/{encoded}"
        logger.debug("[onedrive] delete_folder path=%s", folder_path)

        async def _delete():
            async with httpx.AsyncClient() as client:
                r = await client.delete(url, headers=self._headers(access_token))
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r

        res = await with_retry(_delete, f"[onedrive] delete_folder {folder_path}", logger)
        if res is None:
            logger.debug("[onedrive] delete_folder: already gone (404): %s", folder_path)
            return
        logger.debug("[onedrive] delete_folder complete: %s (status %s)", folder_path, res.status_code)


onedrive_service = OneDriveService()
