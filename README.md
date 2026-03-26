# MetaboCoach — Personal Metabolic AI Agent

A personal AI health agent that continuously monitors glucose (FreeStyle Libre 2), activity (Garmin), and food intake (via photo uploads through WhatsApp/Telegram), learns individual metabolic patterns, and sends pre-emptive recommendations to prevent glucose crashes and optimize weight loss.

**Core Principle:** No new app. The user interacts through messaging platforms they already use.

## Architecture

```
User (WhatsApp / Telegram)
        │
        ▼
  FastAPI Gateway (Cloud Run)
        │
  ┌─────┼─────────────┐
  ▼     ▼             ▼
Ingest  AI Engine    Alert Engine
(Libre, (Gemini,     (Rules,
Garmin, Pattern      Throttler,
Food)   Detection)   Dispatcher)
  │     │             │
  ▼     ▼             ▼
  PostgreSQL + TimescaleDB (Cloud SQL)
  Redis (Memorystore)
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Runtime | Python 3.12 + FastAPI |
| Database | PostgreSQL + TimescaleDB (Cloud SQL) |
| Cache | Redis (Memorystore) |
| Task Queue | Celery + Redis |
| AI/LLM | Google Gemini (gemini-2.5-flash) |
| Vision | Gemini Vision API |
| Messaging | WhatsApp (Twilio) + Telegram Bot API |
| Hosting | Google Cloud Platform (Cloud Run) |
| IaC | Terraform |
| CI/CD | Cloud Build |

## Features

- **Real-time glucose monitoring** — Polls FreeStyle Libre 2 via LibreLinkUp API every 5 minutes
- **Food photo analysis** — Send a photo of your meal via WhatsApp/Telegram for instant nutritional breakdown
- **Pre-emptive crash alerts** — Warns before glucose crashes happen based on trends and patterns
- **Post-meal walk nudges** — Suggests walking when glucose is spiking after a meal
- **Activity integration** — Garmin Connect push API for steps, workouts, sleep, and stress
- **Personal metabolic profile** — Learns your individual food responses over 14+ days
- **Daily & weekly reports** — Automated summaries with AI-generated insights
- **Message throttling** — Max 8 messages/day to prevent notification fatigue

## Project Structure

```
metabocoach/
├── src/
│   ├── main.py                  # FastAPI entry point
│   ├── config.py                # Settings (env vars)
│   ├── api/
│   │   ├── webhooks/            # WhatsApp, Telegram, Garmin webhooks
│   │   └── routes/              # Health check, dashboard API
│   ├── ingestion/               # LibreLinkUp, Garmin, Food processors
│   ├── ai/                      # Gemini food analyzer, conversation, patterns
│   ├── engine/                  # Rules, alerts, metabolic profile, calorie tracker
│   ├── messaging/               # WhatsApp, Telegram, dispatcher, throttler
│   ├── models/                  # SQLAlchemy models (TimescaleDB)
│   ├── tasks/                   # Celery tasks (polling, reports, analysis)
│   └── utils/                   # Glucose math, nutrition DB, formatters
├── tests/                       # Pytest test suite
├── migrations/                  # Alembic DB migrations
├── scripts/                     # Setup scripts (Libre, Garmin, food DB)
├── terraform/                   # GCP infrastructure (Terraform)
├── docker-compose.yml           # Local development
├── Dockerfile
├── cloudbuild.yaml              # GCP Cloud Build CI/CD
└── app.yaml                     # App Engine config (alternative)
```

## Quick Start

### Prerequisites

- Python 3.12+
- Docker & Docker Compose (for local development)
- GCP account (for deployment)
- LibreLinkUp account (FreeStyle Libre 2 sharing)
- Twilio account (WhatsApp Business API)
- Telegram bot token
- Google Gemini API key

### Local Development

```bash
# Clone and setup
cp .env.example .env
# Edit .env with your API keys

# Start services (PostgreSQL + TimescaleDB, Redis)
docker-compose up -d db redis

# Install dependencies
pip install -e ".[dev]"

# Run database migrations
alembic upgrade head

# Setup LibreLinkUp
python -m scripts.setup_libre

# Start the app
uvicorn src.main:app --reload

# In another terminal, start Celery worker
celery -A src.tasks.celery_app worker --loglevel=info

# In another terminal, start Celery beat (scheduled tasks)
celery -A src.tasks.celery_app beat --loglevel=info
```

### Run Tests

```bash
pytest tests/ -v
```

### Deploy to GCP

```bash
# Provision infrastructure
cd terraform
terraform init
terraform apply -var="project_id=your-project" -var="db_password=your-password"

# Deploy via Cloud Build
gcloud builds submit --config=cloudbuild.yaml

# Or deploy to Cloud Run directly
gcloud run deploy metabocoach-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated
```

## Configuration

All configuration is via environment variables. See `.env.example` for the full list.

Key variables:
- `GEMINI_API_KEY` — Google Gemini API key for food analysis and conversation
- `LIBRE_EMAIL` / `LIBRE_PASSWORD` — LibreLinkUp credentials
- `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` — WhatsApp messaging
- `TELEGRAM_BOT_TOKEN` — Telegram bot
- `DATABASE_URL` — PostgreSQL + TimescaleDB connection string
- `REDIS_URL` — Redis for caching and task queue

## How It Works

1. **Glucose Monitoring**: Celery polls LibreLinkUp every 5 min, stores readings in TimescaleDB
2. **Food Logging**: User sends photo/text via WhatsApp → Gemini Vision analyzes → stores meal with macros
3. **Pattern Detection**: Nightly job correlates glucose ↔ food ↔ activity data to build personal metabolic profile
4. **Alert Engine**: Every glucose reading triggers rule evaluation → pre-emptive alerts sent via messaging
5. **Reports**: Daily summary at 9 PM, weekly report on Sundays — both with AI-generated insights

## Estimated Monthly Costs (GCP)

| Service | Cost |
|---------|------|
| Cloud Run | $15-30 |
| Cloud SQL (PostgreSQL) | $15-30 |
| Memorystore (Redis) | $15 |
| Gemini API | $20-40 |
| Twilio WhatsApp | $15-20 |
| Cloud Storage | $5 |
| **Total** | **~$85-140/month** |
