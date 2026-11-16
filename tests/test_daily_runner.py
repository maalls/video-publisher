from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from cryptography.fernet import Fernet
from video_publisher.durable_state import StateCodec, StateSession, empty_state, StateError
from video_publisher.daily_plan import PARIS, operation_key, PlanError
from video_publisher.daily_runner import run
from test_durable_state import MemoryCAS


class RunnerTests(unittest.TestCase):
    def setUp(self):
        state = empty_state()
        state['grant'] = dict(version=1, content='daily-french-horoscope', youtube_account='channel',
                              tiktok_account='target', starts_on='2026-11-17', expires_on='2026-12-17',
                              youtube_enabled=True, tiktok_enabled=True, costs_confirmed=True)
        codec = StateCodec(Fernet.generate_key())
        self.store = MemoryCAS(codec.encode(state))
        self.session = StateSession(self.store, codec)
        self.now = datetime(2026,11,17,5,tzinfo=PARIS)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.video = Path(self.tmp.name)/'video.mp4'; self.video.write_bytes(b'video')
        self.generate = Mock(return_value=self.video)
        self.identities = Mock(return_value=('channel','target'))
        self.youtube = Mock(return_value={'video_id':'id'})
        self.tiktok = Mock(return_value={'status':'SEND_TO_USER_INBOX'})

    def run_plan(self):
        return run(self.session,self.now,self.generate,self.identities,self.youtube,self.tiktok)

    def test_success_each_once_repeat_no_effects(self):
        self.assertEqual(self.run_plan(), {'youtube':'complete','tiktok':'complete'})
        self.assertEqual(self.run_plan(), {'status':'already-complete'})
        self.generate.assert_called_once();self.youtube.assert_called_once();self.tiktok.assert_called_once()

    def test_uncertain_youtube_blocks_retry(self):
        self.youtube.side_effect=RuntimeError('network')
        result=self.run_plan()
        self.assertEqual(result, {'youtube':'uncertain','tiktok':'complete'})
        with self.assertRaises(StateError): self.run_plan()
        self.youtube.assert_called_once();self.tiktok.assert_called_once()

    def test_generation_failure_never_charged_again(self):
        self.generate.side_effect=RuntimeError('network')
        with self.assertRaises(RuntimeError): self.run_plan()
        with self.assertRaises(StateError): self.run_plan()
        self.generate.assert_called_once();self.youtube.assert_not_called()

    def test_cost_and_grant_before_any_effect(self):
        self.session.state['grant']['costs_confirmed']=False
        with self.assertRaises(PlanError):self.run_plan()
        self.generate.assert_not_called();self.identities.assert_not_called()

    def test_wrong_live_account_no_generation(self):
        self.identities.return_value=('wrong','target')
        with self.assertRaises(PlanError):self.run_plan()
        self.generate.assert_not_called()

    def test_state_unavailable_no_generation(self):
        self.store.fail=True
        with self.assertRaises(StateError):self.run_plan()
        self.generate.assert_not_called()

    def test_intermediate_receipt_persisted(self):
        def youtube(video,day,grant,persist):
            persist({'video_id':'recovery-id'})
            raise RuntimeError('interrupted')
        self.youtube.side_effect=youtube
        self.assertEqual(self.run_plan()['youtube'],'uncertain')
        key=operation_key(self.now.date(),'youtube','channel')
        self.assertEqual(self.session.state['operations'][key]['receipt']['video_id'],'recovery-id')
