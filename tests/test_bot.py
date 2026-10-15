import unittest
from bot import Bot, load_content, route


class FakeAPI:
    def __init__(self):
        self.calls = []

    def call(self, method, fields, photo=None):
        self.calls.append((method, fields, photo))


class BotTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()
        self.bot = Bot(self.api, load_content())

    def start(self, text, confirm=True):
        self.bot.handle({"message": {"chat": {"id": 1, "type": "private"}, "from": {"id": 2}, "text": text}})
        if confirm:
            self.confirm()

    def confirm(self):
        self.answer("human:" + self.bot.pending[(1, 2)]["id"])


    def answer(self, data):
        self.bot.handle({"callback_query": {"id": "test", "from": {"id": 2},
            "message": {"chat": {"id": 1}}, "data": data}})

    def test_all_start_parameters_open_same_quiz(self):
        for command in ("/start", "/start start", "/start india", "/start egypt", "/start Iran", "/start unknown"):
            self.assertEqual(route(command), "quiz")
            self.start(command, confirm=False)
            method, fields, _ = self.api.calls[-1]
            self.assertEqual(method, "sendMessage")
            self.assertEqual(fields["text"], self.bot.content["confirmation"]["text"])
            self.assertNotIn((1, 2), self.bot.sessions)
            self.confirm()
            self.assertIn("1/5", self.api.calls[-1][1]["text"])
        self.assertIsNone(route("hello"))

    def test_stale_and_duplicate_confirmation(self):
        self.start("/start", confirm=False)
        old = "human:" + self.bot.pending[(1, 2)]["id"]
        self.start("/start", confirm=False)
        count = len(self.api.calls)
        self.answer(old)
        self.assertEqual(len(self.api.calls), count + 1)
        self.assertNotIn((1, 2), self.bot.sessions)
        current = "human:" + self.bot.pending[(1, 2)]["id"]
        self.confirm()
        count = len(self.api.calls)
        self.answer(current)
        self.assertEqual(len(self.api.calls), count + 1)

    def test_complete_quiz_and_reject_duplicate(self):
        self.start("/start start")
        session_id = self.bot.sessions[(1, 2)]["id"]
        for index, question in enumerate(self.bot.content["quiz"]["questions"]):
            data = f'q:{session_id}:{index}:{question["correct"]}'
            self.answer(data)
            count = len(self.api.calls)
            self.answer(data)
            self.assertEqual(len(self.api.calls), count + 1)
            self.assertEqual(self.api.calls[-1][0], "answerCallbackQuery")
        results = [fields["text"] for method, fields, _ in self.api.calls if method == "sendMessage"]
        self.assertIn("Quiz complete! Your score: 5/5", results)
        self.assertNotIn((1, 2), self.bot.sessions)

    def test_old_session_and_invalid_answer(self):
        self.start("/start")
        old = self.bot.sessions[(1, 2)]["id"]
        self.start("/start")
        self.answer(f"q:{old}:0:0")
        current = self.bot.sessions[(1, 2)]
        self.answer(f'q:{current["id"]}:0:-1')
        self.assertEqual(current["index"], 0)


if __name__ == "__main__":
    unittest.main()
