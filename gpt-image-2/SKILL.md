---
name: gpt-image-2
displayName: "GPT Image 2 — Direct OpenAI (BYOK)"
description: >
  Generate and edit images with OpenAI GPT Image 2 (ChatGPT Images 2.0) by
  calling the OpenAI Images API directly with your own API key — no
  RunComfy account needed. Fork of agentspace-so/runcomfy-skills' gpt-image-2
  that replaces the RunComfy broker with a direct, bring-your-own-key call.
  Documents GPT Image 2's strengths (embedded text, logos, multilingual
  typography, instruction precision), its 3 fixed sizes, edit-with-
  preservation language, and when to route to a sibling instead. Triggers on
  "gpt image 2", "gpt-image-2", "ChatGPT Images 2", "image 2", or any
  explicit ask to generate or edit with this model.
homepage: https://platform.openai.com/docs/guides/images
license: MIT
---

# GPT Image 2 — Direct OpenAI (BYOK)

> **Fork notice.** This is a derivative of
> [agentspace-so/runcomfy-skills' `gpt-image-2`](https://github.com/agentspace-so/runcomfy-skills/tree/main/gpt-image-2)
> (MIT), modified to call OpenAI's Images API directly instead of going
> through the RunComfy broker. It is not affiliated with or endorsed by
> RunComfy. See `scripts/openai_image.py` for the implementation and
> `scripts/test_openai_image.py` for its tests.

OpenAI **GPT Image 2** (ChatGPT Images 2.0), called **directly against
OpenAI** with your own API key. No RunComfy account, no broker hop, no async
polling — the OpenAI endpoint is synchronous.

## Material change from the RunComfy original

The upstream skill's `edit` endpoint took `images: string[]` of **public
HTTPS URLs**, which RunComfy's server fetched for you. OpenAI's own
`/v1/images/edits` takes **local image file bytes** via multipart upload —
there is no URL-reference mode. **In this fork, `images` means local file
paths on this machine, not URLs.** If you have a URL, download it first.
Passing a URL where a local path is expected fails fast with a clear error
(not a silent wrong request).

## Prerequisites

1. **An OpenAI API key** — bring your own, from
   [platform.openai.com](https://platform.openai.com/api-keys).
2. Set it in the environment: `export OPENAI_API_KEY=sk-...` (never commit
   it, never print it, never put it in a shell history you'll share).
3. `curl` and Python 3.9+ on PATH (both already required by this
   environment's other tooling).
4. Optional: `OPENAI_BASE_URL` to point at an OpenAI-compatible endpoint
   instead of `https://api.openai.com/v1` (defaults to direct OpenAI).

## Endpoints + input schema

Two subcommands, same model (`gpt-image-2` by default; override with
`--model`).

### `generate`

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `prompt` | string | yes | — | The positive prompt |
| `size` | enum | no | `1024_1024` | `1024_1024` (1:1), `1024_1536` (2:3 portrait), `1536_1024` (3:2 landscape) — **only these three**, or the native OpenAI `1024x1024` / `1024x1536` / `1536x1024` tokens (both accepted) |
| `quality` | enum | no | `low` | `low` / `medium` / `high` — OpenAI bills per call by quality; `low` is the cheapest sanity-check tier |

### `edit`

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `prompt` | string | yes | — | Natural-language **edit instruction** |
| `images` | string[] | yes | — | **Local file paths** (not URLs — see Material change above) |
| `size` | enum | no | `auto` | `auto` (preserve input ratio), or one of the three fixed sizes above |
| `quality` | enum | no | `low` | as above |

## How to invoke

**Text-to-image:**

```bash
python3 scripts/openai_image.py generate \
  --input '{"prompt": "<user prompt>", "size": "1024_1536", "quality": "low"}' \
  --output-dir <absolute/path>
```

**Edit (local reference file):**

```bash
python3 scripts/openai_image.py edit \
  --input '{
    "prompt": "<edit instruction>",
    "images": ["/absolute/path/to/reference.png"]
  }' \
  --output-dir <absolute/path>
```

The script POSTs synchronously, decodes the returned `b64_json`, and writes
each result image into `--output-dir` as `result_<n>.png`. Stdout is the
full parsed result JSON. Stderr is any error.

## Prompting — what actually works

(Unchanged from the upstream model guidance — these are properties of the
model, not the transport.)

**Be explicit on subject + setting + mood.** "A close-up of a matte ceramic
water bottle on warm linen, soft window light, neutral background" beats
"nice product photo of a bottle."

**Quote embedded text exactly. Keep it short.** Put literal characters in
quotes. For multilingual text, name the script ("Japanese kana", "Cyrillic",
"Arabic right-to-left").

**Iterate one attribute at a time.** Change one thing per refinement pass
(lighting OR background OR pose OR text), keep the rest verbatim.

For **edit** specifically: state preservation goals up front ("keep the
person's pose and face identity unchanged"), use directional language for
spatial edits, and number multiple references in the prompt.

## Exit codes

| code | meaning |
|---|---|
| 0  | success |
| 64 | bad CLI args or missing required field |
| 65 | bad input JSON / unsupported `size` / local file not found |
| 69 | upstream 5xx |
| 75 | retryable: rate limited or insufficient quota — top up credits or retry with backoff |
| 77 | `OPENAI_API_KEY` missing, or OpenAI rejected it (401/403) |

## How it works

1. `scripts/openai_image.py` builds a JSON body (`generate`) or multipart
   form (`edit`) from `--input`.
2. It calls `curl` against `${OPENAI_BASE_URL:-https://api.openai.com/v1}/images/generations`
   or `/images/edits` with your `OPENAI_API_KEY` as a bearer token.
3. The call is synchronous — no polling, no request IDs, no job queue.
4. On HTTP 200, each `data[].b64_json` is decoded and written to
   `--output-dir`.

## What this skill is not

Not a RunComfy client. Not multi-tenant — one `OPENAI_API_KEY` per
invocation, read from the environment. Does not fetch remote image URLs for
you (see Material change).

## Security & Privacy

- **Key storage**: this skill never writes `OPENAI_API_KEY` to disk. It
  reads it from the process environment on every call. The scripts assert
  (and are tested to prove) that the key value never appears in stdout or
  stderr, including in error paths.
- **Input boundary**: the prompt is passed via a temp JSON file (`generate`)
  or `curl -F` fields (`edit`), never shell-interpolated — no
  shell-injection surface from prompt content.
- **Local files you reference** in `images` are read and uploaded as-is;
  treat any reference file from an untrusted source the same way you'd
  treat untrusted input to any other tool.
- **Outbound endpoints**: only `OPENAI_BASE_URL` (default
  `api.openai.com`). No telemetry, no callbacks, no RunComfy dependency.
- **Cost**: every `generate`/`edit` call spends your own OpenAI credits.
  `quality: "low"` is the cheapest tier; use it for sanity checks before a
  `high`-quality run.
