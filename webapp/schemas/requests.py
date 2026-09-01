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
    start_image: str
    end_image: str | None = None
    quality: str = "480p"
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


class QuotaResponse(BaseModel):
    limit: int
    used: int
    remaining: int


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
