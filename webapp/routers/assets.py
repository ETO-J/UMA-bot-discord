"""Asset-library and temporary Ref2VA upload endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from auth import is_admin_user
from dependencies import get_current_user, get_current_user_id
from schemas.requests import (
    AssetFolderRequest,
    AssetFolderResponse,
    AssetListResponse,
    AssetResponse,
    AssetUpdateRequest,
    LikeRequest,
    LikeResponse,
    PublishedUpdateRequest,
    QuotaResponse,
    TempUploadResponse,
)
from services import discord_publisher
from services.asset_library import asset_library
from services.media_store import temp_media_store

router = APIRouter(tags=["assets"])
logger = logging.getLogger(__name__)


def _parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except json.JSONDecodeError:
        pass
    return [x.strip() for x in raw.split(",") if x.strip()]


def _require_admin(user_id: str):
    if not is_admin_user(user_id):
        raise HTTPException(status_code=403, detail="需要管理员权限")


async def _announce_publish(item: dict, publisher_name: str) -> dict:
    """Post a Discord feed announcement for a freshly published item."""
    published_id = item.get("published_id") or item.get("id")
    if not published_id:
        return item
    try:
        thumb = asset_library.get_published_thumbnail_path(published_id)
        file_path = asset_library.get_published_path(published_id)
        message_id = await discord_publisher.post_publish_message(
            title=item.get("title", ""),
            description=item.get("description", ""),
            publisher_name=publisher_name,
            kind=item.get("kind", ""),
            tags=item.get("tags", []),
            file_path=file_path,
            thumb_path=thumb,
        )
        if message_id:
            asset_library.set_discord_message_id(published_id, message_id)
            item["discord_posted"] = True
        else:
            item["discord_posted"] = False if discord_publisher.feed_enabled() else None
    except Exception as exc:  # noqa: BLE001 - sync failure must not break publishing
        logger.warning("Discord feed sync failed for %s: %s", published_id, exc)
        item["discord_posted"] = False
        item["discord_error"] = str(exc)[:200]
    return item


def _media_type(path: Path, fallback: str = "application/octet-stream"):
    return mimetypes.guess_type(str(path))[0] or fallback


@router.get("/assets/quota", response_model=QuotaResponse)
async def get_asset_quota(user_id: str = Depends(get_current_user_id)):
    limit_bytes, used_bytes, enabled = asset_library.storage_quota(user_id)
    return QuotaResponse(
        limit=0,
        used=0,
        remaining=0,
        asset_limit_bytes=limit_bytes,
        asset_used_bytes=used_bytes,
        asset_remaining_bytes=max(0, limit_bytes - used_bytes),
        asset_enabled=enabled,
    )


@router.get("/assets/folders", response_model=list[AssetFolderResponse])
async def list_folders(user_id: str = Depends(get_current_user_id)):
    folders = asset_library.list_folders(user_id)
    return [
        AssetFolderResponse(
            id=folder["id"],
            name=folder["name"],
            parent_id=folder["parent_id"],
            asset_count=folder["asset_count"],
            is_root=folder.get("is_root", False),
        )
        for folder in folders
    ]


@router.post("/assets/folders", response_model=AssetFolderResponse)
async def create_folder(
    req: AssetFolderRequest,
    user_id: str = Depends(get_current_user_id),
):
    try:
        folder = asset_library.create_folder(user_id, req.name, req.parent_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return AssetFolderResponse(
        id=folder["id"],
        name=folder["name"],
        parent_id=folder["parent_id"],
        asset_count=folder["asset_count"],
        is_root=folder.get("is_root", False),
    )


@router.get("/assets/folders/{folder_id}/stats")
async def get_folder_stats(
    folder_id: str,
    user_id: str = Depends(get_current_user_id),
):
    try:
        stats = asset_library.folder_stats(user_id, folder_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if stats is None:
        raise HTTPException(status_code=404, detail="文件夹不存在或不可访问")
    return stats


@router.delete("/assets/folders/{folder_id}")
async def delete_folder(
    folder_id: str,
    confirm: bool = False,
    user_id: str = Depends(get_current_user_id),
):
    try:
        result = asset_library.delete_folder(user_id, folder_id, confirm=confirm)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="文件夹不存在或不可访问")
    if not result.get("ok") or result.get("needs_confirmation"):
        raise HTTPException(
            status_code=409,
            detail=(
                "文件夹不为空，确认后请传入 confirm=true；"
                f"素材 {result.get('asset_count', 0)} 个，子文件夹 {result.get('folder_count', 0)} 个"
            ),
        )
    return result


@router.post("/assets", response_model=AssetResponse)
async def upload_asset(
    file: UploadFile = File(...),
    title: str = Form(""),
    description: str = Form(""),
    tags: str = Form(""),
    folder_id: str = Form(""),
    subject_key: str = Form(""),
    subject_aliases: str = Form(""),
    subject_role: str = Form(""),
    user_id: str = Depends(get_current_user_id),
):
    try:
        data = await file.read()
        return await asyncio.to_thread(
            asset_library.upload,
            user_id,
            file.filename or "upload.bin",
            file.content_type or "",
            data,
            title=title,
            description=description,
            tags=_parse_tags(tags),
            folder_id=folder_id or None,
            subject_key=subject_key or None,
            subject_aliases=subject_aliases,
            subject_role=subject_role or None,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/assets", response_model=AssetListResponse)
async def list_assets(
    kind: str | None = None,
    folder_id: str | None = None,
    q: str = "",
    shared: bool = False,
    user_id: str = Depends(get_current_user_id),
):
    try:
        items = asset_library.list_assets(
            user_id,
            kind=kind,
            folder_id=folder_id,
            query=q,
            shared=shared,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    # Lazily backfill legacy publisher names (one row per missing name).
    if shared:
        for item in items:
            if not item.get("publisher_name") and item.get("publisher_id"):
                name = await discord_publisher.resolve_username(item["publisher_id"])
                if name:
                    asset_library.set_publisher_name(item["published_id"], name)
                    item["publisher_name"] = name
    limit_bytes, used_bytes, enabled = asset_library.storage_quota(user_id)
    return AssetListResponse(
        items=items,
        used_bytes=used_bytes,
        limit_bytes=limit_bytes,
        enabled=enabled,
    )


@router.get("/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
):
    item = asset_library.get_asset(user_id, asset_id)
    if not item:
        raise HTTPException(status_code=404, detail="资产不存在或不可访问")
    return item


@router.patch("/assets/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: str,
    req: AssetUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    try:
        return asset_library.update_asset(
            user_id,
            asset_id,
            title=req.title,
            description=req.description,
            tags=req.tags,
            folder_id=req.folder_id,
            subject_key=req.subject_key,
            subject_aliases=req.subject_aliases,
            subject_role=req.subject_role,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete("/assets/{asset_id}")
async def delete_asset(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
):
    if not asset_library.delete_asset(user_id, asset_id):
        raise HTTPException(status_code=404, detail="资产不存在或不可访问")
    return {"ok": True}


@router.post("/assets/{asset_id}/publish", response_model=AssetResponse)
async def publish_asset(
    asset_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    try:
        user = await get_current_user(request)
        publisher_name = (user or {}).get("username", "") or ""
        item = asset_library.publish(user_id, asset_id, publisher_name=publisher_name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    # Sync to the Discord feed channel (same bot account as the NoneBot2 process).
    return await _announce_publish(item, publisher_name)


@router.post("/assets/{asset_id}/unpublish")
async def unpublish_asset(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
):
    published = asset_library.get_published_for_source(user_id, asset_id)
    if not published:
        raise HTTPException(status_code=404, detail="该资产未发布")
    # Silently remove the correlated Discord announcement first (best effort).
    message_deleted: bool | None = None
    message_id = published.get("discord_message_id")
    if message_id:
        try:
            message_deleted = await discord_publisher.delete_publish_message(message_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Discord feed delete failed for %s: %s", published["published_id"], exc)
            message_deleted = False
        if message_deleted:
            asset_library.set_discord_message_id(published["published_id"], None)
    if not asset_library.unpublish(user_id, published["published_id"]):
        raise HTTPException(status_code=404, detail="该资产未发布")
    return {
        "ok": True,
        "discord_message_deleted": message_deleted,
    }


@router.post("/assets/public/{published_id}/like", response_model=LikeResponse)
async def like_public_asset(
    published_id: str,
    req: LikeRequest,
    user_id: str = Depends(get_current_user_id),
):
    result = asset_library.set_like(published_id, user_id, req.liked)
    if result is None:
        raise HTTPException(status_code=404, detail="公开素材不存在")
    return LikeResponse(published_id=published_id, like_count=result["like_count"], liked=result["liked"])


@router.post("/assets/public/upload", response_model=AssetResponse)
async def admin_upload_public_asset(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    description: str = Form(""),
    tags: str = Form(""),
    user_id: str = Depends(get_current_user_id),
):
    _require_admin(user_id)
    try:
        data = await file.read()
        user = await get_current_user(request)
        publisher_name = (user or {}).get("username", "") or ""
        item = await asyncio.to_thread(
            asset_library.admin_upload_public,
            user_id,
            file.filename or "upload.bin",
            file.content_type or "",
            data,
            title=title,
            description=description,
            tags=_parse_tags(tags),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _announce_publish(item, publisher_name)


@router.patch("/assets/public/{published_id}", response_model=AssetResponse)
async def admin_update_public_asset(
    published_id: str,
    req: PublishedUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    _require_admin(user_id)
    item = asset_library.admin_update_published(
        published_id,
        title=req.title,
        description=req.description,
        tags=req.tags,
    )
    if not item:
        raise HTTPException(status_code=404, detail="公开素材不存在")
    return item


@router.delete("/assets/public/{published_id}")
async def admin_remove_public_asset(
    published_id: str,
    user_id: str = Depends(get_current_user_id),
):
    _require_admin(user_id)
    row = asset_library.get_published(published_id)
    if not row:
        raise HTTPException(status_code=404, detail="公开素材不存在")
    # Silently remove the correlated Discord announcement first (best effort).
    message_deleted: bool | None = None
    message_id = row.get("discord_message_id")
    if message_id:
        try:
            message_deleted = await discord_publisher.delete_publish_message(message_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Discord feed delete failed for %s: %s", published_id, exc)
            message_deleted = False
        if message_deleted:
            asset_library.set_discord_message_id(published_id, None)
    if not asset_library.admin_remove_published(published_id):
        raise HTTPException(status_code=404, detail="公开素材不存在")
    return {"ok": True, "discord_message_deleted": message_deleted}


@router.get("/assets/{asset_id}/file")
async def get_asset_file(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
):
    try:
        path = asset_library.get_asset_path(user_id, asset_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return FileResponse(path, media_type=_media_type(path))


@router.get("/assets/{asset_id}/thumbnail")
async def get_asset_thumbnail(
    asset_id: str,
    user_id: str = Depends(get_current_user_id),
):
    path = asset_library.get_asset_thumbnail_path(user_id, asset_id)
    if path is None:
        raise HTTPException(status_code=404, detail="缩略图不存在")
    return FileResponse(path, media_type="image/webp")


@router.get("/assets/public/{published_id}/file")
async def get_published_file(
    published_id: str,
    user_id: str = Depends(get_current_user_id),
):
    path = asset_library.get_published_path(published_id)
    return FileResponse(path, media_type=_media_type(path))


@router.get("/assets/public/{published_id}/thumbnail")
async def get_published_thumbnail(
    published_id: str,
    user_id: str = Depends(get_current_user_id),
):
    path = asset_library.get_published_thumbnail_path(published_id)
    if path is None:
        raise HTTPException(status_code=404, detail="缩略图不存在")
    return FileResponse(path, media_type="image/webp")


@router.post("/assets/public/{published_id}/save", response_model=AssetResponse)
async def save_public_asset(
    published_id: str,
    folder_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await asyncio.to_thread(
            asset_library.save_published_to_private,
            user_id,
            published_id,
            folder_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/video/uploads", response_model=TempUploadResponse)
async def upload_video_reference(
    file: UploadFile = File(...),
    store_to_library: str = Form("true"),
    user_id: str = Depends(get_current_user_id),
):
    try:
        data = await file.read()
        should_store = store_to_library.strip().lower() in {"1", "true", "yes", "on"}
        if should_store:
            try:
                _, _, enabled = asset_library.storage_quota(user_id)
                if enabled:
                    asset = await asyncio.to_thread(
                        asset_library.upload,
                        user_id,
                        file.filename or "upload.bin",
                        file.content_type or "",
                        data,
                        title=Path(file.filename or "upload.bin").stem,
                        tags=["reference"],
                        subject_role="reference",
                    )
                    return TempUploadResponse(
                        id=asset["id"],
                        kind=asset["kind"],
                        size_bytes=asset["size_bytes"],
                        storage_mode="asset",
                        asset_id=asset["id"],
                        thumbnail_url=asset.get("thumbnail_url"),
                    )
            except Exception as exc:  # noqa: BLE001 - fall back to temp on quota/setup failure
                logger.warning("Store reference upload to asset library failed: %s", exc)
        temp = await asyncio.to_thread(
            temp_media_store.save,
            file.filename or "upload.bin",
            file.content_type or "",
            data,
        )
        return TempUploadResponse(
            id=temp["id"],
            kind=temp["kind"],
            size_bytes=temp["size_bytes"],
            storage_mode="temp",
            upload_id=temp["id"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
