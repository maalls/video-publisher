"""Tests hors ligne du smoke test TTS : aucun appel Google."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import wave

spec = importlib.util.spec_from_file_location(
    "check_tts", Path(__file__).resolve().parents[1] / "scripts" / "check_tts.py")
check_tts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_tts)


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\x00\x00" * 2400)
    return buffer.getvalue()


class TTSSmokeTests(unittest.TestCase):
    def run_check(self, root, args=(), api_error=None):
        client = MagicMock()
        client.synthesize_speech.return_value.audio_content = wav_bytes()
        if api_error:
            client.synthesize_speech.side_effect = api_error
        output = io.StringIO()
        with patch.object(check_tts, "ROOT", root), \
             patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": "secrets/test.json",
                                     "TTS_VOICE": "fr-FR-Wavenet-A"}), \
             patch("sys.argv", ["check_tts.py", *args]), \
             patch("google.cloud.texttospeech.TextToSpeechClient", return_value=client), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = check_tts.main()
        return status, output.getvalue(), client

    def make_credentials(self, root):
        path = root / "secrets" / "test.json"
        path.parent.mkdir()
        path.write_text(json.dumps({"type": "service_account", "private_key": "fake-test-only",
                                   "client_email": "test@example.invalid", "token_uri": "test-only",
                                   "project_id": "test-only"}))

    def test_single_and_rerun_always_call_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_credentials(root)
            for _ in range(2):
                status, output, client = self.run_check(root)
                self.assertEqual(status, 0, output)
                client.synthesize_speech.assert_called_once()
                self.assertIsNone(client.synthesize_speech.call_args.kwargs["retry"])
                self.assertEqual(client.synthesize_speech.call_args.kwargs["timeout"], 60)
                self.assertTrue((root / "output/tts-check/voice-00.wav").is_file())

    def test_all_twelve(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_credentials(root)
            status, output, client = self.run_check(root, ["--all"])
            self.assertEqual(status, 0, output)
            self.assertEqual(client.synthesize_speech.call_count, 12)
            self.assertEqual(len(list((root / "output/tts-check-all").glob("*.wav"))), 12)

    def test_empty_json_no_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_credentials(root)
            (root / "secrets/test.json").write_text("")
            status, output, client = self.run_check(root)
            self.assertEqual(status, 1)
            self.assertIn("JSON vide ou invalide", output)
            client.synthesize_speech.assert_not_called()

    def test_missing_json_no_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            status, output, client = self.run_check(Path(tmp))
            self.assertEqual(status, 1)
            self.assertIn("JSON introuvable", output)
            client.synthesize_speech.assert_not_called()

    def test_api_error_does_not_expose_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_credentials(root)
            status, output, client = self.run_check(root, api_error=ValueError("sensitive-test-marker"))
            self.assertEqual(status, 1)
            self.assertNotIn("sensitive-test-marker", output)
            self.assertNotIn("OK :", output)
            client.synthesize_speech.assert_called_once()


if __name__ == "__main__":
    unittest.main()
