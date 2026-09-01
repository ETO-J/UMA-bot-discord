import logging
from fastapi import APIRouter, HTTPException, Depends

from schemas.requests import (
    ChatSendRequest,
    ChatResponse,
    ChatHistoryItem,
    ChatEstimateRequest,
    ChatEstimateResponse,
)
from services.chat_assistant import chat_with_artist
from services.chat_history_service import chat_history
from services.chat_billing import estimate_chat_cost
from services.workflow_manager import wm
from dependencies import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/chat/send", response_model=ChatResponse)
async def send_chat(req: ChatSendRequest, user_id: str = Depends(get_current_user_id)):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Dynamic cost: estimated input tokens (text + image), capped at max.
    estimate = estimate_chat_cost(
        req.message, req.images, req.image_sizes
    )
    cost = estimate["cost"]
    user_settings = wm.get_user_settings(user_id)
    remaining = user_settings["limit_count"] - user_settings["used_today"]
    if remaining < cost:
        raise HTTPException(status_code=429, detail=f"Quota exhausted: need {cost}, have {remaining}")
    if not wm.use_quota(user_id, cost):
        raise HTTPException(status_code=429, detail="Quota check failed")

    try:
        result = await chat_with_artist(user_id, req.message, images=req.images)
        return ChatResponse(
            content=result["content"],
            prompt=result["prompt"],
            negative=result["negative"],
        )
    except Exception as e:
        wm.refund_quota(user_id, cost)
        logger.error("Chat failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/estimate", response_model=ChatEstimateResponse)
async def estimate_chat(req: ChatEstimateRequest, user_id: str = Depends(get_current_user_id)):
    est = estimate_chat_cost(req.message, image_sizes=req.image_sizes)
    user_settings = wm.get_user_settings(user_id)
    remaining = user_settings["limit_count"] - user_settings["used_today"]
    return ChatEstimateResponse(
        text_tokens=est["text_tokens"],
        image_tokens=est["image_tokens"],
        image_count=est["image_count"],
        total_tokens=est["total_tokens"],
        cost=est["cost"],
        max_cost=est["max_cost"],
        remaining=remaining,
    )


@router.get("/chat/history", response_model=list[ChatHistoryItem])
async def get_chat_history(user_id: str = Depends(get_current_user_id)):
    messages = chat_history.get_recent_messages(user_id)
    items = []
    for m in messages:
        images = None
        if m.get("content_type") == "image":
            images = chat_history.load_images_data_urls(m.get("image_paths"))
            if not images and m.get("image_path"):
                single = chat_history.load_image_data_url(m.get("image_path"))
                images = [single] if single else None
        items.append(
            ChatHistoryItem(
                role=m["role"],
                content=m["content"],
                timestamp=m["timestamp"],
                content_type=m.get("content_type") or "text",
                image=images[0] if images else None,
                images=images,
            )
        )
    return items


@router.delete("/chat/clear")
async def clear_chat(user_id: str = Depends(get_current_user_id)):
    chat_history.clear_session(user_id)
    return {"status": "ok"}
