import json
import tempfile
import unittest
from pathlib import Path
from video_publisher.youtube_accounts import AccountError, describe, load_registry, resolve

CH = "UC" + "a" * 22


class YouTubeAccountsTest(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.reg = self.d / "youtube-accounts.json"

    def write(self, accounts, default=None):
        self.reg.write_text(json.dumps({"default": default, "accounts": accounts}))
        return load_registry(self.reg)

    def test_no_account_chosen_means_refusal(self):
        r = self.write({"a": {"token_file": "a.json", "channel_id": CH}}, default="a")
        with self.assertRaises(AccountError): resolve(r, self.d, None)

    def test_resolves_authorized_account(self):
        (self.d / "a.json").write_text("{}")
        r = self.write({"a": {"token_file": "a.json", "channel_id": CH}})
        self.assertEqual(resolve(r, self.d, "a")[2], CH)

    def test_unverified_channel_and_missing_token_refused(self):
        r = self.write({"m": {"token_file": "m.json", "channel_id": None}})
        with self.assertRaises(AccountError): resolve(r, self.d, "m")
        r = self.write({"m": {"token_file": "m.json", "channel_id": CH}})
        with self.assertRaises(AccountError): resolve(r, self.d, "m")

    def test_rejects_path_traversal_and_bad_ids(self):
        for bad in ({"token_file": "../x.json", "channel_id": CH}, {"token_file": "a.json", "channel_id": "nope"}):
            with self.assertRaises(AccountError): self.write({"a": bad})

    def test_unknown_account_and_describe(self):
        r = self.write({"a": {"token_file": "a.json", "channel_id": None}})
        with self.assertRaises(AccountError): resolve(r, self.d, "zz")
        self.assertFalse(describe(r, self.d)[0]["ready"])


if __name__ == "__main__":
    unittest.main()
