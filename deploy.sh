#!/usr/bin/env bash
# End-to-end deploy: infra (minus Cloud Run) -> image build -> Cloud Run.
# Terraform owns everything; the two-phase apply exists only because Cloud Run
# needs the image to exist and the image needs the Artifact Registry repo.
set -euo pipefail
cd "$(dirname "$0")"

TAG="${1:-v1}"
PROJECT_ID="$(grep -E '^project_id' terraform/terraform.tfvars | cut -d'"' -f2)"
REGION="$(grep -E '^region' terraform/terraform.tfvars | cut -d'"' -f2)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/agents/ops-agent:${TAG}"

echo "== phase 1: registry, IAM, bucket, Firestore"
terraform -chdir=terraform init -input=false >/dev/null
terraform -chdir=terraform apply -input=false -auto-approve \
  -target=google_artifact_registry_repository.agents \
  -target=google_service_account.build \
  -target=google_project_iam_member.build_roles \
  -target=google_firestore_database.default

echo "== phase 2: build ${IMAGE} with Cloud Build"
gcloud builds submit --project "${PROJECT_ID}" --config cloudbuild.yaml \
  --substitutions="_TAG=${TAG},_REGION=${REGION}" .

echo "== phase 3: everything else (Cloud Run)"
terraform -chdir=terraform apply -input=false -auto-approve -var "image=${IMAGE}"

echo
echo "Open the UI (private service) with:"
echo "  gcloud run services proxy ops-agent --region ${REGION} --project ${PROJECT_ID} --port 8080"
