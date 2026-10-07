import unittest
from unittest.mock import Mock
import bot


class FunnelTests(unittest.TestCase):
    def setUp(self):
        self.config = bot.load_config()
        self.api = Mock()

    def test_language(self):
        for code in ('hi', 'hi-IN', 'HI_in'):
            self.assertEqual(bot.language(code), 'hi')
        for code in (None, '', 'en', 'ru', 'bn', 'hif'):
            self.assertEqual(bot.language(code), 'en')

    def test_start(self):
        for language in ('hi', 'ru', None):
            self.api.reset_mock()
            bot.handle_update(self.api, self.config, {'message': {'chat': {'id': 7, 'type': 'private'}, 'from': {'language_code': language}, 'text': '/start source'}})
            args = self.api.call.call_args
            self.assertEqual(args.args, ('sendMessage',))
            buttons = args.kwargs['reply_markup']['inline_keyboard']
            self.assertEqual(len(buttons), 1)
            self.assertEqual(len(buttons[0]), 1)
            self.assertEqual(buttons[0][0]['callback_data'], 'human:' + bot.language(language))

    def test_confirm(self):
        for language in ('hi', 'en'):
            self.api.reset_mock()
            bot.handle_update(self.api, self.config, {'callback_query': {'id': 'q', 'data': 'human:' + language, 'from': {'id': 7}, 'message': {'chat': {'id': 7, 'type': 'private'}, 'message_id': 2}}})
            calls = self.api.call.call_args_list
            self.assertEqual([c.args[0] for c in calls], ['answerCallbackQuery', 'sendPhoto', 'editMessageReplyMarkup'])
            offer = calls[1].kwargs
            self.assertTrue(offer['photo'].is_file())
            self.assertEqual(offer['caption'], self.config['languages'][language]['caption'])
            self.assertEqual(offer['reply_markup']['inline_keyboard'], [[{'text': self.config['languages'][language]['bonus_button'], 'url': self.config['bonus_url']}]])

    def test_other_messages_ignored(self):
        bot.handle_update(self.api, self.config, {'message': {'chat': {'id': 7, 'type': 'private'}, 'text': 'hello'}})
        bot.handle_update(self.api, self.config, {'message': {'chat': {'id': 7, 'type': 'group'}, 'text': '/start'}})
        self.api.call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
