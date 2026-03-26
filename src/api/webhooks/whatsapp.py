"""WhatsApp webhook handler (Twilio)."""

import logging

import httpx
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.conversation import conversation_engine
from src.ingestion.food import process_food_photo, process_food_text
from src.messaging.whatsapp_client import whatsapp_client
from src.models.base import get_db
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle incoming WhatsApp messages via Twilio webhook."""
    form = await request.form()

    from_number = form.get("From", "")  # whatsapp:+1234567890
    body = form.get("Body", "").strip()
    num_media = int(form.get("NumMedia", 0))

    # Look up user
    phone = from_number.replace("whatsapp:", "")
    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()

    if not user:
        logger.warning("Unknown WhatsApp user: %s", from_number)
        return Response(status_code=200)

    # Handle STOP command
    if body.upper() in ("STOP", "PAUSE"):
        from src.messaging.throttler import throttler

        await throttler.pause_for_user(str(user.id), hours=2)
        await whatsapp_client.send_message(from_number, "Notifications paused for 2 hours.")
        return Response(status_code=200)

    try:
        if num_media > 0:
            # Photo received — process as food
            media_url = form.get("MediaUrl0", "")
            async with httpx.AsyncClient() as client:
                media_response = await client.get(media_url)
                photo_bytes = media_response.content

            analysis = await process_food_photo(
                photo_bytes=photo_bytes,
                user=user,
                caption=body,
            )
            response_text = _format_meal_response(analysis)
        elif body:
            # Check if this looks like food logging
            food_keywords = ["had", "ate", "eating", "having", "lunch", "dinner", "breakfast", "snack"]
            is_food = any(kw in body.lower() for kw in food_keywords)

            if is_food:
                analysis = await process_food_text(text=body, user=user)
                response_text = _format_meal_response(analysis)
            else:
                response_text = await conversation_engine.respond(
                    user_message=body,
                    user_context={"name": user.name, "hba1c": user.hba1c},
                )
        else:
            return Response(status_code=200)

        await whatsapp_client.send_message(from_number, response_text)
    except Exception:
        logger.exception("Error processing WhatsApp message from %s", from_number)
        await whatsapp_client.send_message(
            from_number, "Sorry, I had trouble processing that. Please try again."
        )

    return Response(status_code=200)


def _format_meal_response(analysis) -> str:
    """Format meal analysis into a WhatsApp-friendly message."""
    items_text = ", ".join(item.name for item in analysis.items) if analysis.items else "your meal"

    lines = [
        f"I see: {items_text}",
        f"📊 Estimated: ~{analysis.total_calories} cal | "
        f"{analysis.total_protein_g:.0f}g protein | {analysis.total_carbs_g:.0f}g carbs",
    ]

    if analysis.predicted_spike > 2.0:
        lines.append(f"⚠️ Predicted spike: +{analysis.predicted_spike:.1f} mmol/L")

    if analysis.crash_risk in ("medium", "high"):
        lines.append(f"⚡ Crash risk: {analysis.crash_risk}")

    if analysis.recommendation:
        lines.append(f"💡 {analysis.recommendation}")

    return "\n".join(lines)
