import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'tales'))
import instagram_unified as m

class CoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.caption = self.root / 'caption.txt'
        self.caption.write_text('Approved fixture')
        self.video = self.root / 'video.mp4'
        self.video.write_bytes(b'fixture-video')
        self.cover = self.root / 'cover.jpg'
        self.cover.write_bytes(b'fixture-cover')
        self.user = {'user_id': '123', 'username': 'example.test'}
        self.token = {'user_id': '123', 'access_token': 'not-real'}
        self.args = argparse.Namespace(action='create', state_dir=str(self.root), video=str(self.video),
            caption_file=str(self.caption), cover=None, video_url='https://example.invalid/video',
            cover_url=None, ai_generated='yes', share_to_feed='yes', execute=True)
        self.target = self.root / ('reel-123-' + m.digest(self.video) + '.json')
    def tearDown(self):
        self.tmp.cleanup()
    def spec(self):
        with patch.object(m, 'validate_video'), patch.object(m, 'validate_cover'):
            return m.plan(self.args, self.user)
    def test_cover_changes_plan_and_bytes_are_bound(self):
        no_cover = self.spec()
        self.args.cover = str(self.cover)
        first = self.spec()
        self.cover.write_bytes(b'different-cover')
        second = self.spec()
        self.assertNotIn('cover_sha256', no_cover)
        self.assertEqual(first['cover_sha256'], __import__('hashlib').sha256(b'fixture-cover').hexdigest())
        self.assertNotEqual(no_cover['plan_sha256'], first['plan_sha256'])
        self.assertNotEqual(first['plan_sha256'], second['plan_sha256'])
    def create(self, spec, verify=None):
        self.args.confirm_plan = spec['plan_sha256']
        with patch.object(m, 'checked', return_value=(self.token,self.user)), patch.object(m, 'plan', return_value=spec), patch.object(m, 'verify_url', side_effect=verify) as check, patch.object(m, 'api', return_value={'id': '456'}) as api, contextlib.redirect_stdout(io.StringIO()):
            m.reel(self.args, {}, self.root/'token.json')
            return check.call_args_list, api.call_args
    def test_create_passes_both_hash_checked_urls(self):
        self.args.cover = str(self.cover)
        self.args.cover_url = 'https://example.invalid/cover'
        spec = self.spec()
        checks, call = self.create(spec)
        self.assertEqual([(x.args) for x in checks], [(self.args.video_url,spec['sha256']), (self.args.cover_url,spec['cover_sha256'])])
        self.assertEqual(call.args[3]['cover_url'], self.args.cover_url)
        self.assertEqual(m.load(self.target)['cover_sha256'], spec['cover_sha256'])
    def test_no_cover_remains_compatible(self):
        spec = self.spec()
        checks, call = self.create(spec)
        self.assertEqual(len(checks), 1)
        self.assertNotIn('cover_url', call.args[3])
    def test_orphan_url_is_rejected_before_intent(self):
        self.args.cover_url = 'https://example.invalid/cover'
        with self.assertRaises(m.Stop): self.create(self.spec())
        self.assertFalse(self.target.exists())
    def test_missing_url_is_rejected_before_intent(self):
        self.args.cover = str(self.cover)
        with self.assertRaises(m.Stop): self.create(self.spec())
        self.assertFalse(self.target.exists())
    def test_bad_remote_cover_hash_never_creates(self):
        self.args.cover = str(self.cover)
        self.args.cover_url = 'https://example.invalid/cover'
        with self.assertRaises(m.Stop): self.create(self.spec(), [None,m.Stop('fixture mismatch')])
        self.assertFalse(self.target.exists())
    def test_validate_cover_rejects_wrong_codec_and_ratio(self):
        for stream in [{'codec_name':'png','width':1080,'height':1920}, {'codec_name':'mjpeg','width':1080,'height':1080}]:
            with patch.object(m.subprocess,'check_output',return_value=json.dumps({'streams':[stream]}).encode()):
                with self.assertRaises(m.Stop): m.validate_cover(self.cover)
    def test_validate_cover_accepts_jpeg_vertical(self):
        with patch.object(m.subprocess,'check_output',return_value=json.dumps({'streams':[{'codec_name':'mjpeg','width':1080,'height':1920}]}).encode()):
            m.validate_cover(self.cover)
    def test_no_extra_extension(self):
        p=self.root/'cover.png'; p.write_bytes(b'fixture')
        with self.assertRaises(m.Stop): m.validate_cover(p)

if __name__ == '__main__': unittest.main()
