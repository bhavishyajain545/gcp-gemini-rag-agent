output "service_url" {
  description = "Cloud Run URL (private: open it with `gcloud run services proxy ops-agent --region <region>`)."
  value       = google_cloud_run_v2_service.agent.uri
}

output "service_account" {
  value = google_service_account.agent.email
}

output "build_service_account" {
  value = google_service_account.build.email
}

output "runbooks_bucket" {
  value = google_storage_bucket.runbooks.name
}

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.agents.repository_id}"
}
