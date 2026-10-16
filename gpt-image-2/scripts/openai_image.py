#!/usr/bin/env python3
"""Call OpenAI's Images API directly (BYOK), replacing the RunComfy broker.

Material behavior change vs. the upstream runcomfy-based skill: the `images`
field for the `edit` subcommand is a list of LOCAL FILE PATHS, not public
HTTPS URLs. OpenAI's /v1/images/edits takes multipart file bytes; there is no
URL-reference mode like RunComfy's broker had.

Never logs or prints OPENAI_API_KEY. Reads it only from the environment.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

SIZE_MAP = {
    "1024_1024": "1024x1024",
    "1024_1536": "1024x1536",
    "1536_1024": "1536x1024",
    "1024x1024": "1024x1024",
    "1024x1536": "1024x1536",
    "1536x1024": "1536x1024",
    "auto": "auto",
}

DEFAULT_MODEL = "gpt-image-2"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def parse_size(size: str) -> str:
    try:
        return SIZE_MAP[size]
    except KeyError:
        raise ValueError(
            f"unsupported size {size!r}; expected one of "
            f"{sorted(set(SIZE_MAP))}"
        )


def build_generate_body(prompt: str, size: str, quality: str, model: str = DEFAULT_MODEL) -> dict:
    return {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": parse_size(size),
        "quality": quality,
    }


def build_edit_form(prompt: str, images: list[str], size: str, quality: str, model: str = DEFAULT_MODEL) -> list[str]:
    for image_path in images:
        if not Path(image_path).is_file():
            raise FileNotFoundError(
                f"image ref {image_path!r} is not a local file. "
                "This fork takes local file paths for `images`, not URLs "
                "(see README: material behavior change from the RunComfy "
                "broker, which fetched URLs server-side)."
            )
    form = [
        f"model={model}",
        f"prompt={prompt}",
        f"size={parse_size(size)}",
        f"quality={quality}",
        "n=1",
    ]
    for image_path in images:
        form.append(f"image[]=@{image_path}")
    return form


def run_curl(url: str, api_key: str, body=None, form=None) -> tuple[int, str]:
    """Execute the HTTP call via curl. Mocked in tests — this is the network
    boundary, never the unit under test."""
    cmd = ["curl", "-s", "-m", "240", "-o", "-", "-w", "\n__HTTP__%{http_code}",
           "-H", f"Authorization: Bearer {api_key}"]
    if body is not None:
        tmp = Path(f"/tmp/.openai_image_body_{uuid.uuid4().hex}.json")
        tmp.write_text(json.dumps(body))
        try:
            cmd += ["-H", "Content-Type: application/json", "-X", "POST",
                    url, "-d", f"@{tmp}"]
            out = subprocess.run(cmd, capture_output=True).stdout.decode(errors="replace")
        finally:
            tmp.unlink(missing_ok=True)
    else:
        cmd += ["-X", "POST", url]
        for field in form:
            cmd += ["-F", field]
        out = subprocess.run(cmd, capture_output=True).stdout.decode(errors="replace")
    resp_body, _, code = out.rpartition("\n__HTTP__")
    return int(code or 0), resp_body


def _exit_code_for_status(status: int, body: str) -> int:
    if status == 200:
        return 0
    if status in (401, 403):
        return 77
    if status == 429:
        return 75
    try:
        err = json.loads(body).get("error", {})
    except (json.JSONDecodeError, AttributeError):
        err = {}
    if status == 429 or err.get("code") in ("insufficient_quota", "rate_limit_exceeded"):
        return 75
    if status >= 500:
        return 69
    return 65


def _save_result(body: str, output_dir: str) -> dict:
    parsed = json.loads(body)
    for i, item in enumerate(parsed.get("data", [])):
        b64 = item.get("b64_json")
        if b64:
            out_path = Path(output_dir) / f"result_{i}.png"
            out_path.write_bytes(base64.b64decode(b64))
    return parsed


def main(argv) -> int:
    parser = argparse.ArgumentParser(prog="openai_image")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("generate", "edit"):
        p = sub.add_parser(name)
        p.add_argument("--input", required=True)
        p.add_argument("--output-dir", required=True)
        p.add_argument("--model", default=DEFAULT_MODEL)

    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 64

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("OPENAI_API_KEY is not set in the environment", file=sys.stderr)
        return 77

    try:
        payload = json.loads(args.input)
    except json.JSONDecodeError as e:
        print(f"invalid --input JSON: {e}", file=sys.stderr)
        return 65

    prompt = payload.get("prompt")
    if not prompt:
        print("missing required field: prompt", file=sys.stderr)
        return 64

    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    size = payload.get("size", "auto" if args.command == "edit" else "1024_1024")
    quality = payload.get("quality", "low")

    try:
        if args.command == "generate":
            body = build_generate_body(prompt=prompt, size=size, quality=quality, model=args.model)
            url = f"{base_url}/images/generations"
            status, resp_body = run_curl(url, api_key, body=body)
        else:
            images = payload.get("images")
            if not images:
                print("missing required field: images", file=sys.stderr)
                return 64
            form = build_edit_form(prompt=prompt, images=images, size=size, quality=quality, model=args.model)
            url = f"{base_url}/images/edits"
            status, resp_body = run_curl(url, api_key, form=form)
    except ValueError as e:
        print(f"invalid --input: {e}", file=sys.stderr)
        return 65
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 65

    code = _exit_code_for_status(status, resp_body)
    if code != 0:
        print(f"OpenAI API error (HTTP {status}): {resp_body[:300]}", file=sys.stderr)
        return code

    result = _save_result(resp_body, args.output_dir)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
