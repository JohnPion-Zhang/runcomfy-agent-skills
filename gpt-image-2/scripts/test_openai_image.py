"""Unit tests for openai_image.py. Stdlib unittest only, no network.

Run: python3 -m unittest gpt-image-2/scripts/test_openai_image.py -v
(or from this scripts/ dir: python3 -m unittest test_openai_image -v)
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
import openai_image as mod  # noqa: E402


class ParseSizeTests(unittest.TestCase):
    def test_runcomfy_enum_square(self):
        self.assertEqual(mod.parse_size("1024_1024"), "1024x1024")

    def test_native_openai_token_passthrough(self):
        self.assertEqual(mod.parse_size("1024x1024"), "1024x1024")

    def test_auto_passthrough(self):
        self.assertEqual(mod.parse_size("auto"), "auto")

    def test_unsupported_size_raises(self):
        with self.assertRaises(ValueError):
            mod.parse_size("2048_2048")


class BuildGenerateBodyTests(unittest.TestCase):
    def test_body_shape(self):
        body = mod.build_generate_body(prompt="x", size="1024_1536", quality="low")
        self.assertEqual(
            body,
            {
                "model": "gpt-image-2",
                "prompt": "x",
                "n": 1,
                "size": "1024x1536",
                "quality": "low",
            },
        )


class BuildEditFormTests(unittest.TestCase):
    def test_form_contains_model_prompt_size_quality_and_images_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.png"
            b = Path(d) / "b.png"
            a.write_bytes(b"x")
            b.write_bytes(b"y")
            form = mod.build_edit_form(
                prompt="x", images=[str(a), str(b)], size="auto", quality="low"
            )
        self.assertIn("model=gpt-image-2", form)
        self.assertIn("prompt=x", form)
        self.assertIn("size=auto", form)
        self.assertIn("quality=low", form)
        image_args = [f for f in form if f.startswith("image[]=@")]
        self.assertEqual(image_args, [f"image[]=@{a}", f"image[]=@{b}"])

    def test_missing_local_file_raises_file_not_found(self):
        # Material behavior change: a URL (not a local path) must fail loudly,
        # not silently 400 against OpenAI.
        with self.assertRaises(FileNotFoundError):
            mod.build_edit_form(
                prompt="x",
                images=["https://example.com/not-a-local-file.png"],
                size="auto",
                quality="low",
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
        with patch.object(mod, "run_curl") as mock_curl:
            code, out, err = self._run(
                ["generate", "--input", '{"prompt":"x"}', "--output-dir", "/tmp"]
            )
        self.assertEqual(code, 77)
        self.assertEqual(mock_curl.call_count, 0)
        self.assertIn("OPENAI_API_KEY", err)

    def test_malformed_input_json_exits_65(self):
        os.environ["OPENAI_API_KEY"] = "sk-test"
        with patch.object(mod, "run_curl") as mock_curl:
            code, out, err = self._run(
                ["generate", "--input", "{not json", "--output-dir", "/tmp"]
            )
        self.assertEqual(code, 65)
        self.assertEqual(mock_curl.call_count, 0)

    def test_missing_prompt_field_exits_64(self):
        os.environ["OPENAI_API_KEY"] = "sk-test"
        with patch.object(mod, "run_curl") as mock_curl:
            code, out, err = self._run(
                ["generate", "--input", "{}", "--output-dir", "/tmp"]
            )
        self.assertEqual(code, 64)
        self.assertEqual(mock_curl.call_count, 0)

    def test_success_decodes_and_writes_file_and_prints_json(self):
        os.environ["OPENAI_API_KEY"] = "sk-test"
        fake_body = json.dumps({"data": [{"b64_json": "eA=="}]})  # b"x"
        with tempfile.TemporaryDirectory() as d:
            with patch.object(mod, "run_curl", return_value=(200, fake_body)) as mock_curl:
                code, out, err = self._run(
                    ["generate", "--input", '{"prompt":"x"}', "--output-dir", d]
                )
            self.assertEqual(code, 0)
            self.assertEqual(mock_curl.call_count, 1)
            written = list(Path(d).glob("*.png"))
            self.assertEqual(len(written), 1)
            self.assertEqual(written[0].read_bytes(), b"x")
        self.assertIn('"data"', out)

    def test_insufficient_quota_exits_75_no_file_no_key_leak(self):
        os.environ["OPENAI_API_KEY"] = "sk-test-secret-value"
        fake_body = json.dumps({"error": {"code": "insufficient_quota"}})
        with tempfile.TemporaryDirectory() as d:
            with patch.object(mod, "run_curl", return_value=(429, fake_body)):
                code, out, err = self._run(
                    ["generate", "--input", '{"prompt":"x"}', "--output-dir", d]
                )
            self.assertEqual(code, 75)
            self.assertEqual(list(Path(d).glob("*")), [])
        self.assertNotIn("sk-test-secret-value", out)
        self.assertNotIn("sk-test-secret-value", err)

    def test_unauthorized_exits_77(self):
        os.environ["OPENAI_API_KEY"] = "sk-test"
        with patch.object(mod, "run_curl", return_value=(401, "{}")):
            code, out, err = self._run(
                ["generate", "--input", '{"prompt":"x"}', "--output-dir", "/tmp"]
            )
        self.assertEqual(code, 77)

    def test_server_error_exits_69(self):
        os.environ["OPENAI_API_KEY"] = "sk-test"
        with patch.object(mod, "run_curl", return_value=(500, "{}")):
            code, out, err = self._run(
                ["generate", "--input", '{"prompt":"x"}', "--output-dir", "/tmp"]
            )
        self.assertEqual(code, 69)


if __name__ == "__main__":
    unittest.main()
