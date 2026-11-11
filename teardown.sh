#!/usr/bin/env bash
# Teardown so nothing bills afterwards: terraform destroy (bucket force_destroy, Firestore deletion_policy=DELETE,
# Artifact Registry repo, Cloud Run service, service accounts) and then a report of what is left. Safe to re-run.
set -uo pipefail
cd "$(dirname "$0")"
PROJECT_ID="$(grep -E '^project_id' terraform/terraform.tfvars | cut -d'"' -f2)"
REGION="$(grep -E '^region' terraform/terraform.tfvars | cut -d'"' -f2)"
g() { gcloud "$@" --project "$PROJECT_ID" --quiet; }

echo "== terraform destroy"
terraform -chdir=terraform init -input=false >/dev/null 2>&1 || true
terraform -chdir=terraform destroy -input=false -auto-approve 2>&1 | grep -v 'Still destroying' | tail -8

echo "== leftovers in $PROJECT_ID (expect nothing below)"
echo "Cloud Run services:"; g run services list --region "$REGION" --format='value(metadata.name)' 2>/dev/null | grep -v '^billing-guard$' || true
echo "Artifact repos:";     g artifacts repositories list --format='value(name)' 2>/dev/null
echo "buckets:";            gcloud storage ls --project "$PROJECT_ID" 2>/dev/null | grep -v 'cloudbuild\|gcf-' || true
echo "Firestore:";          g firestore databases list --format='value(name)' 2>/dev/null
echo "done. (billing-guard, if present, is the budget kill-switch function: scale-to-zero, keep it.)"
