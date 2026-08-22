from __future__ import annotations

import hashlib
import io
import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Iterable

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

from models import Photo, db, log_action


ALLOWED_RECORD_TYPES = {
    "meal",
    "med_submission",
    "med",
    "vital",
    "bowel",
    "medplan",
    "abnormal",
}
ALLOWED_KINDS = {"care_evidence", "med_reference", "abnormal_followup"}
MAX_SINGLE_UPLOAD_BYTES = 20 * 1024 * 1024
THUMBNAIL_SIZE = (420, 420)


@dataclass
class MediaSaveResult:
    photos: list[Photo] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: int = 0

    @property
    def saved_count(self) -> int:
        return len(self.photos)


def _normalise_type(record_type: str) -> str:
    if record_type not in ALLOWED_RECORD_TYPES:
        raise ValueError(f"unsupported record type: {record_type}")
    return record_type


def _normalise_kind(kind: str) -> str:
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"unsupported media kind: {kind}")
    return kind


def _relative_directory(
    *,
    kind: str,
    elder_id: int,
    record_type: str,
    record_id: int,
    record_date: date,
) -> PurePosixPath:
    safe_elder_id = int(elder_id or 0)
    root = PurePosixPath("elders") / f"elder-{safe_elder_id:06d}"
    if kind == "med_reference":
        return root / "medication-plans" / f"plan-{record_id:06d}" / "reference"
    if kind == "abnormal_followup":
        return root / "abnormal-events" / f"event-{record_id:06d}" / "followup"

    folder = {
        "meal": "meal",
        "med_submission": "medication",
        "med": "medication",
        "vital": "vital",
        "bowel": "bowel",
    }.get(record_type, record_type)
    record_label = (
        f"submission-{record_id:06d}"
        if record_type == "med_submission"
        else f"record-{record_id:06d}"
    )
    return (
        root
        / "care-records"
        / f"{record_date:%Y}"
        / f"{record_date:%m}"
        / f"{record_date:%d}"
        / folder
        / record_label
    )


def _absolute_path(relative_name: str) -> Path:
    upload_root = Path(current_app.config["UPLOAD_DIR"]).resolve()
    relative = relative_name.replace("\\", "/").lstrip("/")
    candidate = (upload_root / relative).resolve()
    if os.path.commonpath([str(upload_root), str(candidate)]) != str(upload_root):
        raise ValueError("invalid media path")
    return candidate


def file_path(photo: Photo, *, thumbnail: bool = False) -> Path:
    relative = photo.thumbnail_filename if thumbnail else photo.filename
    if not relative:
        relative = photo.filename
    return _absolute_path(relative)


def _read_upload(uploaded) -> bytes:
    data = uploaded.read(MAX_SINGLE_UPLOAD_BYTES + 1)
    if len(data) > MAX_SINGLE_UPLOAD_BYTES:
        raise ValueError("圖片檔案超過 20 MB")
    if not data:
        raise ValueError("圖片內容為空")
    return data


def _prepare_image(raw: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("不是可辨識的圖片檔") from exc
    image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        image = image.convert("RGB")
    return image


def _write_jpeg(image: Image.Image, destination: Path, *, max_width: int) -> tuple[int, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    output = image.copy()
    if output.width > max_width:
        ratio = max_width / output.width
        output = output.resize(
            (max_width, max(1, round(output.height * ratio))),
            Image.Resampling.LANCZOS,
        )
    output.save(
        destination,
        "JPEG",
        quality=int(current_app.config.get("PHOTO_QUALITY", 82)),
        optimize=True,
    )
    return output.size


def _write_thumbnail(image: Image.Image, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    thumb = image.copy()
    thumb.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
    thumb.save(destination, "JPEG", quality=76, optimize=True)


def save_images(
    files: Iterable,
    *,
    kind: str,
    record_type: str,
    record_id: int,
    elder_id: int,
    record_date: date | None = None,
    uploaded_by: int | None = None,
    limit: int | None = None,
    start_order: int = 0,
) -> MediaSaveResult:
    """Validate, normalise, structure and register uploaded images.

    The caller controls the surrounding database transaction and commits after all
    related care data, media rows and abnormal events are ready.
    """

    kind = _normalise_kind(kind)
    record_type = _normalise_type(record_type)
    record_date = record_date or date.today()
    candidates = [item for item in files if item and getattr(item, "filename", "")]
    result = MediaSaveResult()
    if limit is not None and len(candidates) > limit:
        result.skipped = len(candidates) - max(limit, 0)
        candidates = candidates[: max(limit, 0)]
        result.errors.append(f"超過圖片數量上限，已略過 {result.skipped} 張")

    relative_dir = _relative_directory(
        kind=kind,
        elder_id=elder_id,
        record_type=record_type,
        record_id=record_id,
        record_date=record_date,
    )
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")

    for uploaded in candidates:
        absolute_file = None
        absolute_thumb = None
        try:
            raw = _read_upload(uploaded.stream)
            image = _prepare_image(raw)
            random_part = uuid.uuid4().hex[:8]
            order = start_order + len(result.photos) + 1
            marker_prefix = {
                "med_reference": "p",
                "abnormal_followup": "a",
            }.get(kind, "s" if record_type == "med_submission" else "r")
            marker = f"{marker_prefix}{record_id:06d}"
            base = f"{record_type}_{marker}_{timestamp}_{order:02d}_{random_part}"
            relative_file = relative_dir / f"{base}.jpg"
            relative_thumb = relative_dir / f"{base}_thumb.jpg"
            absolute_file = _absolute_path(relative_file.as_posix())
            absolute_thumb = _absolute_path(relative_thumb.as_posix())

            stored_width, stored_height = _write_jpeg(
                image,
                absolute_file,
                max_width=int(current_app.config.get("PHOTO_MAX_WIDTH", 1280)),
            )
            _write_thumbnail(image, absolute_thumb)
            checksum = hashlib.sha256(absolute_file.read_bytes()).hexdigest()
            photo = Photo(
                kind=kind,
                record_type=record_type,
                record_id=record_id,
                elder_id=elder_id,
                record_date=record_date,
                filename=relative_file.as_posix(),
                thumbnail_filename=relative_thumb.as_posix(),
                uploaded_by=uploaded_by,
                sort_order=order,
                is_primary=(kind == "med_reference" and order == 1),
                width=stored_width,
                height=stored_height,
                file_size=absolute_file.stat().st_size,
                mime_type="image/jpeg",
                checksum=checksum,
            )
            db.session.add(photo)
            db.session.flush()
            result.photos.append(photo)
        except Exception as exc:  # Keep the care record, but make upload failure visible.
            for partial in (absolute_file, absolute_thumb):
                try:
                    if partial and partial.exists():
                        partial.unlink()
                except OSError:
                    current_app.logger.exception("Unable to remove partial media file %s", partial)
            current_app.logger.exception("Photo upload failed for %s", record_type)
            result.errors.append(f"{getattr(uploaded, 'filename', '圖片')}：{exc}")

    if result.photos:
        log_action(
            uploaded_by,
            "create",
            "photo",
            result.photos[0].id,
            f"{record_type} +{len(result.photos)} photo(s)",
            elder_id=elder_id,
            event_code="photo.upload",
            metadata={
                "kind": kind,
                "record_type": record_type,
                "record_id": record_id,
                "photo_ids": [photo.id for photo in result.photos],
            },
        )
    return result


def active_photos_query():
    return Photo.query.filter(Photo.deleted_at.is_(None))


def photos_for(record_type: str, record_id: int, *, kind: str | None = None):
    query = active_photos_query().filter_by(
        record_type=record_type, record_id=record_id
    )
    if kind:
        query = query.filter(Photo.kind == kind)
    return query.order_by(Photo.is_primary.desc(), Photo.sort_order, Photo.id).all()


def soft_delete_photo(photo: Photo, *, user_id: int | None, reason: str = "") -> None:
    if photo.deleted_at is not None:
        return
    photo.deleted_at = datetime.now()
    for path in (photo.filename, photo.thumbnail_filename):
        if not path:
            continue
        try:
            target = _absolute_path(path)
            if target.exists():
                target.unlink()
        except Exception:
            current_app.logger.exception("Unable to delete media file %s", path)
    log_action(
        user_id,
        "delete",
        "photo",
        photo.id,
        reason or f"{photo.kind}/{photo.record_type}",
        elder_id=photo.elder_id,
        event_code="photo.delete",
        metadata={"filename": photo.filename, "record_id": photo.record_id},
    )


def soft_delete_record_photos(
    record_type: str, record_id: int, *, user_id: int | None
) -> int:
    photos = photos_for(record_type, record_id)
    for photo in photos:
        soft_delete_photo(photo, user_id=user_id, reason="source record deleted")
    return len(photos)


def set_primary_med_photo(photo: Photo, *, user_id: int | None) -> None:
    if photo.kind != "med_reference" or photo.record_type != "medplan":
        raise ValueError("not a medication reference photo")
    peers = photos_for("medplan", photo.record_id, kind="med_reference")
    for peer in peers:
        peer.is_primary = peer.id == photo.id
    log_action(
        user_id,
        "update",
        "photo",
        photo.id,
        "set medication primary photo",
        elder_id=photo.elder_id,
        event_code="photo.set_primary",
    )


def migrate_legacy_photos(*, dry_run: bool = True) -> dict[str, int]:
    """Move legacy 1.1.x media into the structured CareLog directory tree.

    Each source is decoded and re-encoded as JPEG rather than merely renamed.  The
    legacy source is removed only after the database transaction has committed.
    """

    summary = {"scanned": 0, "migrated": 0, "missing": 0, "failed": 0}
    sources_to_remove: list[Path] = []
    created_outputs: list[Path] = []
    rows = active_photos_query().order_by(Photo.id).all()
    for photo in rows:
        summary["scanned"] += 1
        normalised = (photo.filename or "").replace("\\", "/")
        if normalised.startswith("elders/"):
            continue

        destination: Path | None = None
        thumb_path: Path | None = None
        try:
            source = _absolute_path(normalised)
            if not source.exists():
                summary["missing"] += 1
                continue

            uploaded_at = photo.uploaded_at or datetime.now()
            record_day = photo.record_date or uploaded_at.date()
            target_dir = _relative_directory(
                kind=photo.kind or "care_evidence",
                elder_id=photo.elder_id,
                record_type=photo.record_type,
                record_id=photo.record_id,
                record_date=record_day,
            )
            marker_prefix = {
                "med_reference": "p",
                "abnormal_followup": "a",
            }.get(photo.kind or "care_evidence", "r")
            target_name = (
                f"{photo.record_type}_{marker_prefix}{photo.record_id:06d}_"
                f"{uploaded_at:%Y%m%dT%H%M%S}_{photo.id:04d}.jpg"
            )
            relative_target = target_dir / target_name
            destination = _absolute_path(relative_target.as_posix())
            thumb_name = relative_target.with_name(relative_target.stem + "_thumb.jpg")
            thumb_path = _absolute_path(thumb_name.as_posix())

            if dry_run:
                summary["migrated"] += 1
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source) as source_image:
                image = ImageOps.exif_transpose(source_image).convert("RGB")
                stored_width, stored_height = _write_jpeg(
                    image,
                    destination,
                    max_width=int(current_app.config.get("PHOTO_MAX_WIDTH", 1280)),
                )
                _write_thumbnail(image, thumb_path)
            created_outputs.extend((destination, thumb_path))

            photo.width, photo.height = stored_width, stored_height
            photo.thumbnail_filename = thumb_name.as_posix()
            photo.filename = relative_target.as_posix()
            photo.record_date = record_day
            photo.file_size = destination.stat().st_size
            photo.mime_type = "image/jpeg"
            photo.checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
            sources_to_remove.append(source)
            summary["migrated"] += 1
        except Exception:
            summary["failed"] += 1
            for partial in (destination, thumb_path):
                try:
                    if partial and partial.exists():
                        partial.unlink()
                    if partial in created_outputs:
                        created_outputs.remove(partial)
                except OSError:
                    current_app.logger.exception(
                        "Unable to remove failed migration output %s", partial
                    )
            current_app.logger.exception("Legacy photo migration failed for %s", photo.id)

    if not dry_run:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            for output in created_outputs:
                try:
                    output.unlink(missing_ok=True)
                except OSError:
                    current_app.logger.exception(
                        "Unable to remove uncommitted migration output %s", output
                    )
            current_app.logger.exception("Legacy photo migration database commit failed")
            raise
        for source in sources_to_remove:
            try:
                source.unlink(missing_ok=True)
            except OSError:
                current_app.logger.exception(
                    "Unable to remove legacy media source %s", source
                )
    return summary
