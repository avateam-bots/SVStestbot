import io
import json
import os
import unittest
from unittest.mock import patch
import urllib.parse

import bot


class StartupTests(unittest.TestCase):
    def test_environment_and_polling(self):
        calls = []

        def reply(request, timeout):
            method = request.full_url.rsplit('/', 1)[-1]
            fields = urllib.parse.parse_qs(request.data.decode())
            calls.append((method, fields))
            if method == 'getUpdates':
                raise KeyboardInterrupt
            return io.BytesIO(json.dumps({'ok': True, 'result': True}).encode())

        with patch.dict(os.environ, {'BOT_TOKEN': '123456:audit-placeholder'}), \
                patch('bot.urllib.request.urlopen', side_effect=reply):
            with self.assertRaises(KeyboardInterrupt):
                bot.main()
        self.assertEqual(calls[0], ('deleteWebhook', {'drop_pending_updates': ['false']}))
        self.assertEqual(calls[1][0], 'getUpdates')
        self.assertEqual(calls[1][1]['timeout'], ['30'])
        self.assertEqual(json.loads(calls[1][1]['allowed_updates'][0]), ['message', 'callback_query'])

    def test_missing_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(SystemExit, 'BOT_TOKEN'):
                bot.main()

    def test_image_contains_static_content_without_storage(self):
        content = bot.load_content()
        self.assertNotIn('offers', content)
        self.assertEqual(len(content['quiz']['questions']), 5)
        if str(bot.ROOT) == '/app':
            self.assertFalse(os.path.exists('/data'))
            self.assertFalse(list(bot.ROOT.rglob('*.sqlite3')))
