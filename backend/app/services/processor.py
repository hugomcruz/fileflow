import fnmatch
import hashlib
import io
import json
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session_factory
from app.models import OAuthConnection, ProcessingJob, ProcessingLog, Rule
from app.services.dropbox import dropbox_service
from app.services.onedrive import (
    PHOTO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    StorageFile,
    onedrive_service,
)
from app.services.token_refresh import ensure_fresh_token, refresh_token_now

logger = logging.getLogger(__name__)


# ─── Filename-pattern fallback ────────────────────────────────────────────────

def _parse_filename_datetime(filename: str) -> datetime | None:
    """
    Try to extract a datetime from a filename alone (used only when EXIF is absent).

    Supported patterns:
      OneDrive:  YYYYMMDD_HHMMSSF_iOS.ext   e.g. 20210915_143022123_iOS.jpg
                 3 underscore-delimited parts; 3rd part must be "iOS".
                 Date validated as %Y%m%d, time as %H%M%S%f (subsecond optional).

      Dropbox:   YYYY-MM-DD HH.MM.SS*.ext   e.g. 2021-09-15 14.30.22.jpg
                 2 space-delimited parts; time portion uses dots as separators.

    Returns a naive datetime on success, None otherwise.
    """
    basename = os.path.splitext(os.path.basename(filename))[0]

    # ── OneDrive: YYYYMMDD_HHMMSSF_iOS ───────────────────────────────────────
    parts = basename.split("_")
    if len(parts) == 3 and parts[2] == "iOS":
        try:
            datetime.strptime(parts[0], "%Y%m%d")
            datetime.strptime(parts[1], "%H%M%S%f")   # %f handles 1-6 subsecond digits
            return datetime.strptime(parts[0] + parts[1][:6], "%Y%m%d%H%M%S")
        except ValueError:
            pass

    # ── Dropbox: YYYY-MM-DD HH.MM.SS ─────────────────────────────────────────
    space_parts = basename.split(" ")
    if len(space_parts) == 2:
        try:
            return datetime.strptime(basename[:19], "%Y-%m-%d %H.%M.%S")
        except ValueError:
            pass

    return None


# ─── Timestamp extraction ─────────────────────────────────────────────────────

def _exif_timestamp(data: bytes, filename: str = "") -> tuple[datetime | None, str, bool]:
    """
    Extract timestamp from image EXIF data.
    Returns (datetime, subsecond_str, is_local_time), or (None, "000", False) if nothing found.
    Falls back to filename-pattern parsing before giving up.
    """
    subsecond = "000"
    is_local = False

    try:
        import piexif

        exif = piexif.load(data)
        exif_ifd = exif.get("Exif", {})

        # DateTimeOriginal
        raw_dt = exif_ifd.get(piexif.ExifIFD.DateTimeOriginal)
        if not raw_dt:
            raw_dt = exif_ifd.get(piexif.ExifIFD.DateTimeDigitized)
        if not raw_dt:
            raw_dt = exif.get("0th", {}).get(piexif.ImageIFD.DateTime)

        if raw_dt:
            ts_str = raw_dt.decode("ascii") if isinstance(raw_dt, bytes) else raw_dt

            # Subsecond
            raw_sub = exif_ifd.get(piexif.ExifIFD.SubSecTimeOriginal)
            if raw_sub:
                sub_str = raw_sub.decode("ascii") if isinstance(raw_sub, bytes) else str(raw_sub)
                subsecond = (sub_str + "000")[:3]  # pad/truncate to 3 digits

            # Timezone offset
            raw_off = exif_ifd.get(piexif.ExifIFD.OffsetTimeOriginal)
            offset_str = ""
            if raw_off:
                offset_str = raw_off.decode("ascii") if isinstance(raw_off, bytes) else str(raw_off)

            try:
                if offset_str:
                    dt = datetime.strptime(f"{ts_str}{offset_str}", "%Y:%m:%d %H:%M:%S%z")
                    # Normalise to UTC
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                else:
                    dt = datetime.strptime(ts_str, "%Y:%m:%d %H:%M:%S")
                    is_local = True  # no offset info → local time
                return dt, subsecond, is_local
            except ValueError:
                pass
    except Exception:
        pass

    # Pillow fallback
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        exif_data = img._getexif()  # noqa: SLF001
        if exif_data:
            from PIL.ExifTags import TAGS
            for tag_id, value in exif_data.items():
                tag = TAGS.get(tag_id, "")
                if tag in ("DateTimeOriginal", "DateTime", "DateTimeDigitized"):
                    try:
                        dt = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                        return dt, subsecond, True
                    except ValueError:
                        continue
    except Exception:
        pass

    # Filename fallback
    if filename:
        dt = _parse_filename_datetime(filename)
        if dt:
            return dt, subsecond, True

    return None, "000", False


def _video_timestamp(file_path: str, filename: str = "") -> datetime | None:
    """
    Extract the capture/encode datetime from video metadata via ffprobe.

    Tag priority (highest first):
      1. com.apple.quicktime.creationdate  – iPhone recorded date (most accurate, has timezone)
      2. creation_time                      – common container tag (MOV, MP4)
      3. encoded_date / tagged_date         – MKV / other containers

    Searches format-level tags first, then all stream-level tags.
    Falls back to filename-pattern parsing if ffprobe finds nothing.
    Returns a naive UTC datetime, or None if everything fails.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = json.loads(result.stdout)

        # Collect all tag dicts: format first, then each stream
        tag_sources: list[dict] = [data.get("format", {}).get("tags", {})]
        for stream in data.get("streams", []):
            tag_sources.append(stream.get("tags", {}))

        def _parse_tag(value: str) -> datetime | None:
            """Parse a timestamp string to a naive UTC datetime.

            Handles formats seen in the wild:
              - "2026-04-03T07:43:40.000000Z"   (ffprobe creation_time with microseconds)
              - "2026-04-03T07:43:40Z"           (ffprobe creation_time without microseconds)
              - "2024-01-15T14:30:00+05:30"      (ISO 8601 with offset)
              - "UTC 2024-01-15 14:30:00"         (Matroska encoded_date / tagged_date)
            """
            value = value.strip()

            # Strip trailing Z and try explicit strptime formats first (most reliable
            # across Python versions) before falling back to fromisoformat.
            normalised = value
            utc_offset = timezone.utc
            is_utc = False

            if value.endswith("Z"):
                normalised = value[:-1]
                is_utc = True

            # Explicit formats: with and without microseconds
            for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(normalised, fmt)
                    if is_utc:
                        return dt  # already UTC, return naive
                    # No Z but also no offset → treat as UTC (ffprobe default)
                    return dt
                except ValueError:
                    continue

            # ISO 8601 with explicit timezone offset (e.g. "+05:30")
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt.astimezone(utc_offset).replace(tzinfo=None)
            except ValueError:
                pass

            # Matroska-style "UTC 2024-01-15 14:30:00"
            for prefix in ("UTC ", "utc "):
                if value.startswith(prefix):
                    try:
                        dt = datetime.strptime(value[len(prefix):], "%Y-%m-%d %H:%M:%S")
                        return dt  # already UTC, naive
                    except ValueError:
                        pass

            return None

        # Priority order of tag names to try
        TAG_PRIORITY = [
            "com.apple.quicktime.creationdate",
            "creation_time",
            "encoded_date",
            "tagged_date",
        ]

        for tag_name in TAG_PRIORITY:
            for tags in tag_sources:
                value = tags.get(tag_name) or tags.get(tag_name.upper())
                if value:
                    dt = _parse_tag(value)
                    if dt:
                        logger.debug(
                            "[ffprobe] %s: matched tag '%s' = '%s' → %s",
                            filename or os.path.basename(file_path), tag_name, value, dt,
                        )
                        return dt

    except Exception:
        logger.debug("ffprobe failed for %s", file_path, exc_info=True)

    # Filename fallback (uses original filename, not the tmp path)
    result_dt = _parse_filename_datetime(filename or os.path.basename(file_path))
    logger.debug(
        "[ffprobe] %s: no metadata tag found, filename-pattern fallback → %s",
        filename or os.path.basename(file_path), result_dt,
    )
    return result_dt


def _build_new_name(original: str, ts: datetime, is_video: bool = False,
                    subsecond: str = "000", is_local_time: bool = False) -> str:
    """
    Build a new filename following the reference convention:
      Photos: p_YYYYMMDD_HHMMSS.ext
      Videos: v_YYYYMMDD_HHMMSS.ext
    """
    ext = os.path.splitext(original)[1].lstrip(".").lower()
    date_part = ts.strftime("%Y%m%d")
    time_part = ts.strftime("%H%M%S")
    prefix = "v" if is_video else "p"
    name = f"{prefix}_{date_part}_{time_part}"
    return f"{name}.{ext}" if ext else name


def _matches_pattern(name: str, pattern: str | None) -> bool:
    """Return True if the filename matches any comma-separated glob in pattern, or if pattern is empty."""
    if not pattern or not pattern.strip():
        return True
    for pat in pattern.split(","):
        pat = pat.strip()
        if pat and fnmatch.fnmatch(name.lower(), pat.lower()):
            return True
    return False


# ─── Template variable helpers ────────────────────────────────────────────────

def _photo_type(filename: str) -> str:
    """Classify as 'screenshot' (iPhone PNG) or 'photo'. All other media → 'video'."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return "screenshot" if ext == "png" else "photo"


def _build_template_vars(
    file: StorageFile,
    file_dt: datetime,
    exif_dt: datetime | None,
    media_type: str,
    new_name: str,
) -> dict:
    """
    Build the full variable dict for target path/filename template expansion.

    EXIF vars ({year}, {month}, …) use exif_dt when available, else output zeros (0000/00).
    File vars ({fileyear}, …) always use the file's last-modified date.

    Additional vars:
      {type}          → 'screenshot' | 'photo' | 'video'
      {originalname}  → original filename with extension
      {originalstem}  → original filename without extension
      {ext}           → extension without the leading dot
      {name}          → auto-generated canonical name (p_YYYYMMDD_… / v_YYYYMMDD_…)
    """
    fd = file_dt
    stem = os.path.splitext(file.name)[0]
    ext = os.path.splitext(file.name)[1].lstrip(".")
    if exif_dt is not None:
        exif_vars: dict = {
            "date":    exif_dt.strftime("%Y-%m-%d"),
            "time":    exif_dt.strftime("%H:%M:%S"),
            "year":    exif_dt.strftime("%Y"),
            "month":   exif_dt.strftime("%m"),
            "day":     exif_dt.strftime("%d"),
            "hour":    exif_dt.strftime("%H"),
            "minute":  exif_dt.strftime("%M"),
            "seconds": exif_dt.strftime("%S"),
        }
    else:
        exif_vars = {
            "date":    "0000-00-00",
            "time":    "00:00:00",
            "year":    "0000",
            "month":   "00",
            "day":     "00",
            "hour":    "00",
            "minute":  "00",
            "seconds": "00",
        }
    return {
        **exif_vars,
        # File-system date
        "filedate":    fd.strftime("%Y-%m-%d"),
        "filetime":    fd.strftime("%H:%M:%S"),
        "fileyear":    fd.strftime("%Y"),
        "filemonth":   fd.strftime("%m"),
        "fileday":     fd.strftime("%d"),
        "filehour":    fd.strftime("%H"),
        "fileminute":  fd.strftime("%M"),
        "fileseconds": fd.strftime("%S"),
        # Media classification
        "type": media_type,
        # File naming helpers
        "originalname": file.name,
        "originalstem": stem,
        "ext":          ext,
        "name":         new_name,
    }


# If any of these appear in the target_path template, the whole template
# is treated as a full path (directory + filename). Otherwise it's a directory
# and the auto-generated name is appended.
_FILENAME_VARS = frozenset({"{name}", "{originalname}", "{originalstem}", "{ext}"})


def _apply_template(template: str, tmpl_vars: dict) -> str:
    """Replace {varname} patterns in template (case-insensitive). Unknown names are left unchanged."""
    def _sub(m: re.Match) -> str:
        return str(tmpl_vars.get(m.group(1).lower(), m.group(0)))
    return re.sub(r"\{(\w+)\}", _sub, template)


def _resolve_target_file_path(template: str, tmpl_vars: dict, new_name: str) -> str:
    """
    Expand the target_path template and compute the final destination path.
    - If template contains a filename variable ({Name}, {OriginalName}, etc.)
      → treat expanded result as the complete path.
    - Otherwise → treat expanded result as a directory and append new_name.
    """
    expanded = _apply_template(template, tmpl_vars)
    if any(v in template.lower() for v in _FILENAME_VARS):
        return expanded
    return f"{expanded.rstrip('/')}/{new_name}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _suffixed_path(path: str, n: int) -> str:
    """Insert _N before the extension: /folder/p_20210915.jpg -> /folder/p_20210915_2.jpg"""
    stem, ext = os.path.splitext(path)
    return f"{stem}_{n}{ext}"


def _is_photo(name: str) -> bool:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext in PHOTO_EXTENSIONS


def _is_video(name: str) -> bool:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext in VIDEO_EXTENSIONS


# ─── Processor ────────────────────────────────────────────────────────────────

class ProcessorService:
    async def run_job(self, job_id: str) -> None:
        async with async_session_factory() as db:
            result = await db.execute(
                select(ProcessingJob)
                .where(ProcessingJob.id == job_id)
                .options(selectinload(ProcessingJob.rule))
            )
            job = result.scalar_one_or_none()
            if not job:
                return

            # Mark running
            job.status = "running"
            await db.commit()

            rule: Rule = job.rule

            try:
                # Fetch source and target OAuth connections
                if rule.source_connection_id:
                    src_result = await db.execute(
                        select(OAuthConnection).where(
                            OAuthConnection.id == rule.source_connection_id,
                            OAuthConnection.user_id == rule.user_id,
                        )
                    )
                    src_conn = src_result.scalar_one_or_none()
                else:
                    src_result = await db.execute(
                        select(OAuthConnection).where(
                            OAuthConnection.user_id == rule.user_id,
                            OAuthConnection.provider == rule.source_provider,
                        )
                    )
                    src_conn = src_result.scalars().first()

                if rule.target_connection_id:
                    tgt_result = await db.execute(
                        select(OAuthConnection).where(
                            OAuthConnection.id == rule.target_connection_id,
                            OAuthConnection.user_id == rule.user_id,
                        )
                    )
                    tgt_conn = tgt_result.scalar_one_or_none()
                else:
                    tgt_result = await db.execute(
                        select(OAuthConnection).where(
                            OAuthConnection.user_id == rule.user_id,
                            OAuthConnection.provider == rule.target_provider,
                        )
                    )
                    tgt_conn = tgt_result.scalars().first()

                if not src_conn or not tgt_conn:
                    raise RuntimeError(
                        f"Missing connection(s): source={rule.source_provider} target={rule.target_provider}"
                    )

                # Proactively refresh tokens that are about to expire
                src_conn = await ensure_fresh_token(db, src_conn)
                tgt_conn = await ensure_fresh_token(db, tgt_conn)

                src_svc = onedrive_service if rule.source_provider == "onedrive" else dropbox_service
                tgt_svc = onedrive_service if rule.target_provider == "onedrive" else dropbox_service

                # Human-readable connection labels for log entries
                def _conn_label(conn: OAuthConnection) -> str:
                    if conn.display_name:
                        return f"{conn.display_name} ({conn.provider})"
                    return conn.provider
                src_label = _conn_label(src_conn)
                tgt_label = _conn_label(tgt_conn)

                # Load file IDs already successfully processed for this rule
                done_result = await db.execute(
                    select(ProcessingLog.source_file_id)
                    .join(ProcessingJob, ProcessingLog.job_id == ProcessingJob.id)
                    .where(
                        ProcessingJob.rule_id == rule.id,
                        ProcessingLog.status == "success",
                        ProcessingLog.source_file_id.isnot(None),
                    )
                )
                already_done: set[str] = {row[0] for row in done_result}

                # List files – retry once with a fresh token on 401
                try:
                    files: list[StorageFile] = await src_svc.list_files(
                        src_conn.access_token, rule.source_path, rule.file_types, rule.recursive
                    )
                except Exception as exc:
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if status == 401:
                        logger.warning("401 on list_files for connection %s, refreshing token and retrying.", src_conn.id)
                        src_conn = await refresh_token_now(db, src_conn)
                        files = await src_svc.list_files(
                            src_conn.access_token, rule.source_path, rule.file_types, rule.recursive
                        )
                    else:
                        raise

                processed = skipped = errored = 0
                wants_photos = "photos" in rule.file_types or "both" in rule.file_types
                wants_videos = "videos" in rule.file_types or "both" in rule.file_types

                for file in files:
                    if file.id in already_done:
                        skipped += 1
                        await self._log(db, job_id, file.name, None, "skipped", "Already processed",
                            source_file_id=file.id, source_path=file.path,
                            source_connection=src_label, target_connection=tgt_label)
                        continue

                    if (not wants_photos and _is_photo(file.name)) or (
                        not wants_videos and _is_video(file.name)
                    ):
                        skipped += 1
                        await self._log(db, job_id, file.name, None, "skipped", "File type not selected",
                            source_path=file.path, source_connection=src_label, target_connection=tgt_label)
                        continue

                    if not _matches_pattern(file.name, rule.file_pattern):
                        skipped += 1
                        await self._log(db, job_id, file.name, None, "skipped", "Does not match file pattern",
                            source_path=file.path, source_connection=src_label, target_connection=tgt_label)
                        continue

                    tmp_path: str | None = None
                    try:
                        try:
                            data = await src_svc.download_file(
                                src_conn.access_token, file.id, file.path
                            )
                        except Exception as dl_exc:
                            status = getattr(getattr(dl_exc, "response", None), "status_code", None)
                            if status == 401:
                                logger.warning("401 on download for connection %s — refreshing token and retrying.", src_conn.id)
                                try:
                                    src_conn = await refresh_token_now(db, src_conn)
                                except Exception as ref_exc:
                                    raise RuntimeError(
                                        f"Token refresh failed for connection {src_conn.id} ({src_conn.provider}): {ref_exc}"
                                    ) from ref_exc
                                data = await src_svc.download_file(
                                    src_conn.access_token, file.id, file.path
                                )
                            else:
                                raise

                        timestamp: datetime | None = None
                        subsecond = "000"
                        is_local_time = False
                        is_video = _is_video(file.name)

                        if _is_photo(file.name):
                            timestamp, subsecond, is_local_time = _exif_timestamp(data, file.name)
                        elif is_video:
                            suffix = os.path.splitext(file.name)[1] or ".tmp"
                            with tempfile.NamedTemporaryFile(
                                suffix=suffix, delete=False, prefix="fileflow_"
                            ) as tmp:
                                tmp.write(data)
                                tmp_path = tmp.name
                            logger.debug("[tmp] %s written to %s", file.name, tmp_path)
                            timestamp = _video_timestamp(tmp_path, file.name)

                        if timestamp is not None:
                            new_name = _build_new_name(file.name, timestamp, is_video, subsecond, is_local_time)
                            logger.debug(
                                "[rename] %s → %s  (timestamp=%s, source=%s)",
                                file.name, new_name, timestamp,
                                "exif" if _is_photo(file.name) else "video-metadata",
                            )
                        else:
                            new_name = file.name  # no EXIF/metadata/filename-pattern → preserve original name
                            logger.debug("[rename] %s → (no timestamp found, keeping original name)", file.name)

                        # Build template variables from file metadata + EXIF
                        raw_file_dt = file.modified_at or datetime.now(timezone.utc)
                        file_dt = (
                            raw_file_dt.astimezone(timezone.utc).replace(tzinfo=None)
                            if getattr(raw_file_dt, "tzinfo", None)
                            else raw_file_dt
                        )
                        exif_dt = timestamp  # None when no EXIF/metadata/filename-pattern found
                        media_type = _photo_type(file.name) if _is_photo(file.name) else "video"
                        tmpl_vars = _build_template_vars(file, file_dt, exif_dt, media_type, new_name)
                        target_file_path = _resolve_target_file_path(rule.target_path, tmpl_vars, new_name)

                        src_hash = _sha256(data)
                        try:
                            final_path, already_there = await self._resolve_target_path(
                                tgt_svc, tgt_conn.access_token, target_file_path, src_hash,
                            )
                        except Exception as rp_exc:
                            status = getattr(getattr(rp_exc, "response", None), "status_code", None)
                            if status == 401:
                                logger.warning("401 on resolve_target_path for connection %s, refreshing and retrying.", tgt_conn.id)
                                tgt_conn = await refresh_token_now(db, tgt_conn)
                                final_path, already_there = await self._resolve_target_path(
                                    tgt_svc, tgt_conn.access_token, target_file_path, src_hash,
                                )
                            else:
                                raise
                        final_name = os.path.basename(final_path)

                        if not already_there:
                            try:
                                await tgt_svc.upload_file(tgt_conn.access_token, final_path, data)
                            except Exception as ul_exc:
                                status = getattr(getattr(ul_exc, "response", None), "status_code", None)
                                if status == 401:
                                    logger.warning("401 on upload for connection %s, refreshing and retrying.", tgt_conn.id)
                                    tgt_conn = await refresh_token_now(db, tgt_conn)
                                    await tgt_svc.upload_file(tgt_conn.access_token, final_path, data)
                                else:
                                    raise

                        if rule.delete_source:
                            try:
                                try:
                                    await src_svc.delete_file(src_conn.access_token, file.id, file.path)
                                except Exception as del_exc:
                                    status = getattr(getattr(del_exc, "response", None), "status_code", None)
                                    if status == 401:
                                        logger.warning("401 on delete_file for connection %s, refreshing and retrying.", src_conn.id)
                                        src_conn = await refresh_token_now(db, src_conn)
                                        await src_svc.delete_file(src_conn.access_token, file.id, file.path)
                                    else:
                                        raise
                                # Walk up the ancestor chain deleting empty folders
                                # up to (but not including) the rule's source_path.
                                parent = os.path.dirname(file.path)
                                while parent and parent != "/" and parent != rule.source_path:
                                    try:
                                        if await src_svc.is_folder_empty(src_conn.access_token, parent):
                                            await src_svc.delete_folder(src_conn.access_token, parent)
                                            logger.info("Deleted empty folder: %s", parent)
                                        else:
                                            break  # folder still has content; no point going higher
                                    except Exception as folder_exc:
                                        logger.warning("Could not clean up empty folder %s: %s", parent, folder_exc)
                                        break
                                    parent = os.path.dirname(parent)
                            except Exception as del_exc:
                                logger.warning("Failed to delete source file %s: %s", file.name, del_exc)

                        processed += 1
                        msg = "Duplicate: already at destination" if already_there else None
                        await self._log(db, job_id, file.name, final_name, "success",
                            message=msg, source_file_id=file.id,
                            source_path=file.path, target_path=final_path,
                            source_connection=src_label, target_connection=tgt_label)

                    except Exception as exc:
                        errored += 1
                        err_msg = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                        await self._log(db, job_id, file.name, None, "error", err_msg,
                            source_path=file.path,
                            source_connection=src_label, target_connection=tgt_label)
                        logger.warning("File processing error %s: %s", file.name, err_msg, exc_info=True)
                    finally:
                        if tmp_path:
                            try:
                                os.unlink(tmp_path)
                                logger.debug("[tmp] deleted %s", tmp_path)
                            except OSError as e:
                                logger.warning("[tmp] failed to delete %s: %s", tmp_path, e)

                job.status = "completed"
                job.files_processed = processed
                job.files_skipped = skipped
                job.files_errored = errored
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()

                rule.last_run_at = datetime.now(timezone.utc)
                await db.commit()

                logger.info(
                    "Job %s completed – processed:%d skipped:%d errors:%d",
                    job_id, processed, skipped, errored,
                )

            except Exception as exc:
                job.status = "failed"
                job.completed_at = datetime.now(timezone.utc)
                job.error_message = str(exc)
                await db.commit()
                logger.exception("Job %s failed", job_id)

    async def _resolve_target_path(
        self,
        tgt_svc,
        access_token: str,
        target_path: str,
        src_hash: str,
    ) -> tuple[str, bool]:
        """
        Determine the final write path and whether the file is already there.
        Returns (final_path, already_uploaded).
        - If the destination doesn't exist: upload to target_path.
        - If it exists with the same hash: skip upload (already_uploaded=True).
        - If it exists with a different hash: try _2, _3 ... until a free slot or hash match.
        """
        suffix = 0
        candidate = target_path
        while suffix <= 999:
            existing = await tgt_svc.download_if_exists(access_token, candidate)
            if existing is None:
                return candidate, False
            if _sha256(existing) == src_hash:
                return candidate, True
            suffix = 2 if suffix == 0 else suffix + 1
            candidate = _suffixed_path(target_path, suffix)
        raise RuntimeError(f"Could not find a unique target path for {target_path}")

    async def _log(
        self,
        db,
        job_id: str,
        original_name: str,
        new_name: str | None,
        status: str,
        message: str | None = None,
        source_file_id: str | None = None,
        source_path: str | None = None,
        target_path: str | None = None,
        source_connection: str | None = None,
        target_connection: str | None = None,
    ) -> None:
        db.add(
            ProcessingLog(
                job_id=job_id,
                original_name=original_name,
                new_name=new_name,
                status=status,
                message=message,
                source_file_id=source_file_id,
                source_path=source_path,
                target_path=target_path,
                source_connection=source_connection,
                target_connection=target_connection,
            )
        )
        await db.commit()


processor_service = ProcessorService()
