locals {
  services = [
    "aiplatform.googleapis.com",
    "run.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
  ]
  runbook_files = fileset("${path.module}/../runbooks", "*.md")
}

resource "google_project_service" "apis" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------------------
# Identity: one dedicated service account for the agent, least privilege.
# ---------------------------------------------------------------------------
resource "google_service_account" "agent" {
  account_id   = "sa-ops-agent"
  display_name = "Ops agent (Cloud Run runtime identity)"
  depends_on   = [google_project_service.apis]
}

# Project-level roles the agent needs: call Gemini/embeddings and use Firestore.
resource "google_project_iam_member" "agent_roles" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/datastore.user",
  ])
  project = var.project_id
  role    = each.value
  member  = google_service_account.agent.member
}

# Build identity used by `gcloud builds submit` (default Cloud Build SA has no
# roles in new organizations).
resource "google_service_account" "build" {
  account_id   = "sa-build"
  display_name = "Cloud Build (image build + push)"
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "build_roles" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/artifactregistry.writer",
    "roles/storage.objectViewer", # read the uploaded source tarball
  ])
  project = var.project_id
  role    = each.value
  member  = google_service_account.build.member
}

# ---------------------------------------------------------------------------
# Runbooks: private bucket, uniform access, no public access, read-only for the agent.
# ---------------------------------------------------------------------------
resource "google_storage_bucket" "runbooks" {
  name                        = "${var.project_id}-runbooks"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true
  depends_on                  = [google_project_service.apis]
}

resource "google_storage_bucket_object" "runbooks" {
  for_each     = local.runbook_files
  bucket       = google_storage_bucket.runbooks.name
  name         = "runbooks/${each.value}"
  source       = "${path.module}/../runbooks/${each.value}"
  content_type = "text/markdown"
}

resource "google_storage_bucket_iam_member" "agent_reads_runbooks" {
  bucket = google_storage_bucket.runbooks.name
  role   = "roles/storage.objectViewer"
  member = google_service_account.agent.member
}

# ---------------------------------------------------------------------------
# Firestore (native mode) for tickets.
# ---------------------------------------------------------------------------
resource "google_firestore_database" "default" {
  name            = "(default)"
  location_id     = var.firestore_location
  type            = "FIRESTORE_NATIVE"
  deletion_policy = "DELETE"
  depends_on      = [google_project_service.apis]
}

# Composite index used by list_open_tickets (status == open, order by created_at desc).
resource "google_firestore_index" "tickets_open_by_created" {
  database   = google_firestore_database.default.name
  collection = "tickets"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }
  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }
}

# ---------------------------------------------------------------------------
# Artifact Registry for the agent image.
# ---------------------------------------------------------------------------
resource "google_artifact_registry_repository" "agents" {
  repository_id = "agents"
  location      = var.region
  format        = "DOCKER"
  description   = "Container images for ADK agents"
  depends_on    = [google_project_service.apis]
}

# ---------------------------------------------------------------------------
# Cloud Run: private service (no allUsers invoker), scale to zero.
# ---------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "agent" {
  name                = "ops-agent"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.agent.email

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = var.image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle = true
      }

      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "TRUE"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.vertex_location
      }
      env {
        name  = "GEMINI_MODEL"
        value = var.gemini_model
      }
      env {
        name  = "EMBEDDING_MODEL"
        value = var.embedding_model
      }
      env {
        name  = "RUNBOOKS_BUCKET"
        value = google_storage_bucket.runbooks.name
      }
      env {
        name  = "FIRESTORE_DATABASE"
        value = google_firestore_database.default.name
      }

      startup_probe {
        http_get {
          path = "/dev-ui/"
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 12
      }
    }
  }

  depends_on = [
    google_project_iam_member.agent_roles,
    google_storage_bucket_iam_member.agent_reads_runbooks,
    google_firestore_index.tickets_open_by_created,
  ]
}
