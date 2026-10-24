---
name: enable-a2ui
description: Make an ADK agent emit A2UI so its replies render as rich display UI (cards, tables built from rows/columns, and images from a public URL) in the ADK dev UI (adk web) instead of plain text. Use when the user wants to add A2UI to their agent, render cards or tables in adk web, show an image inside a card, or when A2UI shows up as raw JSON or a blank card. Ships a ready-made a2ui_utils.py (the after_model_callback adk web's renderer needs) in ./template. Display-only in adk web (buttons, actions, and modals don't function); shipping A2UI to a custom production frontend is a separate concern.
---

# Enable A2UI (renders in adk web)

Make an ADK agent return **A2UI** so `adk web` renders cards instead of plain text.
You need **both** of these or you'll just see raw JSON:

1. A **system prompt** that teaches the model to emit A2UI JSON (`A2uiSchemaManager`).
2. An **`after_model_callback`** that rewraps that JSON into the format adk web's
   renderer detects — ships ready-made as **`./template/a2ui_utils.py`**. Copy it,
   don't rewrite it.

> **Use version `0.8` everywhere.** The callback keys off v0.8 messages
> (`beginRendering`, `surfaceUpdate`). v0.9 output won't render.

## Step 0 — Install the SDK

`A2uiSchemaManager` / `BasicCatalog` (Step 2) come from the **`a2ui-agent-sdk`** package:

```bash
uv add "a2ui-agent-sdk>=0.4.0,<0.5.0"
```

- **Name trap:** the package is `a2ui-agent-sdk`, but you **import** it as `a2ui`
  (`from a2ui.schema.manager import ...`). Don't `pip install a2ui` or add a bare
  `a2ui` dep; it doesn't exist, and `uv sync` fails with *"a2ui was not found"*.
- **Use `uv add`, not `uv pip install`.** `uv add` records the dep in
  `pyproject.toml`/`uv.lock`, which `agents-cli deploy` needs. `uv pip install` is
  venv-only: it works in the playground, then the deployed agent crashes with
  `ModuleNotFoundError: No module named 'a2ui'`.
- No need to override the index, hand-list `a2ui-core`, or `git clone` the repo.
  Pin `0.4.x`; newer majors move the import paths used below.

## Step 1 — Copy the callback

Copy `./template/a2ui_utils.py` next to your `agent.py`. It's self-contained (needs
only `google-adk` / `google-genai`).

## Step 2 — Build the system prompt

```python
from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog

schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description="<what your agent is / does>",
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)
```

## Step 3 — Wire the callback onto the agent

```python
from google.adk.agents import Agent
from .a2ui_utils import a2ui_callback

root_agent = Agent(
    model="<your model>",
    name="<your agent>",
    instruction=instruction,
    tools=[...],
    after_model_callback=a2ui_callback,   # <- this is what makes adk web render it
)
```

## Step 4 — Test in adk web

```bash
uv run adk web --port 8080 --allow_origins "*" --reload_agents
```

> Use **`uv run`**, not a bare `adk web`. Bare `adk` uses a global Python that lacks
> your project deps and fails at startup (`cannot import name 'firestore' from
> 'google.cloud'` / `ModuleNotFound`). `uv run` uses the project `.venv`.

Start a **New Session** and ask for something visual — you should see a card, not
JSON. **Turn Token Streaming OFF** first (dev UI gear icon): with it on, adk web
shows the raw streamed JSON and never swaps in the card.

## adk web renderer limits (design around these)

- **Display only.** Buttons, actions, and forms render but do nothing. For real
  interactivity use a custom frontend (`build-agent-frontend`).
- **Supported components:** `Card, Column, Row, Text, Divider, List, Icon, Image`.
  No `Table` or `Heading`: build tables from Rows/Columns of Text, and use `Text`
  + `usageHint` for headings.
- **Images need a public `http(s)` URL.** An `Image` renders inline only when its
  url is a fetchable `https` link. If your agent uploads a generated image to
  a public bucket and passes that URL to the `Image`, it renders inline in the card.
  An image saved only as an artifact has no fetchable URL, so an `Image` pointed at
  the filename shows a broken icon; the callback swaps non-`http(s)` Images for a
  short text note and the image still appears in the Artifacts panel. See
  `build-agent-frontend` for showing images in a custom frontend.
- **Small and flat renders best.** Deep nesting and big cards render blank. The
  callback drops broken surfaces (invalid JSON, undefined root, dangling refs) and
  shows a short fallback instead.
- **The renderer is flaky:** even a valid surface sometimes renders blank. That's
  an adk-web bug, not your agent.

## Troubleshooting

| What you see | Most likely fix |
| --- | --- |
| `ModuleNotFoundError: No module named 'a2ui'` (locally) | SDK not installed — run `uv add "a2ui-agent-sdk>=0.4.0,<0.5.0"` (Step 0). Import is `a2ui`, package is `a2ui-agent-sdk` |
| Works locally but the **deployed** agent errors `No module named 'a2ui'` | You used `uv pip install` (venv-only). Run `uv add "a2ui-agent-sdk>=0.4.0,<0.5.0"` so it's in `pyproject.toml`, then redeploy |
| `uv sync` fails: `a2ui was not found in the package registry` | You added the wrong name. Remove `a2ui` from deps; use `a2ui-agent-sdk` instead (Step 0) |
| Raw JSON while it types | Token Streaming is ON — turn it off (gear), hard-refresh, New Session |
| Raw JSON (not streaming) | Callback not wired (`after_model_callback=a2ui_callback`), or wrong version (use `0.8`) |
| Blank card | Surface too big/complex — ask for something simpler; or stuck UI state — hard-refresh + New Session |

## Reference

- Template: `./template/a2ui_utils.py` (the `after_model_callback`)
- ADK A2UI integration: https://adk.dev/integrations/a2ui/
- A2UI spec (optional): https://a2ui.org/
