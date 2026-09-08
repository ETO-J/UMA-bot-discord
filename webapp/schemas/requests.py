from typing import Literal

from pydantic import BaseModel, Field


class DrawRequest(BaseModel):
    prompt: str
    seed: int | None = None
    sampler_name: str | None = None
    scheduler: str | None = None
    steps: int | None = None
    cfg: float | None = None
    hd_mode: bool = False


class DiffDrawRequest(BaseModel):
    prompt: str
    image: str  # base64-encoded source image (required for img2img / diff)
    denoise: float | None = Field(default=None, ge=0.0, le=1.0)
    seed: int | None = None
    sampler_name: str | None = None
    scheduler: str | None = None
    steps: int | None = None
    cfg: float | None = None
    hd_mode: bool = False


class MultidrawRequest(BaseModel):
    prompt1: str
    prompt2: str
    global_prompt: str
    seed: int | None = None
    sampler_name: str | None = None
    scheduler: str | None = None
    steps: int | None = None
    cfg: float | None = None


class VideoRequest(BaseModel):
    prompt: str
    start_image: str | None = None
    end_image: str | None = None
    video_mode: Literal["fl2va", "ref2va"] = "fl2va"
    reference_image_uploads: list[str] | None = None
    reference_video_uploads: list[str] | None = None
    reference_audio_uploads: list[str] | None = None
    reference_image_asset_ids: list[str] | None = None
    reference_video_asset_ids: list[str] | None = None
    reference_audio_asset_ids: list[str] | None = None
    output_last_frame: bool = False
    quality: str = "480p"
    aspect_ratio: str | None = None
    duration: int = Field(default=5, ge=1, le=15)
    orientation: str = "portrait"
    seed: int | None = None


class ResolutionRequest(BaseModel):
    width: int = Field(ge=64, le=8192)
    height: int = Field(ge=64, le=8192)


class NegativePromptRequest(BaseModel):
    text: str


class HdModeRequest(BaseModel):
    enabled: bool


class ArtistChainRequest(BaseModel):
    text: str


class PartRequest(BaseModel):
    w: int
    h: int
    x: int = 0
    y: int = 0


class Flux2EditRequest(BaseModel):
    prompt: str
    source_image: str  # base64, required
    reference_image: str | None = None  # base64, optional
    negative_prompt: str | None = None
    seed: int | None = None
    steps: int | None = None
    cfg: float | None = None
    sampler_name: str | None = None
    # edit (default) | edit_cutout (Flux2 edit + BiRefNet cutout) | cutout (direct cutout without Flux2)
    mode: Literal["edit", "edit_cutout", "cutout"] = "edit"


class ChatSendRequest(BaseModel):
    message: str
    images: list[str] | None = None  # base64 data URLs of reference images
    image_sizes: list[list[int]] | None = None  # [[w, h], ...] aligned with images


class ChatResponse(BaseModel):
    content: str
    prompt: str | None = None
    negative: str | None = None


class ChatHistoryItem(BaseModel):
    role: str
    content: str
    timestamp: float
    content_type: str = "text"
    image: str | None = None  # data URL, only present for image messages
    images: list[str] | None = None  # all image data URLs for a message


class ChatEstimateRequest(BaseModel):
    message: str
    image_sizes: list[list[int]] | None = None


class ChatEstimateResponse(BaseModel):
    text_tokens: int
    image_tokens: int
    image_count: int = 0
    total_tokens: int
    cost: int
    max_cost: int
    remaining: int | None = None


class LoraAddRequest(BaseModel):
    name: str
    weight: float = Field(default=0.8, ge=0.0, le=2.0)
    workflow: str | None = None


class LoraRemoveRequest(BaseModel):
    name: str


class TaskResponse(BaseModel):
    task_id: str
    status: str
    prompt: str
    created_at: float
    error: str | None = None
    has_image: bool = False
    prompt1: str | None = None
    prompt2: str | None = None
    global_prompt: str | None = None
    seed: int | None = None
    sampler_name: str | None = None
    scheduler: str | None = None
    steps: int | None = None
    cfg: float | None = None
    output_type: str = "image"
    queue_position: int | None = None
    queue_total: int | None = None
    estimated_seconds: float | None = None
    elapsed_seconds: float | None = None
    is_running: bool | None = None
    has_last_frame: bool = False
    video_mode: str | None = None
    reference_ids: dict | None = None
    params: dict | None = None


class QuotaResponse(BaseModel):
    limit: int
    used: int
    remaining: int
    asset_limit_bytes: int = 0
    asset_used_bytes: int = 0
    asset_remaining_bytes: int = 0
    asset_enabled: bool = False
    is_admin: bool = False


class PublishedUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None


class SettingsResponse(BaseModel):
    resolution: tuple[int, int]
    workflow: str
    negative_prompt: str
    artist_chain: str
    active_loras: dict[str, float]
    part1: list[int]
    part2: list[int]
    is_hd_mode: bool = False


class LoraListResponse(BaseModel):
    available: dict[str, list[str]]
    active: dict[str, float]
    workflow_label: str
    thumb_urls: dict[str, str | None] = {}


class TempUploadResponse(BaseModel):
    id: str
    kind: str
    size_bytes: int
    storage_mode: str = "temp"
    asset_id: str | None = None
    upload_id: str | None = None
    thumbnail_url: str | None = None


class AssetFolderRequest(BaseModel):
    name: str
    parent_id: str | None = None


class AssetFolderResponse(BaseModel):
    id: str
    name: str
    parent_id: str | None = None
    asset_count: int = 0
    is_root: bool = False


class AssetResponse(BaseModel):
    id: str
    kind: str
    title: str
    description: str = ""
    tags: list[str] = []
    folder_id: str | None = None
    visibility: str = "private"
    mime_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    subject_key: str | None = None
    subject_role: str | None = None
    created_at: float
    updated_at: float
    file_url: str
    thumbnail_url: str | None = None
    published_id: str | None = None
    # Published (public library) extras.
    publisher_id: str | None = None
    publisher_name: str = ""
    discord_message_id: str | None = None
    like_count: int = 0
    liked_by_me: bool = False
    discord_posted: bool | None = None
    discord_error: str | None = None


class LikeRequest(BaseModel):
    liked: bool = True


class LikeResponse(BaseModel):
    published_id: str
    like_count: int
    liked: bool


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    used_bytes: int
    limit_bytes: int
    enabled: bool


class AssetUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    folder_id: str | None = None
    visibility: Literal["private", "shared"] | None = None
    subject_key: str | None = None
    subject_aliases: str | None = None
    subject_role: str | None = None
