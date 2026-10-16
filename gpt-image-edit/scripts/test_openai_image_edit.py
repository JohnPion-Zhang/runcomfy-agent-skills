"""Unit tests for openai_image_edit.py. Stdlib unittest only, no network.

Edit-only sibling of gpt-image-2/scripts/test_openai_image.py — duplicated
deliberately so this skill stays independently installable (see SPEC).
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))
import openai_image_edit as mod  # noqa: E402


class ParseSizeTests(unittest.TestCase):
    def test_runcomfy_enum_square(self):
        self.assertEqual(mod.parse_size("1024_1024"), "1024x1024")

    def test_auto_passthrough(self):
        self.assertEqual(mod.parse_size("auto"), "auto")

    def test_unsupported_size_raises(self):
        with self.assertRaises(ValueError):
            mod.parse_size("2048_2048")


class BuildEditFormTests(unittest.TestCase):
    def test_form_contains_model_prompt_size_quality_and_images_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.png"
            a.write_bytes(b"x")
            form = mod.build_edit_form(prompt="x", images=[str(a)], size="auto", quality="low")
        self.assertIn("image[]=@" + str(a), form)

    def test_missing_local_file_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            mod.build_edit_form(
                prompt="x", images=["https://example.com/x.png"], size="auto", quality="low"
            )


class CliTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, {}, clear=False)
        self.env_patch.start()
        os.environ.pop("OPENAI_API_KEY", None)

    def tearDown(self):
        self.env_patch.stop()

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = mod.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_missing_api_key_exits_77_and_makes_no_call(self):
        with tempfile.TemporaryDirectory() as d:
            ref = Path(d) / "ref.png"
            ref.write_bytes(b"x")
            with patch.object(mod, "run_curl") as mock_curl:
                code, out, err = self._run(
                    ["--input", json.dumps({"prompt": "x", "images": [str(ref)]}),
                     "--output-dir", d]
                )
        self.assertEqual(code, 77)
        self.assertEqual(mock_curl.call_count, 0)

    def test_success_decodes_and_writes_file(self):
        os.environ["OPENAI_API_KEY"] = "sk-test"
        fake_body = json.dumps({"data": [{"b64_json": "eA=="}]})
        with tempfile.TemporaryDirectory() as d:
            ref = Path(d) / "ref.png"
            ref.write_bytes(b"x")
            with patch.object(mod, "run_curl", return_value=(200, fake_body)) as mock_curl:
                code, out, err = self._run(
                    ["--input", json.dumps({"prompt": "x", "images": [str(ref)]}),
                     "--output-dir", d]
                )
            self.assertEqual(code, 0)
            self.assertEqual(mock_curl.call_count, 1)
            written = [p for p in Path(d).glob("*.png") if p != ref]
            self.assertEqual(len(written), 1)

    def test_missing_images_field_exits_64(self):
        os.environ["OPENAI_API_KEY"] = "sk-test"
        with patch.object(mod, "run_curl") as mock_curl:
            code, out, err = self._run(
                ["--input", json.dumps({"prompt": "x"}), "--output-dir", "/tmp"]
            )
        self.assertEqual(code, 64)
        self.assertEqual(mock_curl.call_count, 0)

    def test_insufficient_quota_exits_75(self):
        os.environ["OPENAI_API_KEY"] = "sk-test-secret"
        fake_body = json.dumps({"error": {"code": "insufficient_quota"}})
        with tempfile.TemporaryDirectory() as d:
            ref = Path(d) / "ref.png"
            ref.write_bytes(b"x")
            with patch.object(mod, "run_curl", return_value=(429, fake_body)):
                code, out, err = self._run(
                    ["--input", json.dumps({"prompt": "x", "images": [str(ref)]}),
                     "--output-dir", d]
                )
            self.assertEqual(code, 75)
        self.assertNotIn("sk-test-secret", out)
        self.assertNotIn("sk-test-secret", err)


if __name__ == "__main__":
    unittest.main()
