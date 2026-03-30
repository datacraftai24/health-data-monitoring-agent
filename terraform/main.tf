# MetaboCoach GCP Infrastructure — Terraform
# Provisions Cloud SQL (PostgreSQL), Memorystore (Redis), Cloud Run, and Secret Manager

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "db_password" {
  description = "Cloud SQL database password"
  type        = string
  sensitive   = true
}

# --- Cloud SQL (PostgreSQL with TimescaleDB) ---
resource "google_sql_database_instance" "metabocoach" {
  name             = "metabocoach-db"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier              = "db-f1-micro"
    availability_type = "ZONAL"

    database_flags {
      name  = "shared_preload_libraries"
      value = "timescaledb"
    }

    backup_configuration {
      enabled    = true
      start_time = "03:00"
    }

    ip_configuration {
      ipv4_enabled = true
    }
  }

  deletion_protection = true
}

resource "google_sql_database" "metabocoach" {
  name     = "metabocoach"
  instance = google_sql_database_instance.metabocoach.name
}

resource "google_sql_user" "metabocoach" {
  name     = "metabocoach"
  instance = google_sql_database_instance.metabocoach.name
  password = var.db_password
}

# --- Memorystore (Redis) ---
resource "google_redis_instance" "metabocoach" {
  name           = "metabocoach-redis"
  tier           = "BASIC"
  memory_size_gb = 1
  region         = var.region
  redis_version  = "REDIS_7_0"
}

# --- Cloud Storage (Food Photos) ---
resource "google_storage_bucket" "photos" {
  name     = "${var.project_id}-metabocoach-photos"
  location = var.region

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type = "Delete"
    }
  }
}

# --- Secret Manager ---
resource "google_secret_manager_secret" "gemini_key" {
  secret_id = "metabocoach-gemini-key"
  replication { auto {} }
}

resource "google_secret_manager_secret" "telegram_token" {
  secret_id = "metabocoach-telegram-token"
  replication { auto {} }
}

resource "google_secret_manager_secret" "db_url" {
  secret_id = "metabocoach-db-url"
  replication { auto {} }
}

resource "google_secret_manager_secret" "db_url_sync" {
  secret_id = "metabocoach-db-url-sync"
  replication { auto {} }
}

resource "google_secret_manager_secret" "redis_url" {
  secret_id = "metabocoach-redis-url"
  replication { auto {} }
}

resource "google_secret_manager_secret" "libre_email" {
  secret_id = "metabocoach-libre-email"
  replication { auto {} }
}

resource "google_secret_manager_secret" "libre_password" {
  secret_id = "metabocoach-libre-password"
  replication { auto {} }
}

resource "google_secret_manager_secret" "libre_region" {
  secret_id = "metabocoach-libre-region"
  replication { auto {} }
}

resource "google_secret_manager_secret" "twilio_sid" {
  secret_id = "metabocoach-twilio-sid"
  replication { auto {} }
}

resource "google_secret_manager_secret" "twilio_token" {
  secret_id = "metabocoach-twilio-token"
  replication { auto {} }
}

# --- Shared locals ---
locals {
  db_url_async = "postgresql+asyncpg://metabocoach:${var.db_password}@/${google_sql_database.metabocoach.name}?host=/cloudsql/${google_sql_database_instance.metabocoach.connection_name}"
  redis_url    = "redis://${google_redis_instance.metabocoach.host}:${google_redis_instance.metabocoach.port}"
  image        = "gcr.io/${var.project_id}/metabocoach:latest"
  cloud_sql    = [google_sql_database_instance.metabocoach.connection_name]
}

# --- Cloud Run: API Service ---
resource "google_cloud_run_v2_service" "metabocoach_api" {
  name     = "metabocoach-api"
  location = var.region

  template {
    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }

    containers {
      image = local.image

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env { name = "APP_ENV"; value = "production" }
      env { name = "DATABASE_URL"; value = local.db_url_async }
      env { name = "REDIS_URL"; value = local.redis_url }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = local.cloud_sql
      }
    }
  }
}

# --- Cloud Run: Celery Worker ---
resource "google_cloud_run_v2_service" "metabocoach_worker" {
  name     = "metabocoach-worker"
  location = var.region

  template {
    scaling {
      min_instance_count = 1
      max_instance_count = 3
    }

    containers {
      image   = local.image
      command = ["/app/scripts/start_worker.sh"]

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      env { name = "APP_ENV"; value = "production" }
      env { name = "DATABASE_URL"; value = local.db_url_async }
      env { name = "REDIS_URL"; value = local.redis_url }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = local.cloud_sql
      }
    }
  }
}

# --- Cloud Run: Celery Beat (singleton) ---
resource "google_cloud_run_v2_service" "metabocoach_beat" {
  name     = "metabocoach-beat"
  location = var.region

  template {
    scaling {
      min_instance_count = 1
      max_instance_count = 1
    }

    containers {
      image   = local.image
      command = ["/app/scripts/start_beat.sh"]

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "0.5"
          memory = "256Mi"
        }
      }

      env { name = "APP_ENV"; value = "production" }
      env { name = "DATABASE_URL"; value = local.db_url_async }
      env { name = "REDIS_URL"; value = local.redis_url }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = local.cloud_sql
      }
    }
  }
}

# Allow unauthenticated access to API (for webhooks)
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.metabocoach_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# --- Outputs ---
output "api_url" {
  value = google_cloud_run_v2_service.metabocoach_api.uri
}

output "worker_url" {
  value = google_cloud_run_v2_service.metabocoach_worker.uri
}

output "beat_url" {
  value = google_cloud_run_v2_service.metabocoach_beat.uri
}

output "db_connection_name" {
  value = google_sql_database_instance.metabocoach.connection_name
}

output "redis_host" {
  value = google_redis_instance.metabocoach.host
}

output "photos_bucket" {
  value = google_storage_bucket.photos.name
}
