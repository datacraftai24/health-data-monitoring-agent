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
    tier              = "db-f1-micro" # Start small, scale later
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
      age = 365 # Delete photos after 1 year
    }
    action {
      type = "Delete"
    }
  }
}

# --- Secret Manager ---
resource "google_secret_manager_secret" "gemini_key" {
  secret_id = "metabocoach-gemini-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "twilio_sid" {
  secret_id = "metabocoach-twilio-sid"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "twilio_token" {
  secret_id = "metabocoach-twilio-token"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "telegram_token" {
  secret_id = "metabocoach-telegram-token"
  replication {
    auto {}
  }
}

# --- Cloud Run Service ---
resource "google_cloud_run_v2_service" "metabocoach" {
  name     = "metabocoach-api"
  location = var.region

  template {
    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }

    containers {
      image = "gcr.io/${var.project_id}/metabocoach:latest"

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "APP_ENV"
        value = "production"
      }

      env {
        name  = "DATABASE_URL"
        value = "postgresql+asyncpg://metabocoach:${var.db_password}@/${google_sql_database.metabocoach.name}?host=/cloudsql/${google_sql_database_instance.metabocoach.connection_name}"
      }

      env {
        name  = "REDIS_URL"
        value = "redis://${google_redis_instance.metabocoach.host}:${google_redis_instance.metabocoach.port}"
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.metabocoach.connection_name]
      }
    }
  }
}

# Allow unauthenticated access (for webhooks)
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.metabocoach.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# --- Outputs ---
output "cloud_run_url" {
  value = google_cloud_run_v2_service.metabocoach.uri
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
