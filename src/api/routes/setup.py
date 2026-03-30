"""Setup wizard API — test connections and save credentials for each integration."""

import logging
import os
from pathlib import Path

import httpx
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


# --- Pydantic models for each integration ---

class GeminiCreds(BaseModel):
    api_key: str


class LibreCreds(BaseModel):
    email: str
    password: str
    region: str = "us"


class TelegramCreds(BaseModel):
    bot_token: str


class GarminCreds(BaseModel):
    consumer_key: str
    consumer_secret: str


class TwilioCreds(BaseModel):
    account_sid: str
    auth_token: str
    whatsapp_from: str = "whatsapp:+14155238886"


# --- Helpers ---

def _read_env() -> dict[str, str]:
    """Read current .env file into a dict."""
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env


def _write_env(updates: dict[str, str]):
    """Update .env file, preserving comments and order."""
    if not ENV_PATH.exists():
        # Bootstrap from .env.example
        example = ENV_PATH.parent / ".env.example"
        if example.exists():
            ENV_PATH.write_text(example.read_text())
        else:
            ENV_PATH.write_text("")

    lines = ENV_PATH.read_text().splitlines()
    updated_keys = set()
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # Append any keys not already in file
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n")


def _mask(value: str) -> str:
    """Mask a credential for display."""
    if not value or value.startswith("your-"):
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


# --- Status endpoint ---

@router.get("/status")
async def get_status():
    """Return connection status for all integrations."""
    return {
        "database": {
            "configured": bool(settings.database_url),
            "url_display": settings.database_url.split("@")[-1] if "@" in settings.database_url else "localhost",
        },
        "redis": {
            "configured": bool(settings.redis_url),
            "url_display": settings.redis_url,
        },
        "gemini": {
            "configured": bool(settings.gemini_api_key and settings.gemini_api_key != "your-gemini-api-key"),
            "key_display": _mask(settings.gemini_api_key),
            "model": settings.gemini_model,
        },
        "libre": {
            "configured": bool(settings.libre_email and settings.libre_email != "your-libreview-email"),
            "email_display": _mask(settings.libre_email),
            "region": settings.libre_region,
        },
        "telegram": {
            "configured": bool(
                settings.telegram_bot_token and settings.telegram_bot_token != "your-telegram-bot-token"
            ),
            "token_display": _mask(settings.telegram_bot_token),
        },
        "garmin": {
            "configured": bool(
                settings.garmin_consumer_key and settings.garmin_consumer_key != "your-garmin-consumer-key"
            ),
            "key_display": _mask(settings.garmin_consumer_key),
        },
        "twilio": {
            "configured": bool(
                settings.twilio_account_sid and settings.twilio_account_sid != "your-twilio-account-sid"
            ),
            "sid_display": _mask(settings.twilio_account_sid),
        },
    }


# --- Test & Save endpoints ---

@router.post("/test/database")
async def test_database():
    """Test PostgreSQL + TimescaleDB connection."""
    try:
        from sqlalchemy import text
        from src.models.base import engine
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            row = result.scalar()
            # Check TimescaleDB
            try:
                ts = await conn.execute(text("SELECT extversion FROM pg_extension WHERE extname='timescaledb'"))
                ts_version = ts.scalar()
            except Exception:
                ts_version = None
        return {
            "success": True,
            "message": f"Connected to PostgreSQL. TimescaleDB: {ts_version or 'not installed'}",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/test/redis")
async def test_redis():
    """Test Redis connection."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url)
        pong = await r.ping()
        info = await r.info("server")
        await r.aclose()
        return {
            "success": True,
            "message": f"Connected to Redis {info.get('redis_version', 'unknown')}",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/test/gemini")
async def test_gemini(creds: GeminiCreds):
    """Test Gemini API key by listing models."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": creds.api_key},
                timeout=10,
            )
            response.raise_for_status()
            models = response.json().get("models", [])
            model_names = [m["name"] for m in models[:5]]
            return {
                "success": True,
                "message": f"Valid API key. {len(models)} models available.",
                "models": model_names,
            }
    except httpx.HTTPStatusError as e:
        return {"success": False, "message": f"API error {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/save/gemini")
async def save_gemini(creds: GeminiCreds):
    """Save Gemini API key to .env."""
    _write_env({"GEMINI_API_KEY": creds.api_key})
    settings.gemini_api_key = creds.api_key
    return {"success": True, "message": "Gemini API key saved."}


@router.post("/test/libre")
async def test_libre(creds: LibreCreds):
    """Test LibreLinkUp credentials."""
    try:
        from src.ingestion.libre import LibreLinkUpClient, REGION_MAP
        client = LibreLinkUpClient()
        client._base_url = REGION_MAP.get(creds.region, REGION_MAP["us"])

        token = await client.authenticate(email=creds.email, password=creds.password)
        connections = await client.get_connections(token)
        if connections:
            patient_names = [c.get("firstName", "Unknown") for c in connections]
            return {
                "success": True,
                "message": f"Authenticated! Found {len(connections)} patient(s): {', '.join(patient_names)}",
                "patients": [
                    {"id": c.get("patientId"), "name": f"{c.get('firstName', '')} {c.get('lastName', '')}"}
                    for c in connections
                ],
            }
        return {
            "success": True,
            "message": "Authenticated! No patient connections found yet — set up sharing in the LibreLinkUp app.",
        }
    except httpx.HTTPStatusError as e:
        return {"success": False, "message": f"Auth failed ({e.response.status_code}): Check email/password/region"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/save/libre")
async def save_libre(creds: LibreCreds):
    """Save LibreLinkUp credentials to .env."""
    _write_env({
        "LIBRE_EMAIL": creds.email,
        "LIBRE_PASSWORD": creds.password,
        "LIBRE_REGION": creds.region,
    })
    settings.libre_email = creds.email
    settings.libre_password = creds.password
    settings.libre_region = creds.region
    return {"success": True, "message": "LibreLinkUp credentials saved."}


@router.post("/test/telegram")
async def test_telegram(creds: TelegramCreds):
    """Test Telegram bot token by calling getMe."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.telegram.org/bot{creds.bot_token}/getMe",
                timeout=10,
            )
            response.raise_for_status()
            bot = response.json().get("result", {})
            return {
                "success": True,
                "message": f"Connected! Bot: @{bot.get('username', 'unknown')} ({bot.get('first_name', '')})",
                "bot": bot,
            }
    except httpx.HTTPStatusError as e:
        return {"success": False, "message": f"Invalid token ({e.response.status_code})"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/save/telegram")
async def save_telegram(creds: TelegramCreds):
    """Save Telegram bot token to .env."""
    _write_env({"TELEGRAM_BOT_TOKEN": creds.bot_token})
    settings.telegram_bot_token = creds.bot_token
    return {"success": True, "message": "Telegram bot token saved."}


@router.post("/test/garmin")
async def test_garmin(creds: GarminCreds):
    """Validate Garmin OAuth credentials format (actual OAuth requires redirect flow)."""
    if len(creds.consumer_key) < 10 or len(creds.consumer_secret) < 10:
        return {"success": False, "message": "Consumer key/secret look too short. Check your Garmin developer portal."}
    return {
        "success": True,
        "message": "Credentials format valid. Full OAuth validation happens during the Garmin connect flow.",
    }


@router.post("/save/garmin")
async def save_garmin(creds: GarminCreds):
    """Save Garmin credentials to .env."""
    _write_env({
        "GARMIN_CONSUMER_KEY": creds.consumer_key,
        "GARMIN_CONSUMER_SECRET": creds.consumer_secret,
    })
    settings.garmin_consumer_key = creds.consumer_key
    settings.garmin_consumer_secret = creds.consumer_secret
    return {"success": True, "message": "Garmin credentials saved."}


@router.post("/test/twilio")
async def test_twilio(creds: TwilioCreds):
    """Test Twilio credentials by fetching account info."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{creds.account_sid}.json",
                auth=(creds.account_sid, creds.auth_token),
                timeout=10,
            )
            response.raise_for_status()
            account = response.json()
            return {
                "success": True,
                "message": f"Connected! Account: {account.get('friendly_name', 'Unknown')} ({account.get('status', '')})",
            }
    except httpx.HTTPStatusError as e:
        return {"success": False, "message": f"Auth failed ({e.response.status_code}): Check SID/token"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/save/twilio")
async def save_twilio(creds: TwilioCreds):
    """Save Twilio credentials to .env."""
    _write_env({
        "TWILIO_ACCOUNT_SID": creds.account_sid,
        "TWILIO_AUTH_TOKEN": creds.auth_token,
        "TWILIO_WHATSAPP_FROM": creds.whatsapp_from,
    })
    settings.twilio_account_sid = creds.account_sid
    settings.twilio_auth_token = creds.auth_token
    settings.twilio_whatsapp_from = creds.whatsapp_from
    return {"success": True, "message": "Twilio credentials saved."}


# --- Seed user ---

class SeedUser(BaseModel):
    name: str
    telegram_chat_id: int
    libre_patient_id: str = ""


@router.post("/seed-user")
async def seed_user(data: SeedUser):
    """Create a user in the database for initial setup."""
    try:
        from sqlalchemy import select as sa_select
        from src.models.base import async_session
        from src.models.user import User

        async with async_session() as db:
            result = await db.execute(
                sa_select(User).where(User.telegram_chat_id == data.telegram_chat_id)
            )
            existing = result.scalar_one_or_none()
            if existing:
                return {"success": True, "message": f"User already exists: {existing.id}"}

            user = User(
                name=data.name,
                telegram_chat_id=data.telegram_chat_id,
                libre_patient_id=data.libre_patient_id or None,
                preferred_channel="telegram",
                timezone="America/Toronto",
                glucose_low_threshold=3.9,
                glucose_high_threshold=10.0,
                glucose_target_low=3.9,
                glucose_target_high=9.0,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            return {"success": True, "message": f"User created: {user.id}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# --- Serve the setup wizard UI ---

@router.get("", response_class=HTMLResponse)
async def setup_wizard():
    """Serve the setup wizard HTML page."""
    html_path = Path(__file__).resolve().parents[2] / "static" / "setup.html"
    return HTMLResponse(content=html_path.read_text(), status_code=200)
