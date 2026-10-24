---
name: record-demo
description: Record a screen-capture demo video (.webm) of the user's agent by driving its chat UI with Playwright — open the page, type queries, wait for replies, save the video. Works against both lab UIs: the custom FastAPI chat frontend (localhost:8080, the default) and the ADK Playground / dev UI (port 8000, via an app name). Can also generate instrumental background music with Google's Lyria model (lyria-002 on Vertex AI) and mix it under the video matched to its length — use when the user asks to add background music/a soundtrack/a vibe to the demo (e.g. "add lo-fi chill music"). Use when the user wants to record a demo, capture a video/screen recording of their agent, make a demo clip of their app, or show their agent in action. Picks demo prompts from the user's request if given, otherwise derives clever ones from project_brief.md. Ships ./record-agent.js. Not for taking still screenshots or for building the UI itself.
---

# Record a demo of your agent

Produce a short **`.webm` screen recording** of the participant's agent by
driving its chat UI in a headless browser: the script opens the page, types each
query, waits for the reply, and saves the video. It ships as
**`./record-agent.js`** and works with **either** lab UI — the custom FastAPI
frontend (default) or the ADK dev UI — so it fits whatever "face" the
participant has running. Every recording gets a branded **"Gemini World Tour"**
frame (a gradient border + title pill) drawn on top, it can be sped up so the
clip stays short, and — when asked — it can score the video with **AI-generated
background music** (Google's Lyria model) matched to the video's length.

> **The one rule:** don't rewrite the recorder. Call `./record-agent.js` with
> the right `--url`/`--app` and `--query` flags. It already handles Playwright
> setup, browser launch, typing, the branded frame, and saving the video.

## What makes a good demo (defaults to aim for)

Keep it **short and snappy** — a great clip is roughly **20–40 seconds**. The
defaults are tuned for that; the main knobs are how many turns you record and how
long each reply takes:

- **2–3 turns.** Enough to tell a story, short enough to stay watchable. Don't
  record more than 3.
- **Pick prompts that show off the best features** (a tool call, a Firestore
  lookup, a generated image, an A2UI card) rather than plain chit-chat.
- **Match `--wait` to the slowest turn.** Text replies land in a few seconds
  (default `--wait 12000` is plenty); **image or video generation needs
  `--wait 30000`+**, or the video cuts off mid-answer.
- **Speed it up to trim dead time.** If a turn has a long wait, add
  **`--speed 1.5`** (or `2`) so the final clip is brisk. This needs `ffmpeg`; if
  it's not installed the script just saves at normal speed.
- The frame, a short pre-roll on the empty UI, and a hold on the final reply are
  automatic — you don't need to configure them.

## Step 1 — Figure out what to demo (the queries)

Choose 2–3 demo prompts, in this order of precedence:

1. **Use what the user gave you.** If the user's request names specific things
   to ask/show (e.g. "record it answering what's in stock and then generating an
   image"), turn those directly into `--query` args, in order.
2. **Otherwise, read `project_brief.md`** in the project and invent 2–3 clever
   prompts that show the agent off — ideally ones that exercise its best
   features (a tool call, a lookup from Firestore, a generated image, an A2UI
   card). Prefer prompts you know will produce a rich reply for *this* agent.
3. **Otherwise** (no request, no brief), let the script fall back to its neutral
   built-in prompts.

Keep prompts short and concrete. For a multi-turn feel, make a later prompt
build on an earlier one (e.g. ask about an item, then ask to see a picture of it).

## Step 2 — Point it at the right UI

Pick the target based on what the participant has running:

- **Custom frontend (default, recommended for a polished demo):** it listens on
  `http://localhost:8080`. Just omit `--url` (or pass `--url http://localhost:8080`).
  Make sure they've started it (`python main.py` from `frontend/`, see the
  `build-agent-frontend` skill).
- **ADK Playground / dev UI:** pass `--app <name>`, where `<name>` is the agent's
  `app` / agent directory (from `agents-cli-manifest.yaml`). The script builds
  `http://127.0.0.1:8000/dev-ui/?app=<name>`. Make sure the playground is running.
  You can also pass a full `--url` if the port differs.

Whichever it is, confirm the UI is actually up and reachable first — the script
exits with a clear error if the page or the chat input can't be found.

## Step 3 — Run the recorder

From the project root:

```bash
# Custom frontend (default URL), prompts tailored to this agent:
node .agents/skills/record-demo/record-agent.js \
  -q "First demo prompt" \
  -q "Second demo prompt" \
  -o agent_demo.webm
```

```bash
# ADK dev UI instead, by app name:
node .agents/skills/record-demo/record-agent.js \
  --app my_agent \
  -q "First demo prompt" \
  -q "Second demo prompt"
```

```bash
# A demo with image generation: wait longer, then speed the clip up:
node .agents/skills/record-demo/record-agent.js \
  -q "What's in stock?" \
  -q "Generate a picture of the first item" \
  --wait 30000 --speed 1.5
```

On success it prints `SUCCESS: Recording saved to <path>`.

## Dependencies (Playwright + Chromium, installed once, globally)

The recorder needs the `playwright` npm package and its Chromium browser. Both
are meant to be installed **once, globally**, so they're never written into a
participant's repo and don't re-download on every run:

```bash
npm install -g playwright        # the package (global)
npx playwright install chromium  # the browser (shared per-user cache)
```

In the lab image these should be **pre-installed**. If they're missing, the
script installs them for you the first time (global package + shared browser
cache) — that first run takes a minute; every run after is instant. The script
resolves the global package via `npm root -g`, so it works without a local
`node_modules`. (If a global install isn't permitted, it falls back to a local
one.) `ffmpeg` is needed for `--speed` and `--music`; it's otherwise optional.
`--music` additionally needs an **authenticated gcloud** (which the lab already
has) — see the music section below.

## Options reference

| Flag | Meaning | Default |
| --- | --- | --- |
| `-q, --query <text>` | A message to send; repeat for multiple turns | two neutral fallback prompts |
| `-u, --url <url>` | Full URL of the chat UI | `http://localhost:8080/` |
| `-a, --app <name>` | ADK dev UI app name (builds the dev-ui URL when `--url` unset) | — |
| `-o, --output <file>` | Output `.webm` path | `./<app>_demo.webm` or `./agent_demo.webm` |
| `--delay <ms>` | Per-keystroke typing delay | `40` |
| `--wait <ms>` | Wait time for each reply (bump to 30000+ for media generation) | `12000` |
| `--speed <factor>` | Speed up the final video (needs `ffmpeg`; ignored if absent) | `1.0` |
| `--music <prompt>` | Generate + mix background music with Lyria (needs `ffmpeg` + gcloud) | off |
| `--music-negative <text>` | Lyria negative prompt (things to exclude) | — |
| `--music-volume <0..1>` | Music mix level | `0.6` |
| `--title <text>` | Frame title text | `Gemini World Tour` |
| `--no-frame` | Turn off the branded frame | frame on |
| `--headed` | Show the browser window | headless |

Run `node .agents/skills/record-demo/record-agent.js --help` for the same list.

## Background music (Lyria) — only when the user asks for it

Music is **opt-in**. Add it only when the user's request calls for it — e.g.
"add lo-fi chill music in the background", "put a soundtrack on it", "give it an
upbeat vibe". When they do, translate their wish into a **Lyria prompt** and pass
`--music`:

```bash
node .agents/skills/record-demo/record-agent.js \
  -q "What's in stock?" \
  -q "Generate a picture of the first item" \
  --wait 30000 --speed 1.5 \
  --music "lo-fi chill hip-hop, mellow Rhodes piano, soft vinyl crackle, relaxed downtempo beat"
```

How it works: the script generates an instrumental track with Google's
**`lyria-002`** model on Vertex AI, then mixes it under the finished video with
ffmpeg. The audio is **matched to the video's length** — it's trimmed (or looped,
since Lyria clips are ~30s) to the exact duration and gets a 1s fade-in and a
2s fade-out that lands on the final frame, so the music starts and ends with the
video. Music is applied **after** `--speed`, so it always matches the final,
sped-up length.

Writing a good Lyria prompt (turn the user's vibe into this):
- **Instrumental only** — Lyria doesn't do vocals. Describe genre, mood,
  instruments, and tempo. e.g. "upbeat corporate synth-pop, bright plucks,
  driving four-on-the-floor beat, optimistic" or "ambient cinematic pad, warm
  strings, slow and hopeful".
- Match the mood to the demo (calm/productive → lo-fi or ambient; exciting
  product reveal → upbeat electronic).
- Use `--music-negative` to exclude things ("vocals, harsh distortion") and
  `--music-volume` to make it more subtle (e.g. `0.4`) or present (`0.8`).

Requirements: `ffmpeg` and an **authenticated gcloud** with a project set — the
lab environment already has both (`gcloud auth login` / ADC and a project).
`lyria-002` runs in `us-central1`; the script targets that region automatically
and reads the project from `GOOGLE_CLOUD_PROJECT` or `gcloud config`. If music
generation fails for any reason, the script **still saves the video** (without
music) and prints why.

## The branded frame

The recorder injects a **"Gemini World Tour"** frame into the page before
recording: a gradient border around the viewport and a title pill at the top. It's
drawn as a `pointer-events: none` overlay, so it never blocks the agent UI, and
it's re-applied if the app re-renders. Styling lives in `./assets/overlay.css`
and the logo in `./assets/logo.svg` — edit those to restyle it. Change the text
with `--title "…"`, or drop the frame entirely with `--no-frame`.

## Tuning the result

- **Replies get cut off / video ends mid-answer:** increase `--wait` (image or
  video generation can take much longer than text — try `--wait 30000` or more).
- **Clip feels slow / too long:** add `--speed 1.5` (or `2`) to trim dead time,
  and/or record fewer turns. Aim for ~20–40s total.
- **Music too loud/quiet:** adjust `--music-volume` (e.g. `0.4` softer, `0.8`
  louder). Change the vibe by rewording the `--music` prompt.
- **Typing looks too fast/slow:** adjust `--delay`.
- **Nothing found / it can't reach the UI:** the frontend or playground isn't
  running, or it's on a different port — start it, or pass the right `--url`.
- **Watch it happen:** add `--headed` to see the browser drive the UI in real time.

## If something's wrong

- **"Could not load <url>":** the UI isn't running or the port is wrong. Start the
  frontend (`python main.py`) or the playground, or fix `--url`/`--app`.
- **"Could not find a chat input":** the page loaded but isn't the chat UI (wrong
  URL), or its input differs from the supported ones (`#input`, the dev UI
  textarea, or a generic text input / contenteditable). Point at the right page.
- **Playwright/Chromium install fails:** the script auto-installs both (globally);
  if the environment blocks it, install manually with `npm install -g playwright
  && npx playwright install chromium`, then re-run.
- **`--speed` had no effect:** `ffmpeg` isn't installed, so the video was saved at
  normal speed. Install ffmpeg and re-run, or leave it as-is.
- **No frame in the video:** the `./assets` files are missing, or you passed
  `--no-frame`. The recording still works — just without branding.
- **Music didn't get added:** the script prints the reason and still saves the
  video. Common causes: `ffmpeg` missing; gcloud not authenticated or no project
  set (`gcloud auth login` + `gcloud config set project …`); or the account
  lacks access to `lyria-002` (Vertex AI / Agent Platform). A `403`/`401` from the
  Lyria API points at auth or access.

## Reference

- Recorder script: `./record-agent.js`
- Frame assets: `./assets/overlay.css`, `./assets/logo.svg`
- Music model: Lyria `lyria-002` on Vertex AI (`us-central1`), instrumental, ~30s clips
- Frontend it targets by default: the `build-agent-frontend` skill (`localhost:8080`)
