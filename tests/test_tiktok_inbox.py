import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from video_publisher import tiktok_inbox as tt


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        pending = patch.object(tt, "PENDING_DIR", self.root / "private-pending")
        pending.start()
        self.addCleanup(pending.stop)
        self.video = self.root / "video.mp4"
        self.video.write_bytes(b"fake mp4 bytes")
        self.journal = self.root / "journal.json"
        self.token = {"access_token": "secret-token", "open_id": "expected-account"}

    def test_private_file_permissions(self):
        tt.private_json(self.journal, {"test": "value"})
        self.assertEqual(os.stat(self.journal).st_mode & 0o777, 0o600)

    def test_no_consent_no_network(self):
        with patch.object(tt, "post_json") as post, self.assertRaises(ValueError):
            tt.upload_inbox(self.video, self.token, self.journal)
        post.assert_not_called()
        self.assertFalse(self.journal.exists())

    def test_single_inbox_transfer_and_no_bearer_on_storage(self):
        init = {"publish_id": "inbox-id", "upload_url": "https://open-upload.tiktokapis.com/video/?upload_token=private"}
        with patch.object(tt, "post_json", side_effect=[init, {"status": "SEND_TO_USER_INBOX"}]) as post, \
             patch.object(tt.requests, "put", return_value=Mock(status_code=201)) as put:
            result = tt.upload_inbox(self.video, self.token, self.journal, explicit_consent=True)
        self.assertEqual(result, "SEND_TO_USER_INBOX")
        route, _, payload = post.call_args_list[0].args
        self.assertEqual(route, "post/publish/inbox/video/init/")
        self.assertNotIn("post_info", payload)
        self.assertEqual(payload["source_info"]["source"], "FILE_UPLOAD")
        self.assertNotIn("Authorization", put.call_args.kwargs["headers"])
        self.assertFalse(put.call_args.kwargs["allow_redirects"])
        receipt = tt.read_json(self.journal)
        self.assertNotIn("upload_url", receipt)
        self.assertNotIn("secret-token", self.journal.read_text())

    def test_existing_journal_blocks_second_init(self):
        self.journal.write_text('{}')
        with patch.object(tt, "post_json") as post, self.assertRaises(FileExistsError):
            tt.upload_inbox(self.video, self.token, self.journal, explicit_consent=True)
        post.assert_not_called()

    def test_wrong_storage_host_no_bytes_sent(self):
        init = {"publish_id": "id", "upload_url": "https://attacker.invalid/video/"}
        with patch.object(tt, "post_json", return_value=init), patch.object(tt.requests, "put") as put:
            with self.assertRaises(tt.TikTokError):
                tt.upload_inbox(self.video, self.token, self.journal, explicit_consent=True)
        put.assert_not_called()
        self.assertEqual(tt.read_json(self.journal)["publish_id"], "id")

    def test_unknown_init_retains_intent(self):
        with patch.object(tt, "post_json", side_effect=tt.TikTokError("uncertain")):
            with self.assertRaises(tt.TikTokError):
                tt.upload_inbox(self.video, self.token, self.journal, explicit_consent=True)
        self.assertEqual(tt.read_json(self.journal)["status"], "started")

    def test_storage_error_no_retry(self):
        init = {"publish_id": "id", "upload_url": "https://open-upload.tiktokapis.com/video/"}
        with patch.object(tt, "post_json", return_value=init) as post, \
             patch.object(tt.requests, "put", side_effect=tt.requests.Timeout("secret URL")) as put:
            with self.assertRaises(tt.TikTokError) as error:
                tt.upload_inbox(self.video, self.token, self.journal, explicit_consent=True)
        self.assertNotIn("secret URL", str(error.exception))
        self.assertEqual(post.call_count, 1)
        self.assertEqual(put.call_count, 1)

    def test_status_wrong_account_and_missing_id(self):
        for receipt in ({"open_id": "other", "publish_id": "id"}, {"open_id": "expected-account"}):
            tt.private_json(self.journal, receipt)
            with patch.object(tt, "post_json") as post, self.assertRaises(tt.TikTokError):
                tt.check_status(self.token, self.journal)
            post.assert_not_called()

    def test_status_read_only(self):
        tt.private_json(self.journal, {"open_id": "expected-account", "publish_id": "id"})
        with patch.object(tt, "post_json", return_value={"status": "PUBLISH_COMPLETE"}) as post:
            self.assertEqual(tt.check_status(self.token, self.journal), "PUBLISH_COMPLETE")
        self.assertEqual(post.call_args.args[0], "post/publish/status/fetch/")

    def test_large_mp4_rejected_before_intent(self):
        with self.video.open("wb") as stream:
            stream.truncate(64_000_001)
        with patch.object(tt, "post_json") as post, self.assertRaises(ValueError):
            tt.upload_inbox(self.video, self.token, self.journal, explicit_consent=True)
        self.assertFalse(self.journal.exists())
        post.assert_not_called()

    def test_storage_allowlist(self):
        for url in ("http://open-upload.tiktokapis.com/", "https://evil.open-upload.tiktokapis.com/", "https://user:password@open-upload.tiktokapis.com/", "https://open-upload.tiktokapis.com:4430/"):
            self.assertFalse(tt.upload_url_allowed(url))
        self.assertTrue(tt.upload_url_allowed("https://open-upload.tiktokapis.com/video/?x=value"))

    def test_api_error_safe_machine_code_only(self):
        response = Mock(status_code=403)
        response.json.return_value = {"error": {"code": "scope_not_authorized", "message": "secret URL"}}
        with patch.object(tt.requests, "post", return_value=response):
            with self.assertRaisesRegex(tt.TikTokError, "scope_not_authorized") as error:
                tt.post_json("post/publish/inbox/video/init/", "secret-token", {})
        self.assertNotIn("secret URL", str(error.exception))

    def test_token_scope_check_and_dynamic_expiry(self):
        data = {"access_token": "access", "refresh_token": "refresh", "open_id": "id", "scope": "user.info.basic,video.upload", "expires_in": 42, "refresh_expires_in": 900}
        with patch.object(tt.time, "time", return_value=1000):
            result = tt.store_token(self.journal, data)
        self.assertEqual(result["expires_at"], 1042)
        self.assertEqual(result["refresh_expires_at"], 1900)
        with self.assertRaises(tt.TikTokError):
            tt.store_token(self.journal, {**data, "scope": "video.publish"})

    def test_refresh_rotation_is_persisted(self):
        client = self.root / "client.json"
        tt.private_json(client, {"client_key": "key", "client_secret": "secret"})
        tt.private_json(self.journal, {**self.token, "refresh_token": "old", "expires_at": 0, "refresh_expires_at": time.time() + 1000})
        updated = {**self.token, "refresh_token": "new", "scope": "user.info.basic,video.upload", "expires_in": 100, "refresh_expires_in": 200}
        with patch.object(tt, "token_request", return_value=updated):
            tt.load_token(client, self.journal)
        self.assertEqual(tt.read_json(self.journal)["refresh_token"], "new")

    def test_user_info_matches_oauth_identity(self):
        response = Mock(status_code=200)
        response.json.return_value = {"error": {"code": "ok"}, "data": {"user": {"open_id": "wrong"}}}
        with patch.object(tt.requests, "get", return_value=response), self.assertRaises(tt.TikTokError):
            tt.user_info(self.token)

    def test_callback_csrf_error_and_path(self):
        spec = importlib.util.spec_from_file_location("authorize_tiktok", Path(__file__).parents[1] / "scripts/authorize_tiktok.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.callback_code("/callback/?state=expected&code=abc", "expected"), "abc")
        for path in ("/callback/?state=evil&code=abc", "/wrong?state=expected&code=abc", "/callback/?state=expected&error=denied"):
            with self.assertRaises(ValueError):
                module.callback_code(path, "expected")


class RegionalUploadHostTests(unittest.TestCase):
    def test_documented_regional_and_default_hosts(self):
        for host in ("open-upload.tiktokapis.com", "upload.us.tiktokapis.com", "upload.eu.tiktokapis.com"):
            self.assertTrue(tt.upload_url_allowed("https://" + host + "/video/?upload_token=secret"))

    def test_rejects_suffix_tricks_credentials_ports_and_subdomains(self):
        for url in ("https://upload.us.tiktokapis.com.evil.invalid/", "https://eviltiktokapis.com/",
                    "https://evil.upload.us.tiktokapis.com/", "https://open.tiktokapis.com/",
                    "http://upload.us.tiktokapis.com/", "https://user@upload.us.tiktokapis.com/",
                    "https://upload.us.tiktokapis.com:444/", "https://upload.us.tiktokapis.com:invalid/",
                    "https://upload.us.tiktokapis.com/#fragment"):
            self.assertFalse(tt.upload_url_allowed(url), url)

    def test_status_retains_safe_byte_count_and_blocks_unknown_fields(self):
        with tempfile.TemporaryDirectory() as root:
            journal = Path(root) / "journal.json"
            tt.private_json(journal, {"open_id": "account", "publish_id": "id"})
            with patch.object(tt, "post_json", return_value={"status": "PROCESSING_UPLOAD", "uploaded_bytes": 0, "upload_url": "secret"}):
                tt.check_status({"open_id": "account", "access_token": "secret"}, journal)
            result = tt.read_json(journal)
            self.assertEqual(result["uploaded_bytes"], 0)
            self.assertNotIn("upload_url", result)


class EmptyRetryTests(unittest.TestCase):
    def test_preserves_original_and_creates_distinct_path_without_init(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "video.mp4"
            video.write_bytes(b"video")
            old = Path(root) / "old.json"
            token = {"open_id": "account", "access_token": "secret"}
            tt.private_json(old, {"open_id": "account", "sha256": tt.file_digest(video), "publish_id": "old-id"})
            with patch.object(tt, "post_json", return_value={"status": "PROCESSING_UPLOAD", "uploaded_bytes": 0}) as post:
                new = tt.retry_empty_journal(token, old, video)
            self.assertNotEqual(old, new)
            self.assertFalse(new.exists())
            self.assertEqual(tt.read_json(old)["publish_id"], "old-id")
            self.assertEqual(post.call_args.args[0], "post/publish/status/fetch/")

    def test_refuses_any_bytes_missing_bytes_or_completed(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "v.mp4"
            video.write_bytes(b"v")
            old = Path(root) / "old.json"
            for data in ({"status": "PROCESSING_UPLOAD", "uploaded_bytes": 1}, {"status": "PROCESSING_UPLOAD"}, {"status": "SEND_TO_USER_INBOX", "uploaded_bytes": 0}):
                tt.private_json(old, {"open_id": "a", "sha256": tt.file_digest(video), "publish_id": "id"})
                with patch.object(tt, "post_json", return_value=data), self.assertRaises(tt.TikTokError):
                    tt.retry_empty_journal({"open_id": "a", "access_token": "s"}, old, video)

    def test_refuses_attempted_transfer_or_changed_file_account(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "v.mp4"
            video.write_bytes(b"v")
            old = Path(root) / "old.json"
            for fields in ({"transfer_attempted": True}, {"open_id": "other"}, {"sha256": "wrong"}):
                tt.private_json(old, {"open_id": "a", "sha256": tt.file_digest(video), "publish_id": "id", **fields})
                with patch.object(tt, "post_json") as post, self.assertRaises(tt.TikTokError):
                    tt.retry_empty_journal({"open_id": "a", "access_token": "s"}, old, video)
                post.assert_not_called()


class RetryFreshEvidenceTests(unittest.TestCase):
    def test_omitted_byte_count_cannot_reuse_old_zero(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "v.mp4"
            video.write_bytes(b"v")
            old = Path(root) / "old.json"
            tt.private_json(old, {"open_id": "a", "sha256": tt.file_digest(video), "publish_id": "id", "uploaded_bytes": 0})
            with patch.object(tt, "post_json", return_value={"status": "PROCESSING_UPLOAD"}), self.assertRaises(tt.TikTokError):
                tt.retry_empty_journal({"open_id": "a", "access_token": "s"}, old, video)

    def test_old_attempt_can_only_prepare_one_recovery(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "v.mp4"
            video.write_bytes(b"v")
            old = Path(root) / "old.json"
            tt.private_json(old, {"open_id": "a", "sha256": tt.file_digest(video), "publish_id": "id"})
            with patch.object(tt, "post_json", return_value={"status": "PROCESSING_UPLOAD", "uploaded_bytes": 0}):
                tt.retry_empty_journal({"open_id": "a", "access_token": "s"}, old, video)
                with self.assertRaises(FileExistsError):
                    tt.retry_empty_journal({"open_id": "a", "access_token": "s"}, old, video)


class PendingResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = patch.object(tt, "PENDING_DIR", self.root / "secrets")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.video = self.root / "v.mp4"
        self.video.write_bytes(b"video")
        self.journal = self.root / "state.json"
        self.token = {"open_id": "account", "access_token": "bearer"}
        self.receipt = {"open_id": "account", "sha256": tt.file_digest(self.video), "publish_id": "id", "transfer_attempted": False}
        tt.private_json(self.journal, self.receipt)
        self.url = "https://open-upload-i18n.tiktokapis.com/upload?upload_token=SIGNED_SECRET"
        tt.private_json(tt.pending_path(self.journal), {**self.receipt, "upload_url": self.url, "expires_at": time.time() + 1000})

    def test_observed_exact_host_accepted(self):
        self.assertTrue(tt.upload_url_allowed(self.url))
        self.assertFalse(tt.upload_url_allowed("https://open-upload-i18n.tiktokapis.com.evil.invalid/"))
        self.assertFalse(tt.upload_url_allowed("https://open-upload-random.tiktokapis.com/"))

    def test_same_init_resume_only_status_no_init_then_put(self):
        with patch.object(tt, "post_json", side_effect=[{"status": "PROCESSING_UPLOAD", "uploaded_bytes": 0}, {"status": "SEND_TO_USER_INBOX"}]) as post, patch.object(tt.requests, "put", return_value=Mock(status_code=201)) as put:
            result = tt.resume_pending(self.video, self.token, self.journal, explicit_consent=True)
        self.assertEqual(result, "SEND_TO_USER_INBOX")
        self.assertTrue(all(call.args[0] == "post/publish/status/fetch/" for call in post.call_args_list))
        self.assertEqual(put.call_args.args[0], self.url)
        self.assertNotIn("Authorization", put.call_args.kwargs["headers"])
        self.assertFalse(put.call_args.kwargs["allow_redirects"])
        self.assertFalse(tt.pending_path(self.journal).exists())
        self.assertNotIn("SIGNED_SECRET", self.journal.read_text())

    def test_no_consent_no_request(self):
        with patch.object(tt, "post_json") as post, self.assertRaises(ValueError):
            tt.resume_pending(self.video, self.token, self.journal)
        post.assert_not_called()

    def test_expired_url_no_put(self):
        tt.private_json(tt.pending_path(self.journal), {**self.receipt, "upload_url": self.url, "expires_at": 0})
        with patch.object(tt.requests, "put") as put, self.assertRaises(tt.TikTokError):
            tt.transfer_pending(self.video, self.token, self.journal)
        put.assert_not_called()
        self.assertFalse(tt.pending_path(self.journal).exists())

    def test_attempted_put_blocks_resume(self):
        tt.private_json(self.journal, {**self.receipt, "transfer_attempted": True})
        with patch.object(tt, "post_json") as post, self.assertRaises(tt.TikTokError):
            tt.resume_pending(self.video, self.token, self.journal, explicit_consent=True)
        post.assert_not_called()

    def test_unknown_host_retains_private_credential_only(self):
        pending = {**self.receipt, "upload_url": "https://unknown.invalid/upload?token=SECRET", "expires_at": time.time()+1000}
        tt.private_json(tt.pending_path(self.journal), pending)
        with patch.object(tt.requests, "put") as put, self.assertRaisesRegex(tt.TikTokError, "unknown.invalid") as error:
            tt.transfer_pending(self.video, self.token, self.journal)
        self.assertNotIn("SECRET", str(error.exception))
        self.assertTrue(tt.pending_path(self.journal).exists())
        self.assertEqual(os.stat(tt.pending_path(self.journal)).st_mode & 0o777, 0o600)
        self.assertFalse(tt.read_json(self.journal)["transfer_attempted"])
        put.assert_not_called()

    def test_uncertain_put_removes_credential_blocks_resend(self):
        with patch.object(tt.requests, "put", side_effect=tt.requests.Timeout("SIGNED_SECRET")), self.assertRaises(tt.TikTokError):
            tt.transfer_pending(self.video, self.token, self.journal)
        self.assertFalse(tt.pending_path(self.journal).exists())
        self.assertTrue(tt.read_json(self.journal)["transfer_attempted"])

    def test_missing_legacy_credential_no_init_or_put(self):
        tt.pending_path(self.journal).unlink()
        with patch.object(tt.requests, "put") as put, patch.object(tt, "post_json") as post, self.assertRaises(tt.TikTokError):
            tt.transfer_pending(self.video, self.token, self.journal)
        put.assert_not_called()
        post.assert_not_called()

    def test_fresh_nonzero_refuses_resume(self):
        with patch.object(tt, "post_json", return_value={"status": "PROCESSING_UPLOAD", "uploaded_bytes": 10}), patch.object(tt.requests, "put") as put, self.assertRaises(tt.TikTokError):
            tt.resume_pending(self.video, self.token, self.journal, explicit_consent=True)
        put.assert_not_called()


class PendingRetentionTests(unittest.TestCase):
    def test_cleanup_removes_only_expired_credentials(self):
        with tempfile.TemporaryDirectory() as root, patch.object(tt, "PENDING_DIR", Path(root)):
            expired, valid = Path(root)/"expired.json", Path(root)/"valid.json"
            tt.private_json(expired, {"expires_at": 0, "upload_url": "secret"})
            tt.private_json(valid, {"expires_at": time.time()+1000, "upload_url": "secret"})
            tt.cleanup_expired_pending()
            self.assertFalse(expired.exists())
            self.assertTrue(valid.exists())

    def test_git_and_artifact_wiring_keeps_pending_out(self):
        root = Path(__file__).parents[1]
        self.assertIn("secrets/", (root/".gitignore").read_text().splitlines())
        workflow = (root/".github/workflows/daily.yml").read_text()
        artifact = workflow.split("name: Livrer", 1)[1].split("- name:", 1)[0]
        self.assertNotIn("secrets", artifact)
        self.assertNotIn("tiktok-pending", artifact)
