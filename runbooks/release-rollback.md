# Runbook: Rolling back a failed release

**Scope:** Containerised services deployed with Docker Compose (on-prem) or Kubernetes (cloud).  
**Severity guidance:** P1 if production users cannot log in or core workflows fail; P2 for a single broken feature on UAT/QA.

## Decide fast: roll back or roll forward?
Roll **back** when the previous image is known-good and the failure is in application code or configuration. Roll **forward** only when the fix is a one-line config change that is already tested. Do not debug in production for more than 10 minutes before rolling back.

## Pre-checks (2 minutes)
1. Identify the failing service and the image tag that was just deployed: `docker compose ps` / `kubectl get deploy <svc> -o jsonpath='{.spec.template.spec.containers[0].image}'`.
2. Confirm the previous tag exists in the registry (Artifact Registry / ACR / ECR).
3. Check whether the release included a **database migration**. If it did, see the section "Releases with migrations" before touching anything.

## Rollback: Docker Compose hosts
1. `cd /opt/<project>/<service>`
2. Edit `.env` or `docker-compose.yml` and set `IMAGE_TAG` back to the previous tag.
3. `docker compose up -d <service>` (recreates only that container).
4. Watch logs for 60 seconds: `docker compose logs -f --tail=100 <service>`. The service must log its "started" line and no stack traces.
5. Run the smoke test: health endpoint `curl -fsS http://localhost:<port>/health` and one real user action.

## Rollback: Kubernetes
1. `kubectl rollout undo deployment/<svc> -n <ns>` (returns to the previous ReplicaSet).
2. `kubectl rollout status deployment/<svc> -n <ns>` must finish with "successfully rolled out".
3. If the deployment is managed by GitOps (ArgoCD), **also revert the commit** in the manifests repo, otherwise ArgoCD will re-apply the broken tag on the next sync. Use `git revert <sha>`, never a force push.

## Releases with migrations
- Migrations that only **add** columns or tables are backward compatible: roll back the application and leave the schema.
- Migrations that **rename or drop** columns are not: do not roll back the application alone. Restore the pre-release database backup, then roll back the application, then re-run the row-count verification from the migration runbook.

## After the rollback
1. Post in the release channel: service, old tag, new (restored) tag, user impact, time to recover.
2. Open a ticket for the root cause with severity matching the user impact.
3. Keep the broken image tag in the registry for debugging; do not delete it for 7 days.
