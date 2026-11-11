# Rebuild from zero

Everything in this repo is reproducible: Terraform owns the cloud resources, Cloud Build builds the image,
`deploy.sh` sequences it, and `demo/` re-records the video. This page is the exact order of operations,
including the organisation-policy and tooling gotchas that cost time the first time.

Time: ~15 minutes to a working agent. Cost while up: Cloud Run scales to zero; a demo run costs a few rupees.

## 0. Prerequisites

| Need | Notes |
|---|---|
| Google Cloud account with a billing account | Credits are fine. A budget with a Pub/Sub → Cloud Run "kill switch" that unlinks billing is a good safety net. |
| `gcloud` (>= 590), `terraform` (>= 1.6), Python 3.12+ | Built from WSL Ubuntu 24.04 on Windows; any Linux/macOS works. |
| `gcloud auth login` and `gcloud auth application-default login` | ADC is used by Terraform, the local agent and the demo recorder. |
| Vertex AI quota for `gemini-3.8-flash` (global) and `gemini-embedding-001` (us-central1) | Default quota is enough. |

If your account lives in an **organisation** (even a one-person Cloud Identity org), two constraints bite:

```bash
# 1. Domain-restricted sharing blocks gmail/system principals in IAM bindings. Override per project:
gcloud services enable orgpolicy.googleapis.com --project "$PROJECT_ID"
cat > /tmp/drs.yaml <<EOF
name: projects/$PROJECT_ID/policies/iam.allowedPolicyMemberDomains
spec:
  rules:
  - allowAll: true
EOF
gcloud org-policies set-policy /tmp/drs.yaml --project "$PROJECT_ID"
# 2. iam.automaticIamGrantsForDefaultServiceAccounts is usually enforced: default SAs have no roles.
#    This repo never uses them (dedicated sa-ops-agent + sa-build), so nothing to do.
```

## 1. Project

```bash
export PROJECT_ID=bj-gemini-agent            # pick a new ID if the old one was deleted (IDs are not reusable)
gcloud projects create "$PROJECT_ID" --name "Gemini RAG agent"
gcloud billing projects link "$PROJECT_ID" --billing-account <BILLING_ACCOUNT_ID>
gcloud config set project "$PROJECT_ID"
gcloud auth application-default set-quota-project "$PROJECT_ID"
```

Terraform enables the APIs (`terraform/apis.tf`): Cloud Run, Cloud Build, Artifact Registry, Vertex AI,
Firestore, Storage, IAM.

## 2. Configure and deploy

```bash
git clone https://github.com/bhavishyajain545/gcp-gemini-rag-agent && cd gcp-gemini-rag-agent
cp terraform/terraform.tfvars.example terraform/terraform.tfvars    # project_id, region, models, image tag
./deploy.sh v1
```

`deploy.sh` does three phases, all through Terraform except the build:

1. `terraform apply` targeted at the Artifact Registry repo, the build service account + roles and the Firestore database.
2. `gcloud builds submit` with `cloudbuild.yaml` (runs as `sa-build`, logging `CLOUD_LOGGING_ONLY`) → `…/agents/ops-agent:v1`.
3. `terraform apply` for the rest: runtime SA + IAM, runbooks bucket + objects, Firestore composite index, Cloud Run service (private, no `allUsers`).

Re-deploying code = `./deploy.sh v2` (new tag; Terraform updates the Cloud Run revision).

## 3. Verify

```bash
gcloud components install cloud-run-proxy            # once
gcloud run services proxy ops-agent --region us-central1 --project "$PROJECT_ID" --port 8080
# open http://127.0.0.1:8080/dev-ui/  (use 127.0.0.1, not localhost: ::1 is not proxied)
# ask: "CouchDB crashed on prod, what are the recovery steps?"  → answer cites (source: couchdb-recovery.md)
# then: "Open a P2 ticket for this."  → Firestore document in the tickets collection
```

The ID token the proxy uses expires after ~1 hour: restart the proxy if the UI starts failing.

Local run without Cloud Run: `pip install -r app/requirements.txt`, export `GOOGLE_GENAI_USE_VERTEXAI=TRUE GOOGLE_CLOUD_PROJECT=$PROJECT_ID GOOGLE_CLOUD_LOCATION=global`, `cd app && adk web`.

## 4. Re-record the demo (optional)

Windows host: Python 3.14 with `playwright` (`playwright install chromium`), ffmpeg 9 in `%LOCALAPPDATA%\Programs\ffmpeg`,
Google Cloud TTS API enabled (narration uses Chirp 3 HD, falls back to edge-tts).

```powershell
# a real Chrome profile that is signed in to the Cloud console, with remote debugging (console scenes are screencast from it)
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir=$env:LOCALAPPDATA\Google\Chrome\DemoProfile --remote-debugging-port=9222
# start the Cloud Run proxy (above) on port 8080, then:
$env:DEMO_EXTRA_PATH = "$env:LOCALAPPDATA\Google\google-cloud-sdk\bin;$env:LOCALAPPDATA\Programs\ffmpeg\ffmpeg-9.0.2-essentials_build\bin"
python -u demo\scenes.py        # writes demo/demo.mp4, captions.srt, transcript.md
```

Review the result frame-by-frame before publishing (`ffmpeg -ss <t> -i demo/demo.mp4 -frames:v 1 f.jpg` per scene).

## 5. Tear down (stop all cost)

```bash
terraform -chdir=terraform destroy -auto-approve     # bucket force_destroy, Firestore deletion_policy=DELETE, AR repo
gcloud projects delete "$PROJECT_ID"                 # optional; IDs cannot be reused afterwards
```

With the project kept but empty there is no charge: Cloud Run, Artifact Registry, Firestore and the bucket are gone.

## Gotchas met while building (so you do not meet them again)

- Gemini 3.x models return 404 from `us-central1`; use the `global` Vertex AI location (`vertex_location`).
- Default thinking made each turn 30–100 s; `thinking_level=low` in `agent.py` brings it to ~10 s.
- `gemini-embedding-2` returned one vector for a batched request; the index uses `gemini-embedding-001` and asserts `len(vectors) == len(texts)`.
- Firestore composite index (`status`, `created_at`) is in Terraform; without it `list_open_tickets` fails.
- Cloud Run proxy on Windows: run it from WSL or install the `cloud-run-proxy` component; it binds 127.0.0.1 only.
