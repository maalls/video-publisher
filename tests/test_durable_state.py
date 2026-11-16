import unittest
from cryptography.fernet import Fernet
from video_publisher.durable_state import StateCodec, StateSession, StateError, empty_state


class MemoryCAS:
    def __init__(self, data):
        self.data, self.revision = data, 1
        self.fail = False

    def read(self):
        return self.data, str(self.revision)

    def cas(self, expected, data):
        if self.fail or expected != str(self.revision):
            raise RuntimeError('private provider body must not escape')
        self.data = data
        self.revision += 1
        return str(self.revision)


class DurableTests(unittest.TestCase):
    def setUp(self):
        self.codec = StateCodec(Fernet.generate_key())
        self.store = MemoryCAS(self.codec.encode(empty_state()))
        self.binding = dict(date='2026-11-17', platform='tiktok', account='target', sha256='abc')

    def test_roundtrip_encrypted(self):
        state = empty_state()
        state['tokens']['tiktok'] = {'value': 'private-canary'}
        raw = self.codec.encode(state)
        self.assertNotIn(b'private-canary', raw)
        self.assertEqual(self.codec.decode(raw), state)

    def test_wrong_key_and_corruption_stop(self):
        for raw in (b'bad', self.store.data):
            with self.assertRaises(StateError):
                StateCodec(Fernet.generate_key()).decode(raw)

    def test_claim_persists_before_caller_can_send(self):
        session = StateSession(self.store, self.codec)
        session.claim('daily-tiktok', self.binding)
        self.assertEqual(self.codec.decode(self.store.data)['operations']['daily-tiktok']['status'], 'intent')
        with self.assertRaises(StateError):
            StateSession(self.store, self.codec).claim('daily-tiktok', self.binding)

    def test_concurrent_claim_only_one_wins(self):
        first = StateSession(self.store, self.codec)
        second = StateSession(self.store, self.codec)
        first.claim('daily', self.binding)
        with self.assertRaises(StateError):
            second.claim('daily', self.binding)
        self.assertTrue(second.poisoned)

    def test_failed_write_poisoned_no_retry(self):
        session = StateSession(self.store, self.codec)
        self.store.fail = True
        with self.assertRaises(StateError) as raised:
            session.claim('daily', self.binding)
        self.assertNotIn('private provider', str(raised.exception))
        self.store.fail = False
        with self.assertRaises(StateError):
            session.claim('daily', self.binding)

    def test_completion_never_removes_replay_guard(self):
        session = StateSession(self.store, self.codec)
        session.claim('daily', self.binding)
        session.record('daily', 'complete', {'publish_id': 'id'})
        with self.assertRaises(StateError):
            StateSession(self.store, self.codec).claim('daily', self.binding)

    def test_token_rotation_durable_account_binding(self):
        session = StateSession(self.store, self.codec)
        session.replace_token('tiktok', 'target', {'refresh_token': 'new'})
        self.assertEqual(self.codec.decode(self.store.data)['tokens']['tiktok']['value']['refresh_token'], 'new')
        with self.assertRaises(StateError):
            session.replace_token('tiktok', 'other', {'refresh_token': 'different'})

    def test_missing_state_cannot_bootstrap_implicitly(self):
        self.store.data = b''
        with self.assertRaises(StateError):
            StateSession(self.store, self.codec)

    def test_no_record_without_intent(self):
        with self.assertRaises(StateError):
            StateSession(self.store, self.codec).record('unknown', 'complete', {})


class GitHubStoreTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import Mock
        from video_publisher.durable_state import GitHubStateStore
        self.http = Mock()
        self.store = GitHubStateStore('owner/repo', 'private-canary', session=self.http)
        from unittest.mock import patch
        private_check = patch.object(self.store, '_require_private')
        private_check.start()
        self.addCleanup(private_check.stop)

    def test_read_dedicated_branch(self):
        import base64
        self.http.get.return_value.status_code = 200
        self.http.get.return_value.json.return_value = dict(
            type='file', encoding='base64', size=4, content=base64.b64encode(b'data').decode(), sha='old')
        self.assertEqual(self.store.read(), (b'data', 'old'))
        options = self.http.get.call_args.kwargs
        self.assertEqual(options['params'], {'ref': 'main'})
        self.assertFalse(options['allow_redirects'])

    def test_missing_file_never_bootstraps(self):
        self.http.get.return_value.status_code = 404
        with self.assertRaises(StateError):
            self.store.read()
        self.http.put.assert_not_called()

    def test_cas_conflict_no_retry(self):
        self.http.put.return_value.status_code = 409
        with self.assertRaises(StateError):
            self.store.cas('old', b'ciphertext')
        self.assertEqual(self.http.put.call_count, 1)
        options = self.http.put.call_args.kwargs
        self.assertEqual(options['json']['sha'], 'old')
        self.assertFalse(options['allow_redirects'])
        self.assertNotIn('private-canary', options['json']['message'])

    def test_cas_verifies_exact_blob(self):
        import hashlib
        expected = hashlib.sha1(b'blob 4\0data').hexdigest()
        self.http.put.return_value.status_code = 200
        self.http.put.return_value.json.return_value = {'content': {'sha': expected}}
        self.assertEqual(self.store.cas('old', b'data'), expected)
        self.http.put.return_value.json.return_value = {'content': {'sha': 'other'}}
        with self.assertRaises(StateError):
            self.store.cas('old', b'data')

    def test_redirect_and_invalid_json_stop(self):
        self.http.get.return_value.status_code = 302
        with self.assertRaises(StateError):
            self.store.read()
        self.http.get.return_value.status_code = 200
        self.http.get.return_value.json.side_effect = ValueError('private-canary')
        with self.assertRaises(StateError) as raised:
            self.store.read()
        self.assertNotIn('private-canary', str(raised.exception))

    def test_forbids_other_branch(self):
        from video_publisher.durable_state import GitHubStateStore
        with self.assertRaises(StateError):
            GitHubStateStore('owner/repo', 'token', branch='other')

    def test_public_or_unknown_repo_rejected(self):
        from video_publisher.durable_state import GitHubStateStore
        fresh = GitHubStateStore('owner/repo', 'private-canary', session=self.http)
        for status, payload in [(200, {'private': False}), (404, {}), (200, {})]:
            self.http.get.return_value.status_code = status
            self.http.get.return_value.json.return_value = payload
            with self.assertRaises(StateError):
                fresh.read()
        self.http.put.assert_not_called()


class RefreshIntentTests(unittest.TestCase):
    def test_interrupted_refresh_blocks_another_refresh(self):
        codec=StateCodec(Fernet.generate_key())
        store=MemoryCAS(codec.encode(empty_state()))
        first=StateSession(store,codec)
        first.begin_refresh('tiktok')
        with self.assertRaises(StateError):
            StateSession(store,codec).begin_refresh('tiktok')
        first.replace_token('tiktok','target',{'refresh_token':'new'})
        StateSession(store,codec).begin_refresh('tiktok')
