from datetime import date, datetime
import unittest
from video_publisher.daily_plan import DailyGrant, PlanError, daily_plan, operation_key, PARIS


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.grant = DailyGrant('channel', 'target', date(2026, 11, 17), date(2026, 12, 17), True, True, True)
        self.now = datetime(2026, 11, 17, 5, tzinfo=PARIS)
        self.sha = 'a' * 64

    def plan(self, ops=None, now=None, grant=None, sha=None, youtube='channel', tiktok='target'):
        return daily_plan(grant or self.grant, now or self.now, ops or {}, sha or self.sha, youtube, tiktok)

    def test_two_separate_destinations(self):
        self.assertEqual([p['action'] for p in self.plan()], ['schedule-0700', 'send-inbox'])

    def test_youtube_complete_does_not_hide_tiktok(self):
        youtube = self.plan()[0]
        ops = {youtube['key']: {'binding': youtube['binding'], 'status': 'complete'}}
        self.assertEqual([p['action'] for p in self.plan(ops)], ['skip', 'send-inbox'])

    def test_uncertain_never_uploads_again(self):
        initial = self.plan()
        ops = {p['key']: {'binding': p['binding'], 'status': 'intent'} for p in initial}
        self.assertEqual([p['action'] for p in self.plan(ops)], ['status-only', 'status-only'])

    def test_new_file_cannot_make_second_daily_upload(self):
        youtube = self.plan()[0]
        ops = {youtube['key']: {'binding': youtube['binding'], 'status': 'complete'}}
        with self.assertRaises(PlanError):
            self.plan(ops, sha='b' * 64)

    def test_0700_exact_deadline_no_late_publication(self):
        now = self.now.replace(hour=7)
        self.assertEqual([p['action'] for p in self.plan(now=now)], ['missed-deadline', 'send-inbox'])

    def test_expired_grant_and_unknown_costs_stop(self):
        with self.assertRaises(PlanError):
            self.plan(now=self.now.replace(year=2027))
        grant = DailyGrant('channel', 'target', date(2026, 11, 17), date(2026, 12, 17), True, True)
        with self.assertRaises(PlanError):
            self.plan(grant=grant)

    def test_wrong_live_identity_blocks_plan(self):
        for options in ({'youtube': 'wrong'}, {'tiktok': 'wrong'}):
            with self.assertRaises(PlanError):
                self.plan(**options)

    def test_no_platform_enabled_no_uploads(self):
        grant = DailyGrant('', '', date(2026, 11, 17), date(2026, 12, 17), costs_confirmed=True)
        self.assertEqual(self.plan(grant=grant), [])

    def test_key_ignores_media_hash_not_account_or_day(self):
        self.assertNotEqual(operation_key(date(2026, 11, 17), 'youtube', 'a'), operation_key(date(2026, 11, 17), 'youtube', 'b'))
        self.assertNotEqual(operation_key(date(2026, 11, 17), 'youtube', 'a'), operation_key(date(2026, 11, 18), 'youtube', 'a'))

    def test_naive_time_and_bad_fingerprint_rejected(self):
        with self.assertRaises(PlanError):
            self.plan(now=self.now.replace(tzinfo=None))
        with self.assertRaises(PlanError):
            self.plan(sha='not a fingerprint')
