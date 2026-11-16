import copy
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from video_publisher.core import (SIGNS, demo_script, validate_script, publish_time,
                                   french_date, save_json, schedule_due)
from video_publisher.metadata import metadata
from video_publisher.cli import main


class CoreTests(unittest.TestCase):
    def test_twelve_signs(self):
        result = demo_script(date(2026, 11, 16))
        self.assertEqual([x['sign'] for x in result['horoscopes']], list(SIGNS))

    def test_wrong_date_rejected(self):
        data = demo_script(date(2026, 11, 16))
        with self.assertRaises(ValueError):
            validate_script(data, date(2026, 11, 17))

    def test_duplicate_sign_rejected(self):
        data = demo_script(date(2026, 11, 16))
        data['horoscopes'][1]['sign'] = 'Bélier'
        with self.assertRaises(ValueError):
            validate_script(data, date(2026, 11, 16))

    def test_long_text_rejected(self):
        data = demo_script(date(2026, 11, 16))
        data['horoscopes'][0]['text'] = 'mot '*20
        with self.assertRaises(ValueError):
            validate_script(data, date(2026, 11, 16))

    def test_control_character_rejected(self):
        data = demo_script(date(2026, 11, 16))
        data['horoscopes'][0]['text'] += '\n'
        with self.assertRaises(ValueError):
            validate_script(data, date(2026, 11, 16))

    def test_publish_winter(self):
        self.assertEqual(publish_time(date(2026, 11, 16)).isoformat(), '2026-11-16T06:00:00+00:00')

    def test_publish_summer(self):
        self.assertEqual(publish_time(date(2026, 7, 16)).isoformat(), '2026-07-16T05:00:00+00:00')

    def test_dst_transition_days(self):
        self.assertEqual(publish_time(date(2026, 3, 29)).hour, 5)
        self.assertEqual(publish_time(date(2026, 10, 25)).hour, 6)

    def test_schedule_gate(self):
        self.assertTrue(schedule_due(datetime(2026, 11, 16, 4, 15, tzinfo=timezone.utc)))
        self.assertFalse(schedule_due(datetime(2026, 11, 16, 3, 15, tzinfo=timezone.utc)))
        self.assertTrue(schedule_due(datetime(2026, 7, 16, 3, 15, tzinfo=timezone.utc)))
        self.assertFalse(schedule_due(datetime(2026, 7, 16, 4, 15, tzinfo=timezone.utc)))

    def test_french_date(self):
        self.assertEqual(french_date(date(2026, 11, 16)), 'lundi 16 novembre 2026')

    def test_timestamps(self):
        data = metadata(date(2026, 11, 16), [{'start':0, 'sign':'Bélier'}, {'start':6.25, 'sign':'Taureau'}])
        self.assertIn('00:00 Bélier\n00:06 Taureau', data['description'])
        self.assertIn('lundi 16 novembre 2026', data['title'])

    def test_atomic_json_unicode(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp)/'state.json'
            save_json(file, {'test':'Bélier'})
            self.assertEqual(json.loads(file.read_text())['test'], 'Bélier')
            self.assertFalse(file.with_suffix('.json.tmp').exists())

    def test_oserror_message_is_logged(self):
        with patch('video_publisher.cli.execute', side_effect=OSError('cannot open resource')), \
             patch('video_publisher.cli.log.error') as error_log, \
             patch('sys.argv', ['video-publisher']):
            with self.assertRaises(SystemExit) as result:
                main()
            self.assertEqual(result.exception.code, 1)
            self.assertIn('cannot open resource', error_log.call_args_list[-1].args)

    def test_demo_upload_blocked(self):
        with patch('sys.argv', ['video-publisher', '--demo', '--publish-youtube']):
            with self.assertRaises(SystemExit) as result:
                main()
            self.assertEqual(result.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
