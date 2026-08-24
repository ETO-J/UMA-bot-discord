import logging
from fastapi import APIRouter, HTTPException, Depends

from schemas.requests import ChatSendRequest, ChatResponse, ChatHistoryItem
from services.chat_assistant import chat_with_artist
from services.chat_history_service import chat_history
from services.workflow_manager import wm
from dependencies import get_current_user_id
from config import ARTIST_CHAT_COST

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/chat/send", response_model=ChatResponse)
async def send_chat(req: ChatSendRequest, user_id: str = Depends(get_current_user_id)):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    cost = ARTIST_CHAT_COST
    user_settings = wm.get_user_settings(user_id)
    remaining = user_settings["limit_count"] - user_settings["used_today"]
    if remaining < cost:
        raise HTTPException(status_code=429, detail=f"Quota exhausted: need {cost}, have {remaining}")
    if not wm.use_quota(user_id, cost):
        raise HTTPException(status_code=429, detail="Quota check failed")

    try:
        result = await chat_with_artist(user_id, req.message)
        return ChatResponse(
            content=result["content"],
            prompt=result["prompt"],
            negative=result["negative"],
        )
    except Exception as e:
        wm.refund_quota(user_id, cost)
        logger.error("Chat failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/history", response_model=list[ChatHistoryItem])
async def get_chat_history(user_id: str = Depends(get_current_user_id)):
    messages = chat_history.get_recent_messages(user_id)
    return [ChatHistoryItem(role=m["role"], content=m["content"], timestamp=m["timestamp"])
            for m in messages]


@router.delete("/chat/clear")
async def clear_chat(user_id: str = Depends(get_current_user_id)):
    chat_history.clear_session(user_id)
    return {"status": "ok"}
