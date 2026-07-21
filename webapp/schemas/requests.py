from pydantic import BaseModel, Field


class DrawRequest(BaseModel):
    prompt: str
    seed: int | None = None
    sampler_name: str | None = None
    scheduler: str | None = None
    steps: int | None = None
    cfg: float | None = None


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
    duration: int = Field(default=5, ge=1, le=6)
    orientation: str = "portrait"
    lora_enabled: bool = True
    lora_strength: float = Field(default=0.7, ge=0.0, le=1.0)
    seed: int | None = None
    negative_prompt: str | None = None


class ResolutionRequest(BaseModel):
    width: int = Field(ge=64, le=8192)
    height: int = Field(ge=64, le=8192)


class NegativePromptRequest(BaseModel):
    text: str


class ArtistChainRequest(BaseModel):
    text: str


class PartRequest(BaseModel):
    w: int
    h: int
    x: int = 0
    y: int = 0


class LoraAddRequest(BaseModel):
    name: str
    weight: float = Field(default=0.8, ge=0.0, le=2.0)


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


class LoraListResponse(BaseModel):
    available: dict[str, list[str]]
    active: dict[str, float]
    workflow_label: str
