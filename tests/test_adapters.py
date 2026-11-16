from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from video_publisher.core import publish_time, save_json
from video_publisher.publishers.tiktok import TikTokSandbox
from video_publisher.publishers.youtube import upload


class AdapterTests(unittest.TestCase):
    def test_tiktok_consent_guard(self):
        adapter = TikTokSandbox('test-only-not-a-secret')
        with patch.object(adapter, 'creator_info') as query:
            with self.assertRaises(ValueError):
                adapter.post_self_only(Path('none.mp4'), 'test', 75,
                    selected_privacy='SELF_ONLY', explicit_consent=False,
                    compliant_ui_ready=False, journal=Path('state.json'))
            query.assert_not_called()

    def test_youtube_completed_journal_no_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp)/'journal.json'
            save_json(journal, {'status':'complete', 'video_id':'already-uploaded'})
            with patch('googleapiclient.discovery.build') as build:
                result = upload(Path('none.mp4'), {}, publish_time(date(2030,1,1)), journal)
                self.assertEqual(result['video_id'], 'already-uploaded')
                build.assert_not_called()

    def test_youtube_uncertain_journal_no_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp)/'journal.json'
            save_json(journal, {'status':'started'})
            with patch('googleapiclient.discovery.build') as build:
                with self.assertRaises(RuntimeError):
                    upload(Path('none.mp4'), {}, publish_time(date(2030,1,1)), journal)
                build.assert_not_called()

    def test_google_sdk_schema_constructs(self):
        from google.genai import types
        config = types.GenerateContentConfig(response_mime_type='application/json',
            response_schema={'type':'object','properties':{'date':{'type':'string'}}})
        options = types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))
        self.assertEqual(config.response_mime_type, 'application/json')
        self.assertEqual(options.retry_options.attempts, 1)

    def test_youtube_wrong_channel_blocks_insert(self):
        with tempfile.TemporaryDirectory() as tmp:
            youtube = MagicMock()
            youtube.channels.return_value.list.return_value.execute.return_value = {'items':[{'id':'UC-other'}]}
            creds = MagicMock(expired=False)
            with patch.dict('os.environ', {'YOUTUBE_TOKEN_FILE':'not-real.json', 'YOUTUBE_CHANNEL_ID':'UC-target'}), \
                 patch('google.oauth2.credentials.Credentials.from_authorized_user_file', return_value=creds), \
                 patch('googleapiclient.discovery.build', return_value=youtube):
                with self.assertRaises(ValueError):
                    upload(Path('none.mp4'), {}, publish_time(date(2030,1,1)), Path(tmp)/'state.json')
                youtube.videos.assert_not_called()
                self.assertFalse((Path(tmp)/'state.json').exists())

    def test_youtube_private_upload_and_final_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            youtube = MagicMock()
            youtube.channels.return_value.list.return_value.execute.return_value = {'items':[{'id':'UC-target'}]}
            youtube.videos.return_value.insert.return_value.next_chunk.return_value = (None, {'id':'mock-video', 'status':{'privacyStatus':'private'}})
            youtube.videos.return_value.list.return_value.execute.return_value = {'items':[{'status':{'privacyStatus':'private'}}]}
            creds = MagicMock(expired=False)
            journal = Path(tmp)/'state.json'
            with patch.dict('os.environ', {'YOUTUBE_TOKEN_FILE':'not-real.json', 'YOUTUBE_CHANNEL_ID':'UC-target'}), \
                 patch('google.oauth2.credentials.Credentials.from_authorized_user_file', return_value=creds), \
                 patch('googleapiclient.discovery.build', return_value=youtube), \
                 patch('googleapiclient.http.MediaFileUpload'):
                receipt = upload(Path('none.mp4'), {'title':'Test'}, publish_time(date(2030,1,1)), journal, private_test=True)
                self.assertTrue(receipt['verified'])
                body = youtube.videos.return_value.insert.call_args.kwargs['body']
                self.assertNotIn('publishAt', body['status'])
                self.assertEqual(body['status']['privacyStatus'], 'private')
                self.assertTrue(journal.exists())

    def test_youtube_schedule_upload_body_and_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            youtube = MagicMock()
            youtube.channels.return_value.list.return_value.execute.return_value = {'items':[{'id':'UC-target'}]}
            youtube.videos.return_value.insert.return_value.next_chunk.return_value = (None, {'id':'mock-video'})
            youtube.videos.return_value.list.return_value.execute.return_value = {'items':[{'status':{'privacyStatus':'private','publishAt':'2030-01-01T06:00:00Z'}}]}
            with patch.dict('os.environ', {'YOUTUBE_TOKEN_FILE':'not-real.json', 'YOUTUBE_CHANNEL_ID':'UC-target'}), \
                 patch('google.oauth2.credentials.Credentials.from_authorized_user_file', return_value=MagicMock(expired=False)), \
                 patch('googleapiclient.discovery.build', return_value=youtube), \
                 patch('googleapiclient.http.MediaFileUpload'):
                receipt = upload(Path('none.mp4'), {'title':'Test'}, publish_time(date(2030,1,1)), Path(tmp)/'state.json')
                self.assertTrue(receipt['verified'])
                self.assertEqual(youtube.videos.return_value.insert.call_args.kwargs['body']['status']['publishAt'], '2030-01-01T06:00:00Z')
