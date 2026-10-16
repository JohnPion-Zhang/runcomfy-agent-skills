---
name: gpt-image-edit
displayName: "GPT Image Edit — Direct OpenAI (BYOK)"
description: >
  Edit images with OpenAI GPT Image 2's `/edit` endpoint by calling the
  OpenAI Images API directly with your own API key — no RunComfy account
  needed. Fork of agentspace-so/runcomfy-skills' gpt-image-edit that
  replaces the RunComfy broker with a direct, bring-your-own-key call.
  Bundled with the model's documented prompting patterns (preservation
  language, multilingual in-image text editing, multi-reference up to 10
  images). Triggers on "gpt image edit", "gpt-image-edit", "chatgpt image
  edit", "edit with gpt image 2", or any explicit ask to edit with this
  model.
homepage: https://platform.openai.com/docs/guides/images
license: MIT
---

# GPT Image Edit — Direct OpenAI (BYOK)

> **Fork notice.** This is a derivative of
> [agentspace-so/runcomfy-skills' `gpt-image-edit`](https://github.com/agentspace-so/runcomfy-skills/tree/main/gpt-image-edit)
> (MIT), modified to call OpenAI's Images API directly instead of going
> through the RunComfy broker. It is not affiliated with or endorsed by
> RunComfy. See `scripts/openai_image_edit.py` for the implementation and
> `scripts/test_openai_image_edit.py` for its tests.

OpenAI **GPT Image 2 — `/edit` endpoint**, called **directly against
OpenAI** with your own API key. Strong at preserving identity through
targeted edits and rewriting embedded text in any script.

## Material change from the RunComfy original

The upstream skill's `images` field was a list of **public HTTPS URLs**,
fetched server-side by RunComfy. OpenAI's edit endpoint takes **local image
file bytes** via multipart upload — there is no URL-reference mode. **In
this fork, `images` means local file paths, not URLs.** If you have a URL,
download it to a local file first. Passing a URL fails fast with a clear
error.

## Prerequisites

1. **An OpenAI API key** — bring your own, from
   [platform.openai.com](https://platform.openai.com/api-keys).
2. `export OPENAI_API_KEY=sk-...` — never commit it, never print it.
3. `curl` and Python 3.9+ on PATH.
4. Optional: `OPENAI_BASE_URL` for an OpenAI-compatible endpoint (defaults
   to direct OpenAI).

## Input schema

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `prompt` | string | yes | — | Edit instruction. Lead with preservation, end with the change. |
| `images` | string[] | yes | — | **Local file paths.** First is primary, rest auxiliary. |
| `size` | enum | no | `auto` | `auto` (preserve input ratio), `1024_1024`, `1024_1536`, `1536_1024` (or native `1024x1024` / `1024x1536` / `1536x1024`) |
| `quality` | enum | no | `low` | `low` / `medium` / `high` — bills per call |

## How to invoke

**Single-ref preservation edit:**

```bash
python3 scripts/openai_image_edit.py \
  --input '{
    "prompt": "Keep the person'\''s face, pose, and brand mark unchanged. Replace the background with a soft warm-grey studio sweep.",
    "images": ["/absolute/path/to/portrait.png"]
  }' \
  --output-dir <absolute/path>
```

**Multi-ref composition:**

```bash
python3 scripts/openai_image_edit.py \
  --input '{
    "prompt": "Compose subject from image 1 into the room from image 2. Match the lighting of image 2. Keep image 1 subject identity unchanged.",
    "images": ["/path/subject.png", "/path/room.png"]
  }' \
  --output-dir <absolute/path>
```

The call is synchronous — submit and get a response, no polling. Result
images are decoded from `b64_json` and written to `--output-dir` as
`edit_result_<n>.png`. Stdout is the full parsed result JSON.

## Prompting — what actually works

(Unchanged from the upstream model guidance.)

**Lead with preservation goals.** `"Keep [face / pose / clothing / brand /
framing] unchanged."` then state the change.

**Multilingual text — quote the characters, name the script.** Don't
paraphrase in-image text; quote it exactly.

**Directional language for spatial edits.** "move the headline from
top-right to bottom-center", not "reposition the headline".

**Multi-ref numbering.** "subject from image 1, lighting from image 2."

**Anti-patterns:** long compound edits drift; missing preservation goals
let the model rewrite the face/brand/framing; paraphrasing in-image text
changes it; `size` outside the fixed set 422s.

## Exit codes

| code | meaning |
|---|---|
| 0  | success |
| 64 | bad CLI args or missing required field (e.g. `images`) |
| 65 | bad input JSON / unsupported `size` / local file not found |
| 69 | upstream 5xx |
| 75 | retryable: rate limited or insufficient quota |
| 77 | `OPENAI_API_KEY` missing, or OpenAI rejected it |

## How it works

`scripts/openai_image_edit.py` builds a multipart form from `--input`,
calls `curl` against
`${OPENAI_BASE_URL:-https://api.openai.com/v1}/images/edits` with your
`OPENAI_API_KEY`, and decodes the synchronous response. No polling, no
RunComfy dependency.

## Security & Privacy

- **Key storage**: never written to disk; read from the environment on
  every call. Tested to never appear in stdout/stderr, including error
  paths.
- **Input boundary**: prompt and fields pass through `curl -F`, never
  shell-interpolated.
- **Local files you reference** are read and uploaded as-is.
- **Outbound endpoints**: only `OPENAI_BASE_URL` (default
  `api.openai.com`). No telemetry, no RunComfy dependency.
- **Cost**: every call spends your own OpenAI credits. `quality: "low"`
  is cheapest.
