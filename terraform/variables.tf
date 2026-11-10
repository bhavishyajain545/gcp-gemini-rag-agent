variable "project_id" {
  description = "GCP project that hosts the agent."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run, Artifact Registry and the runbooks bucket."
  type        = string
  default     = "us-central1"
}

variable "vertex_location" {
  description = "Vertex AI location used by the agent for Gemini calls (newer Gemini models are served from 'global')."
  type        = string
  default     = "global"
}

variable "gemini_model" {
  description = "Gemini model id used by the agent."
  type        = string
  default     = "gemini-3.8-flash"
}

variable "embedding_model" {
  description = "Vertex AI text embedding model used for runbook RAG."
  type        = string
  default     = "gemini-embedding-001"
}

variable "image" {
  description = "Full container image reference for the agent (built and pushed before terraform apply)."
  type        = string
}

variable "firestore_location" {
  description = "Firestore database location (multi-region nam5 is the default for the US)."
  type        = string
  default     = "nam5"
}
