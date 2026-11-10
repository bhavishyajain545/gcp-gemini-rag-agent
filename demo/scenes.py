"""Demo video for Project 1: Gemini RAG + ADK Ops Agent on Cloud Run.

Prerequisites (run from the repo root on the machine with Chrome):
  1. The service is deployed (`./deploy.sh`).
  2. `gcloud run services proxy ops-agent --region us-central1 --port 8080` is running.
  3. Optional: a Chrome profile dir that is signed in to the Google Cloud console
     (PROFILE_DIR below). Without it the console scenes are replaced by gcloud output.

  python demo/scenes.py

Outputs demo/demo.mp4, demo/captions.srt, demo/transcript.md.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

from recorder import Demo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROJECT = "bj-gemini-agent"
REGION = "us-central1"
UI = "http://localhost:8080/dev-ui/?app=ops_agent"
# Console scenes need a signed-in browser. Start Chrome with --remote-debugging-port=9222 and the
# recorder attaches to it (CDP_URL); otherwise a private profile is used and console scenes are skipped.
CDP_URL = os.environ.get("DEMO_CDP_URL", "http://127.0.0.1:9222")  # 127.0.0.1, not localhost: Chrome does not listen on ::1
GCLOUD = os.environ.get("GCLOUD", "gcloud")

CHAT_INPUT = "textarea.chat-input-box"
SEND_BTN = "button.send-message-btn"

# Make gcloud / terraform / curl resolvable even when launched from an IDE with a stale PATH.
for p in os.environ.get("DEMO_EXTRA_PATH", "").split(os.pathsep):
    if p:
        os.environ["PATH"] = p + os.pathsep + os.environ["PATH"]
os.chdir(ROOT)


def sh(cmd: str) -> str:
    """Run a real command now and return its output for the terminal scenes."""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


def tf(args: str) -> str:
    """Terraform was initialised inside WSL (Linux provider binaries), so run it there on Windows."""
    if os.name == "nt":
        wsl_root = "/mnt/" + ROOT.drive[0].lower() + ROOT.as_posix()[2:]
        return sh(f'wsl -e bash -c "source ~/.gcp-env.sh; cd {wsl_root}/terraform && terraform {args}"')
    return sh(f"terraform -chdir=terraform {args}")


BOT_BUBBLE = ".content-bubble.role-bot.type-message"  # final text replies (tool calls render as chips, not bubbles)


async def wait_for_reply(page, previous_count: int, timeout_s: int = 120) -> None:
    """Wait until a new bot text bubble exists and the UI is no longer streaming."""
    await page.wait_for_function(
        "([sel, n]) => document.querySelectorAll(sel).length > n",
        arg=[BOT_BUBBLE, previous_count], timeout=timeout_s * 1000,
    )
    # settle: no text growth for 1.5s
    last, stable = -1, 0
    while stable < 3:
        await asyncio.sleep(0.5)
        length = await page.evaluate("() => document.body.innerText.length")
        stable = stable + 1 if length == last else 0
        last = length


async def bot_count(page) -> int:
    return await page.evaluate("(sel) => document.querySelectorAll(sel).length", BOT_BUBBLE)


NARRATION = {
    "arch": (
        "This is a DevOps on-call assistant built with Google's Agent Development Kit and Gemini on Vertex AI. "
        "It answers operational questions from our runbooks using retrieval-augmented generation, and it can act: "
        "opening incident tickets in Firestore and checking service health. "
        "It runs on Cloud Run as a dedicated service account with no keys, and everything is provisioned with Terraform."
    ),
    "security": (
        "First, the security posture. The Cloud Run service is not public: an unauthenticated request gets a 403, and the IAM policy has no all-users binding. "
        "The runtime identity is a dedicated service account with just two project roles, Vertex AI user and Datastore user, plus read-only access on the runbooks bucket. "
        "There are no service account keys anywhere. Locally I reach the service through gcloud run services proxy, which injects my own identity token."
    ),
    "rag": (
        "Now the agent itself, in the ADK web UI served by Cloud Run. I ask how to recover CouchDB after a crash. "
        "The agent calls search runbooks, which embeds the question with Vertex AI and runs a cosine similarity search over the runbook chunks. "
        "It then reads the best-matching runbook in full and answers with the exact ordered steps, citing the source file. "
        "It is instructed to answer only from the runbooks, so it will say so when something is not covered rather than guess."
    ),
    "trace": (
        "The left panel shows the event and trace view: the model's function call to search runbooks, the tool result, the read runbook call, and the final response. "
        "This is the same observability you get from ADK locally, now running against the deployed service."
    ),
    "ticket": (
        "Next, an action. I ask the agent to open a P1 ticket for this incident. "
        "Gemini fills the tool arguments from the conversation, a title, the severity, and a summary, and calls create incident ticket, "
        "which writes a document to Firestore using the service account, with no credentials in the code. The agent confirms the ticket id."
    ),
    "chain": (
        "The agent can chain tools in one turn. Here it checks the queue processor through the status tool, and then lists the open tickets from Firestore, newest first, "
        "using a composite index that Terraform created alongside the database."
    ),
    "firestore_bridge": (
        "Let's verify that write in the Firestore console."
    ),
    "firestore": (
        "The tickets collection shows the new document with the fields the agent wrote: title, severity, summary, status and a server timestamp."
    ),
    "cloudrun_bridge": (
        "And finally the Cloud Run service itself, on its security tab."
    ),
    "cloudrun": (
        "It confirms what we saw on the command line: authentication is required, "
        "and the service identity is the dedicated sa ops agent service account. No keys were created for it."
    ),
    "wrap": (
        "Everything you saw is defined in Terraform: APIs, the service account and its roles, the private bucket with the runbooks, Firestore and its index, Artifact Registry and the Cloud Run service. "
        "The image is built by Cloud Build with its own least-privilege build account. "
        "The code, Terraform and this recording are in the GitHub repository linked in the description. Thanks for watching."
    ),
}


def cdp_available() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(CDP_URL + "/json/version", timeout=2):
            return True
    except Exception:
        return False


def warm_up() -> None:
    """Hit the agent once so the Cloud Run instance is hot and the RAG index is built before recording."""
    import json as _json
    import urllib.request
    base = "http://localhost:8080"
    try:
        urllib.request.urlopen(urllib.request.Request(f"{base}/apps/ops_agent/users/warm/sessions/w1", data=b"{}", method="POST",
                                                      headers={"Content-Type": "application/json"}), timeout=30)
    except Exception:
        pass
    body = _json.dumps({"appName": "ops_agent", "userId": "warm", "sessionId": "w1",
                        "newMessage": {"role": "user", "parts": [{"text": "How do I renew an expired TLS certificate?"}]}}).encode()
    t = time.time()
    with urllib.request.urlopen(urllib.request.Request(f"{base}/run", data=body, headers={"Content-Type": "application/json"}), timeout=300) as r:
        events = _json.load(r)
    print(f"warm-up: {len(events)} events in {time.time() - t:.0f}s")


async def main() -> None:
    use_cdp = cdp_available()
    demo = Demo(out_dir=HERE, cdp_url=CDP_URL if use_cdp else None)
    await demo.prepare(*NARRATION.values())

    # Pre-compute real command outputs BEFORE recording starts (gcloud on Windows
    # takes ~10 s per call) so the terminal scenes show genuine data without dead air.
    t0 = time.time()
    svc = json.loads(sh(f"{GCLOUD} run services describe ops-agent --region {REGION} --project {PROJECT} --format=json"))
    url = svc["status"]["url"]
    sa = svc["spec"]["template"]["spec"]["serviceAccountName"]
    unauth = sh(f'curl -s -o /dev/null -w "%{{http_code}}" {url}/dev-ui/')
    iam = sh(f"{GCLOUD} run services get-iam-policy ops-agent --region {REGION} --project {PROJECT} --format=yaml")
    roles = sh(f'{GCLOUD} projects get-iam-policy {PROJECT} --flatten="bindings[].members" --filter="bindings.members:{sa}" --format="value(bindings.role)"')
    keys = sh(f"{GCLOUD} iam service-accounts keys list --iam-account {sa} --project {PROJECT} --managed-by=user 2>&1")
    bucket = sh(f"{GCLOUD} storage ls gs://{PROJECT}-runbooks/runbooks/")
    tf_state_count = str(len(tf("state list").splitlines()))
    tf_output = tf("output -no-color")
    print(f"pre-computed command outputs in {time.time() - t0:.0f}s")

    await asyncio.to_thread(warm_up)
    page = await demo.start()

    # Pre-load the two console pages in background tabs; they take 30-120 s on a slow
    # link, which is covered by scenes 1-6. The recording switches to them later.
    fs_tab = run_tab = None
    if use_cdp:
        fs_tab = await demo.new_tab(f"https://console.cloud.google.com/firestore/databases/-default-/data/panel/tickets?project={PROJECT}")
        run_tab = await demo.new_tab(f"https://console.cloud.google.com/run/detail/{REGION}/ops-agent/security?project={PROJECT}")
        await demo.capture(page)

    # ---- Scene 1: title + architecture ------------------------------------
    async def s1():
        await page.goto((ROOT / "docs" / "architecture.html").as_uri())
        await page.evaluate("() => { document.body.style.zoom = '1.33'; document.body.style.margin = '0'; }")
    await demo.scene("Architecture", NARRATION["arch"], s1)

    # ---- Scene 2: private service, keyless identity ------------------------
    async def s2():
        await demo.terminal("Cloud Run: private service, keyless identity", [
            (f"gcloud run services describe ops-agent --region {REGION} --format='value(status.url)'", url),
            (f"curl -s -o /dev/null -w '%{{http_code}}' {url}/dev-ui/", f"{unauth}   <- not public: IAM-authenticated only"),
            ("gcloud run services get-iam-policy ops-agent --region " + REGION, iam + "\n(no allUsers binding)"),
            (f"gcloud projects get-iam-policy {PROJECT} --filter='bindings.members:{sa}' --format='value(bindings.role)'", roles),
            (f"gcloud iam service-accounts keys list --iam-account {sa} --managed-by=user", keys or "Listed 0 items.  <- no JSON keys exist"),
            (f"gcloud storage ls gs://{PROJECT}-runbooks/runbooks/", bucket),
        ], type_delay=8, pause=0.5)
    await demo.scene("Security posture", NARRATION["security"], s2, hold=1.0)

    # ---- Scene 3: ask a runbook question ----------------------------------
    async def s3():
        await page.goto(UI, wait_until="domcontentloaded")
        await page.wait_for_selector(CHAT_INPUT, timeout=60000)
        try:
            await page.get_by_role("button", name="No Thanks").click(timeout=4000)
        except Exception:
            pass
        await asyncio.sleep(0.8)
        await demo.type_into(CHAT_INPUT, "CouchDB crashed on prod after a reboot. What are the recovery steps?", delay=30)
        await asyncio.sleep(0.4)
        n = await bot_count(page)
        await page.click(SEND_BTN)
        await wait_for_reply(page, n)
    await demo.scene("RAG question", NARRATION["rag"], s3, hold=2.5)

    # ---- Scene 4: open the trace -------------------------------------------
    async def s4():
        # Click the tool-call event rows so the left panel shows request/response details.
        rows = page.locator(".message-row-container.bot")
        for idx in (0, 1):  # search_runbooks call, then its result
            try:
                await rows.nth(idx).click(timeout=4000)
                await asyncio.sleep(4)
            except Exception:
                break
        try:
            await page.get_by_role("button", name="Traces").click(timeout=4000)
            await asyncio.sleep(4)
            await page.get_by_role("button", name="Events").click(timeout=4000)
        except Exception:
            pass
    await demo.scene("Tool trace", NARRATION["trace"], s4)

    # ---- Scene 5: take an action -------------------------------------------
    ticket_id: dict[str, str] = {}

    async def s5():
        await demo.type_into(CHAT_INPUT, "Open a P1 ticket for this incident.", delay=35)
        await asyncio.sleep(0.4)
        n = await bot_count(page)
        await page.click(SEND_BTN)
        await wait_for_reply(page, n)
        import re
        text = await page.evaluate("(sel) => [...document.querySelectorAll(sel)].pop()?.innerText || ''", BOT_BUBBLE)
        m = re.search(r"\b[A-Za-z0-9]{20}\b", text)
        if m:
            ticket_id["id"] = m.group(0)
    await demo.scene("Create a ticket", NARRATION["ticket"], s5, hold=2.0)

    # ---- Scene 6: list tickets + status tool -------------------------------
    async def s6():
        await demo.type_into(CHAT_INPUT, "Is the queue-processor healthy? Then list all open tickets.", delay=35)
        await asyncio.sleep(0.4)
        n = await bot_count(page)
        await page.click(SEND_BTN)
        await wait_for_reply(page, n)
    await demo.scene("Status and ticket list", NARRATION["chain"], s6, hold=2.0)

    # ---- Scene 7/8: Google Cloud console (only with the signed-in Chrome via CDP) ----
    # The console takes 10-30 s to render, so a short bridge narration covers the load
    # and the descriptive narration starts once the page is actually on screen.
    async def ready(tab, selector: str, timeout: int = 120000) -> None:
        try:
            await tab.wait_for_selector(selector, timeout=timeout)  # slow loads are cut from the video anyway
        except Exception as exc:
            print(f"  ! not ready ({selector}): {type(exc).__name__}")

    if use_cdp:
        async def s7():
            await ready(fs_tab, "text=Add document")
            await demo.capture(fs_tab)
            if ticket_id:  # open the document the agent just created (in-app navigation, fast)
                try:
                    await fs_tab.get_by_text(ticket_id["id"], exact=True).first.click(timeout=15000)
                except Exception as exc:
                    print(f"  ! could not open ticket doc: {type(exc).__name__}")
                await ready(fs_tab, "text=created_at", 60000)
            await asyncio.sleep(1.5)
        await demo.scene("Open Firestore", NARRATION["firestore_bridge"], s7)
        await demo.scene("Firestore console", NARRATION["firestore"], None, hold=1.5)

        async def s8():
            await ready(run_tab, "text=Require authentication")
            await demo.capture(run_tab)
            await asyncio.sleep(1.5)
        await demo.scene("Open Cloud Run", NARRATION["cloudrun_bridge"], s8)
        await demo.scene("Cloud Run security", NARRATION["cloudrun"], None, hold=1.0)
        await demo.capture(page)

    # ---- Scene 8: wrap-up -----------------------------------------------------
    async def s8():
        await demo.terminal("Infrastructure as code + cleanup", [
            ("ls terraform/", "main.tf  outputs.tf  variables.tf  versions.tf  terraform.tfvars.example"),
            ("terraform -chdir=terraform state list | wc -l", tf_state_count),
            ("terraform -chdir=terraform output", tf_output),
            ("# when done: terraform -chdir=terraform destroy", "Cloud Run scales to zero, so an idle deployment costs nothing; destroy removes everything."),
        ], type_delay=8, pause=0.5)
    await demo.scene("Wrap-up", NARRATION["wrap"], s8, hold=1.5)

    await demo.finish("demo")


if __name__ == "__main__":
    asyncio.run(main())
