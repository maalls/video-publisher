import os
import unittest
from unittest.mock import patch

from video_publisher.visuals import font


class FontPathTests(unittest.TestCase):
    def test_default_font_names_are_preserved(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch('video_publisher.visuals.ImageFont.truetype', return_value='font') as load:
            self.assertEqual(font(32), 'font')
            self.assertEqual(font(32, bold=True), 'font')
        self.assertEqual([call.args for call in load.call_args_list], [
            ('DejaVuSans.ttf', 32), ('DejaVuSans-Bold.ttf', 32)])

    def test_env_paths_override_and_expand_home(self):
        with patch.dict(os.environ, {
            'FONT_PATH': '~/Library/Fonts/DejaVuSans.ttf',
            'FONT_BOLD_PATH': '~/Library/Fonts/DejaVuSans-Bold.ttf',
        }), patch('video_publisher.visuals.ImageFont.truetype', return_value='font') as load:
            font(32)
            font(32, bold=True)
        self.assertEqual([call.args for call in load.call_args_list], [
            (os.path.expanduser('~/Library/Fonts/DejaVuSans.ttf'), 32),
            (os.path.expanduser('~/Library/Fonts/DejaVuSans-Bold.ttf'), 32)])


if __name__ == '__main__':
    unittest.main()
