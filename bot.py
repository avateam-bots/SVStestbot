"""Python 3.12 Telegram bot. Standard library only, long polling only."""
import json
import logging
import os
from pathlib import Path
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger("bot")


def route(text):
    parts = text.split(maxsplit=1)
    if not parts or parts[0].split("@", 1)[0].lower() != "/start":
        return None
    return "quiz"


def load_content():
    content = json.loads((ROOT / "config/content.json").read_text(encoding="utf-8"))
    prompt = content["confirmation"]
    if not prompt["text"] or not prompt["button"]:
        raise ValueError("Empty confirmation text/button")
    quiz = content["quiz"]
    if not quiz["questions"]:
        raise ValueError("Quiz needs questions")
    for question in quiz["questions"]:
        if not question["text"] or not question["answers"]:
            raise ValueError("Empty quiz question")
        if not 0 <= question["correct"] < len(question["answers"]):
            raise ValueError("Invalid correct answer index")
    quiz["result"].format(score=0, total=len(quiz["questions"]))
    return content


class Telegram:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}/"

    def call(self, method, fields):
        fields = {k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list, bool)) else str(v)
                  for k, v in fields.items()}
        body = urllib.parse.urlencode(fields).encode()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        request = urllib.request.Request(self.base + method, data=body, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            # Never log exception URLs: they contain the bot token.
            raise RuntimeError(f"Telegram HTTP status {error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RuntimeError("Telegram connection failed") from None
        if not result.get("ok"):
            raise RuntimeError("Telegram API request failed")
        return result["result"]


class Bot:
    def __init__(self, api, content):
        self.api, self.content = api, content
        self.sessions = {}
        self.pending = {}

    def question(self, chat_id, session):
        index = session["index"]
        question = self.content["quiz"]["questions"][index]
        buttons = [[{"text": answer, "callback_data": f'q:{session["id"]}:{index}:{i}'}]
                   for i, answer in enumerate(question["answers"])]
        self.api.call("sendMessage", {"chat_id": chat_id,
            "text": f'{self.content["quiz"]["title"]}\n\n{index + 1}/{len(self.content["quiz"]["questions"])}\n{question["text"]}',
            "reply_markup": {"inline_keyboard": buttons}})


    def start_quiz(self, chat_id, key):
        session = {"id": secrets.token_hex(4), "index": 0, "score": 0}
        self.sessions[key] = session
        self.question(chat_id, session)

    def handle(self, update):
        message = update.get("message", {})
        if message and message.get("chat", {}).get("type") == "private":
            destination = route(message.get("text", ""))
            if destination is None:
                return
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            key = (chat_id, user_id)
            self.sessions.pop(key, None)
            nonce = secrets.token_hex(8)
            self.pending[key] = {"id": nonce}
            prompt = self.content["confirmation"]
            self.api.call("sendMessage", {"chat_id": chat_id, "text": prompt["text"],
                "reply_markup": {"inline_keyboard": [[{
                    "text": prompt["button"], "callback_data": f"human:{nonce}"
                }]]}})
            return
        callback = update.get("callback_query")
        if not callback:
            return
        if callback.get("data", "").startswith("human:"):
            chat_id = callback.get("message", {}).get("chat", {}).get("id")
            key = (chat_id, callback["from"]["id"])
            pending = self.pending.get(key)
            valid = pending and callback["data"] == f'human:{pending["id"]}'
            self.api.call("answerCallbackQuery", {"callback_query_id": callback["id"]})
            if valid:
                self.start_quiz(chat_id, key)
                self.pending.pop(key, None)
            return
        if not callback.get("data", "").startswith("q:"):
            return
        chat_id = callback.get("message", {}).get("chat", {}).get("id")
        key = (chat_id, callback["from"]["id"])
        session = self.sessions.get(key)
        try:
            _, session_id, index, answer = callback["data"].split(":")
            index, answer = int(index), int(answer)
            question = self.content["quiz"]["questions"][index]
            valid = (session and session["id"] == session_id and session["index"] == index
                     and 0 <= answer < len(question["answers"]))
        except (ValueError, IndexError):
            valid = False
        self.api.call("answerCallbackQuery", {"callback_query_id": callback["id"],
            "text": "" if valid else self.content["quiz"]["expired"]})
        if not valid:
            return
        session["score"] += int(answer == question["correct"])
        session["index"] += 1
        if session["index"] == len(self.content["quiz"]["questions"]):
            self.sessions.pop(key, None)
            self.api.call("sendMessage", {"chat_id": chat_id,
                "text": self.content["quiz"]["result"].format(score=session["score"], total=session["index"])})
        else:
            self.question(chat_id, session)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set BOT_TOKEN in the container runtime environment")
    api = Telegram(token)
    bot = Bot(api, load_content())
    # Switch to polling without discarding queued updates.
    api.call("deleteWebhook", {"drop_pending_updates": False})
    offset = 0
    LOG.info("Bot started with long polling")
    while True:
        try:
            updates = api.call("getUpdates", {"offset": offset, "timeout": 30,
                "allowed_updates": ["message", "callback_query"]})
            for update in updates:
                try:
                    bot.handle(update)
                except Exception:
                    LOG.error("Could not process update %s", update["update_id"])
                offset = update["update_id"] + 1
        except Exception:
            LOG.warning("Polling failed; retrying in 5 seconds")
            time.sleep(5)


if __name__ == "__main__":
    main()

