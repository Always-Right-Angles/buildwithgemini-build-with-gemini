---
name: troubleshoot-lab-setup
description: >-
  Verify the Gemini World lab environment is set up correctly, and diagnose/fix
  common errors. Use at the START of the lab right after logging in to confirm
  everything is ready ("check my setup", "am I ready to start", "verify my
  environment", "did I log in correctly"), AND whenever the user hits an error and
  doesn't know why — permission denied / 403 / PERMISSION_DENIED, "API not
  enabled", a deploy that fails, the frontend can't reach the agent, /chat errors,
  code sandbox failures, image generation failures, Antigravity failing to open a
  link / Chrome not launching in the remote desktop, or a vague "it's not working".
  Checks the usual culprits — signed into Antigravity with the right account
  (GCP/lab flow, not personal Google login), the GCP project is set, both
  gcloud auth login and application-default login have run, the API is enabled,
  and the identity has roles/aiplatform.user. Don't use for writing agent features
  or non-error build questions.
---

# Troubleshoot the lab setup

Nearly every failure in this lab is one of a handful of environment problems —
not the user's code. This skill has **two modes**:

- **Preflight** — run at the *start* of the lab, right after the user logs in, to
  confirm everything is ready before they build. Catches problems early instead
  of mid-module.
- **Error triage** — run when the user hits an error. Run the checks below first,
  fix what's wrong, then jump to the matching symptom.

Prefer *verifying* state with a read command before *changing* anything, and tell
the user what you found.

## Preflight: start-of-lab health check

When the user asks to verify their setup (or you're kicking off the lab), run
**checks 0-6 below in order** and report a clear pass/fail summary, e.g.:

```
Setup check:
✅ Antigravity signed in as <lab account>
✅ Project set to <qwiklabs project id>
✅ gcloud auth + ADC present
✅ Vertex AI / aiplatform API enabled
✅ roles/aiplatform.user granted
✅ agents-cli skills loaded in AGY
✅ URL-open interceptors installed as files (xdg-open + shim; Chrome launches from Antigravity)
You're ready to start. ✅
```

Fix anything that fails, then re-run that check before moving on. Skip the
deploy/frontend/sandbox symptoms during preflight — those come up later.

## The checks (run these for almost ANY error, and for preflight)

These are the usual culprits. Check all of them before deep-diving.

**0. Is the user signed into Antigravity with the RIGHT account?** A very common
trap: signing into Antigravity with a personal **Google login** (e.g. a
`@gmail.com` or `@google.com` account) instead of the **GCP / Qwiklabs lab
credentials**. Everything *looks* fine, but calls to the project fail with
permission errors because AGY is acting as the wrong identity.

- Ask the user which account they used to sign into Antigravity, and confirm it's
  the **Qwiklabs lab account**, not their personal Google account.
- Cross-check the active gcloud account matches the lab account:
  ```bash
  gcloud auth list        # the ACTIVE (*) account should be the lab account
  ```
- If AGY is signed in with the wrong account, have the user sign out of
  Antigravity and sign back in using the GCP/lab login flow (per the lab's setup
  instructions), then re-run the preflight.

**1. Is the right project set?** Cloud Shell / AGY can silently default to the
wrong project (e.g. `cloudshell-gca`), which makes enable/deploy commands fail.

```bash
gcloud config get-value project          # what's active right now?
echo "$GOOGLE_CLOUD_PROJECT"             # what the env thinks it is
```

A correctly-set Qwiklabs project ID **contains the string `qwiklabs`** (e.g.
`qwiklabs-gcp-01-abc123def456`). If the active project doesn't contain
`qwiklabs`, it's almost certainly the wrong project — treat that as a red flag.

If either is wrong, empty, or missing `qwiklabs`, **ask the user for their
Qwiklabs Project ID** (from the lab panel) and pin it for them by running:

```bash
export GOOGLE_CLOUD_PROJECT=<their qwiklabs project id>
gcloud config set project "$GOOGLE_CLOUD_PROJECT"
```

Also confirm the project is pinned inside AGY's own settings so it can't switch
mid-run. During preflight, always pin the project this way — don't assume it's
already set.

**2. Has the user authenticated?** Two separate logins are required — a missing
Application Default Credentials (ADC) login is the #1 cause of 403s from code.

```bash
gcloud auth list                          # is there an active account?
```

If not authenticated, run BOTH:

```bash
gcloud auth login
gcloud auth application-default login
```

**3. Is the needed API enabled?** Deploy, sandbox, and model calls need the
Agent Platform / Vertex AI API on. "API not enabled" errors usually mean this or
the wrong project (see #1).

```bash
gcloud services list --enabled | grep -i aiplatform
gcloud services enable aiplatform.googleapis.com   # enable if missing
```

**4. Does the identity have the right IAM role?** Many features need
`roles/aiplatform.user`. If a call is `PERMISSION_DENIED`, check the role on
whichever identity is making the call (your user, the agent's service account, or
the Cloud Run service account).

```bash
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
  --member="user:<you@example.com>" \
  --role="roles/aiplatform.user"
```

Match the role to what the calling identity actually *does*. A **deployed agent**
runs as its own service account with **no Firestore/Cloud Storage access by
default**, so any agent that reads Firestore must have `roles/datastore.user`
granted to that service account — **grant it at deploy time** (see "After you
deploy" below), not just `aiplatform.user` on your user.

**5. Are the agents-cli skills loaded in AGY?** The lab's scaffold, deploy,
evaluate, and Memory Bank steps all rely on the `google-agents-cli-*` skills
being registered with Antigravity. These are **separate** from the workshop
skills that ship in the repo's `.agents/skills/` — they're installed by the
`agents-cli setup` step, not automatically.

- In AGY, run `/skills` and confirm you see the `google-agents-cli-*` lifecycle
  skills (e.g. scaffold, deploy, adk-code) **in addition to** the workshop
  skills. If only the workshop skills appear, the agents-cli skills aren't loaded.
- If they're missing, install them from the Cloud Shell:
  ```bash
  agents-cli setup --skip-auth
  ```
- Then **restart Antigravity** so it picks up the newly installed skills (see
  "Antigravity / MCP behaving oddly right after install" below), and re-run
  `/skills` to confirm they now appear.

**6. Are the URL-open interceptors installed as executable FILES? (do this EVERY
preflight — don't wait for it to break.)** In the Selkie remote desktop,
Antigravity opens links through two PATH entries — **`/config/automata/bin/xdg-open`**
(what the desktop actually calls to open a URL) and **`/config/automata/bin/shim`**.
Two separate failure modes have been seen:

- The script hits an `exit 0` before it launches a browser (only opens a browser
  when `AG_URL_HANDLER` is set, silently drops the link otherwise).
- **The path ships as a *directory* instead of a file.** This is the nasty one:
  a directory at `/config/automata/bin/shim` can't be executed, AND naively
  copying a file onto it (`cp`/`install <src> <dir>`) drops the file *inside* the
  directory (`.../shim/shim`) instead of replacing it — so the fix appears to run
  but nothing actually changes.

**Proactively install the corrected script to BOTH paths during preflight**,
replacing whatever is there (file *or* directory). This is idempotent — always do
it rather than testing first and hoping. The corrected script is bundled with
this skill at `assets/shim` (already on disk in the cloned repo; no download
needed). Use `sudo` on each command if `/config/automata/bin` is root-owned:

```bash
# Locate this skill's bundled script on disk.
SRC="$(find / -path '*troubleshoot-lab-setup/assets/shim' 2>/dev/null | head -1)"
if [ -z "$SRC" ]; then
  echo "Could not find the bundled shim — is the lab repo cloned? Aborting." >&2
else
  for target in /config/automata/bin/xdg-open /config/automata/bin/shim; do
    # mv aside whatever's there — handles a FILE or a DIRECTORY, unlike cp/install.
    [ -e "$target" ] && mv "$target" "${target}.bak.$(date +%s)"
    install -m 0755 "$SRC" "$target"
    echo "Installed $target from $SRC"
  done
fi
```

Then **verify** both are regular executable files (not directories) and that a URL
actually opens a browser:

```bash
for target in /config/automata/bin/xdg-open /config/automata/bin/shim; do
  if [ -f "$target" ] && [ -x "$target" ] && grep -q 'google-chrome' "$target" \
     && ! grep -q '^exit 0' "$target"; then
    echo "$target OK"
  else
    echo "$target STILL BROKEN (directory? not executable? old script?)"
  fi
done
xdg-open https://example.com   # a Chrome window should open; URL logged to /tmp/ag_opened_urls.txt
```

Confirm `/usr/bin/google-chrome` exists (`command -v google-chrome`); if Chrome
lives elsewhere in the image, update the path in `assets/shim` to match. Only
report this check ✅ once a link actually opens a browser window.

> Tip: if you have the **Developer Knowledge MCP** installed, use it to confirm
> the exact API name, role, and command for a given product instead of guessing.

## Symptom → fix

### 403 / PERMISSION_DENIED / "permission denied"
Almost always one of: signed into Antigravity with the wrong (personal) account
instead of the lab account (check #0), ADC missing (check #2), a missing
`roles/aiplatform.user` on the calling identity (check #4), or the wrong project
(check #1). Rule those out in that order.

### "API not enabled" / "SERVICE_DISABLED"
You're either on the wrong project (#1) or the API is off (#3). Fix the project
first, then enable.

### `adk web`/`adk run` fails at startup / `cannot import name '<x>' from 'google.cloud'` / ModuleNotFound
You ran a **bare `adk`**, which resolves to a *global* Python that doesn't have
your project's dependencies. Run it through the project `.venv` with **`uv run`**:

```bash
uv run adk web --port 8080 --allow_origins "*" --reload_agents
```

Tell-tale symptoms: `cannot import name 'firestore' from 'google.cloud'`, or a
`ModuleNotFoundError` for a package you *know* is installed (e.g.
`a2ui-agent-sdk`). Bare `adk` is a different interpreter; `uv run adk` uses the
project venv where the deps actually live.

### `agents-cli deploy` fails
1. Project pinned? (#1) — this is the most common cause.
2. APIs enabled and authenticated? (#2, #3)
3. Re-read the actual error; if it names a permission, go to #4.
List existing deployments to see current state: `agents-cli deploy --list`.

### After you deploy: grant the agent's service account the roles its tools need
Do this as part of **every** deploy where the agent reads Firestore or Cloud
Storage — proactively, don't wait for it to fail. The deployed agent runs as its
own service account (by default the Reasoning Engine service agent,
`service-PROJECT_NUMBER@gcp-sa-aiplatform-re.iam.gserviceaccount.com`) which has
**no data-access roles by default**. For a Firestore-backed agent, grant it
`roles/datastore.user` (this auto-fills your project number):

```bash
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
  --member="serviceAccount:service-$(gcloud projects describe "$GOOGLE_CLOUD_PROJECT" --format='value(projectNumber)')@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

For an agent that writes files to Cloud Storage (for example one that uploads
generated images), grant its service account write access to the bucket. Scope the
grant to the bucket, not the whole project:

```bash
gcloud storage buckets add-iam-policy-binding "gs://<your-image-bucket>" \
  --member="serviceAccount:service-$(gcloud projects describe "$GOOGLE_CLOUD_PROJECT" --format='value(projectNumber)')@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

A read-only Cloud Storage tool needs only `roles/storage.objectViewer` instead.
Also make sure you seeded your data in the same project you deployed to, otherwise
the deployed agent reads an empty database.

### Frontend can't reach the agent / no reply / errors on send
Run all frontend commands from the `frontend/` folder.
1. Dependencies installed? `pip install -r requirements.txt`
2. Is `AGENT_ENGINE_RESOURCE_NAME` set and correct? It must be the resource name
   from `deployment_metadata.json` (written by the deploy step). Also set
   `AGENT_DIRECTORY` to your `agent_directory` from `agents-cli-manifest.yaml`
   (usually `app`), since the A2A endpoint path includes it:
   ```bash
   echo "$AGENT_ENGINE_RESOURCE_NAME"
   export AGENT_ENGINE_RESOURCE_NAME="<paste from deployment_metadata.json>"
   export AGENT_DIRECTORY="app"
   ```
3. ADC present locally? (#2)
4. Sanity test: send a message, then ask "What did I just ask?" — if it can't
   remember, the wiring to the deployed agent is wrong, not the UI.
5. If plain-text replies work but **tool-backed answers return nothing**, it's not
   the UI — see "Deployed agent gives no reply" below.

### Frontend errors: `operation_schemas()` empty, `no attribute 'stream_query'`, or old proxy 500s
This is the **agents-cli 1.1.0 (GA)** change. GA deploys ADK agents to Agent Runtime
as A2A agents and no longer registers the reasoning-engine operation schema, so a
frontend built on `agent_engines.get(...).stream_query()` fails: `operation_schemas()`
is empty and the handle has no `stream_query`/`create_session`. Confirm the agent is
healthy over A2A first:
```bash
agents-cli run --url https://<LOCATION>-aiplatform.googleapis.com/v1/<RESOURCE> --mode a2a "hi"
```
If that answers, the agent is fine and the proxy is on the dead SDK path. Use the
current `build-agent-frontend` template, which talks A2A (fetches the agent card and
sends messages with the a2a-sdk client). Do not try to force an ADK/`stream_query`
deploy. Every 1.1.0 ADK template is A2A-tagged, and the container serves A2A
whether `is_a2a` is true or false.

### Deployed agent gives no reply / a tool works in the Playground but not deployed
A Firestore-backed tool works in the Playground (your local ADC) but the deployed
agent's turn dies with no reply. You almost certainly hit one of:

1. **You skipped the role grant.** Do "After you deploy" above — the deployed
   service account needs `roles/datastore.user`.
2. **You seeded and deployed in different projects.** The deployed agent reads
   Firestore from *its own* project; if you seeded elsewhere it sees an empty DB.
   Compare and re-seed into the deploy project if they differ:
   ```bash
   gcloud config get-value project          # where you seeded from
   echo "$AGENT_ENGINE_RESOURCE_NAME"        # the project the agent runs in
   ```

Confirm the Firestore DB exists and has data in the deploy project (Firebase
console), then re-test. A silent hang = wrong/empty project; `PERMISSION_DENIED`
= missing role.

### `NotFound: The database (default) does not exist` (deployed Firestore agent)
Your code is building the Firestore client from the project **number**, not the
ID. On Agent Engine, **both `google.auth.default()` and the `GOOGLE_CLOUD_PROJECT`
env var return the project *number*** — but Firestore only resolves the
`(default)` database by project **ID**. So this common pattern 404s on the
deployed agent even though it works locally:

```python
# WRONG on Agent Engine: GOOGLE_CLOUD_PROJECT is the project NUMBER there
db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
```

Pin the project **ID** explicitly — never derive the Firestore project from
`google.auth.default()` or `GOOGLE_CLOUD_PROJECT`:

```python
FIRESTORE_PROJECT = "<your-project-id>"           # the ID, NOT the number
db = firestore.Client(project=FIRESTORE_PROJECT)
```

Use the same ID in your seed script, then **redeploy**. (It works locally only
because your local `GOOGLE_CLOUD_PROJECT`/ADC is already the ID; the deployed
runtime sets it to the number.)

### `/chat` errors after deploying the frontend to Cloud Run
The Cloud Run service runs as a **different identity** than your local user, so
its service account needs `roles/aiplatform.user`. Grant it to the Cloud Run
service account (not your user account), then retry.

### Code sandbox / code execution fails
1. Agent Platform API enabled (#3) and identity has `roles/aiplatform.user` (#4).
2. Does a sandbox actually exist? If not, create one from the agent engine
   resource before running code.

### Image generation fails, or the image doesn't appear
If the tool errors while generating, it is usually an API/permission issue (#3, #4)
or a region/model-access mismatch. Confirm the model and region are available for
the project and that the API is enabled.

If the image shows in the Playground but not on the deployed agent, or a card or the
frontend shows a broken image, the agent uploads generated images to a public bucket
and shows the public URL. Two things must hold:

1. The deployed service account can write to the bucket
   (`roles/storage.objectAdmin`, see "After you deploy" above). It works locally
   because you run as yourself, but the deployed agent runs as its own account.
2. The bucket serves objects publicly. Grant `allUsers` the
   `roles/storage.objectViewer` role on the bucket. If that grant fails with
   `public access prevention is enforced`, the project's organization blocks public
   buckets and the public-URL approach will not work there.

### Antigravity can't open a link / Chrome won't launch in the remote desktop (Selkie)
In the Selkie remote desktop, Antigravity opens URLs through two PATH entries —
`/config/automata/bin/xdg-open` (what the desktop calls) and
`/config/automata/bin/shim`. If clicking a link (or an AGY "open in browser"
action) does nothing and no window appears, one of two things is wrong:

1. **The script exits before launching a browser** — the known-bad version hits
   an `exit 0` before the Chrome block, so it only opens a browser when
   `AG_URL_HANDLER` is set and silently drops the link otherwise.
2. **The path is a *directory*, not a file** — it can't be executed, and copying a
   file onto it lands *inside* the directory (`.../shim/shim`) instead of
   replacing it, so a naive fix looks applied but changes nothing.

The corrected script (routes to `AG_URL_HANDLER` if set, else `google-chrome`,
no stray `exit 0`, forwards `"$@"`) ships with this skill at `assets/shim`.
**Install it to BOTH paths, replacing a file or a directory** — this is the same
thing preflight check 6 does, so just run that block. Quick manual version:

```bash
SRC="$(find / -path '*troubleshoot-lab-setup/assets/shim' 2>/dev/null | head -1)"
for target in /config/automata/bin/xdg-open /config/automata/bin/shim; do
  [ -e "$target" ] && mv "$target" "${target}.bak.$(date +%s)"   # mv handles dir OR file
  install -m 0755 "$SRC" "$target"
done
```

The `exec` lines forward `"$@"` (all arguments) so flags or multiple URLs aren't
dropped, while only the URL (`"$1"`) is written to the capture log.

Verify: run `xdg-open https://example.com` (or click a link in Antigravity) —
Chrome should open and the URL should be appended to `/tmp/ag_opened_urls.txt`.
If it still fails, confirm both paths are regular files: `file
/config/automata/bin/xdg-open /config/automata/bin/shim` (neither should say
"directory").

### Antigravity / MCP behaving oddly right after install
If you just installed agents-cli or the Developer Knowledge MCP, **restart
Antigravity** so it picks up the new skills/MCP, then retry.

## Rules of thumb
- Confirm the **Antigravity account** first — signing in with a personal Google
  account instead of the lab/GCP flow silently breaks project access.
- Fix the **project** next — a wrong project makes half the other errors appear.
- There are **two** auth logins (`login` and `application-default login`); missing
  the second one breaks code-level calls while the CLI still looks fine.
- Match the IAM role to the **identity that actually makes the call** — your user
  locally, but the service account in Cloud Run.
- When unsure of an exact command/role/API name, check the Developer Knowledge MCP
  rather than guessing.
