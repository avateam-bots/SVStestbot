"""Two-step Telegram funnel, using only the Python standard library."""
import json
import logging
import os
from pathlib import Path
import signal
import threading
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger("bot")


def language(code):
    return "hi" if (code or "").lower().replace("_", "-").split("-")[0] == "hi" else "en"


def load_config():
    config = json.loads((ROOT / "config/content.json").read_text(encoding="utf-8"))
    url = urlsplit(config["bonus_url"])
    if url.scheme not in {"http", "https"} or not url.netloc:
        raise ValueError("Set a valid bonus_url in config/content.json")
    for locale in ("en", "hi"):
        content = config["languages"][locale]
        for key, limit in (("confirmation", 4096), ("confirm_button", 64), ("caption", 1024), ("bonus_button", 64)):
            if not isinstance(content[key], str) or not 0 < len(content[key].encode("utf-16-le")) // 2 <= limit:
                raise ValueError(f"Invalid {locale}.{key}")
        image = (ROOT / content["image"]).resolve()
        if not image.is_relative_to(ROOT / "assets") or not image.is_file():
            raise ValueError(f"Invalid image for {locale}")
        if image.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("Image exceeds Telegram's 10 MB limit")
    return config


class APIError(Exception):
    def __init__(self, code, retry_after=0):
        super().__init__(f"Telegram error {code}")
        self.code, self.retry_after = code, retry_after


class Telegram:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}/"

    def call(self, method, photo=None, **params):
        if photo:
            boundary = uuid.uuid4().hex
            parts = []
            for key, value in params.items():
                value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="welcome.png"\r\nContent-Type: image/png\r\n\r\n'.encode() + Path(photo).read_bytes() + b"\r\n")
            body = b"".join(parts) + f"--{boundary}--\r\n".encode()
            content_type = f"multipart/form-data; boundary={boundary}"
        else:
            body = json.dumps(params).encode()
            content_type = "application/json"
        request = urllib.request.Request(self.base + method, data=body, headers={"Content-Type": content_type})
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            try:
                result = json.load(error)
            except (ValueError, OSError):
                raise APIError(error.code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            # Never log exception URLs, which contain the token.
            raise APIError(0) from None
        if not result.get("ok"):
            raise APIError(result.get("error_code", 0), result.get("parameters", {}).get("retry_after", 0))
        return result["result"]


def handle_update(api, config, update):
    message = update.get("message", {})
    if message.get("chat", {}).get("type") == "private" and message.get("text", "").split(" ")[0].split("@")[0] == "/start":
        locale = language(message.get("from", {}).get("language_code"))
        content = config["languages"][locale]
        api.call("sendMessage", chat_id=message["chat"]["id"], text=content["confirmation"], reply_markup={"inline_keyboard": [[{"text": content["confirm_button"], "callback_data": "human:" + locale}]]})
    callback = update.get("callback_query")
    if not callback:
        return
    message = callback.get("message", {})
    if callback.get("data") not in {"human:hi", "human:en"} or message.get("chat", {}).get("type") != "private" or message["chat"]["id"] != callback["from"]["id"]:
        return
    try:
        api.call("answerCallbackQuery", callback_query_id=callback["id"])
    except APIError:
        pass
    # Keep the language selected at Start, even if Telegram settings change.
    locale = callback["data"].split(":")[1]
    content = config["languages"][locale]
    api.call("sendPhoto", chat_id=message["chat"]["id"], photo=ROOT / content["image"], caption=content["caption"], reply_markup={"inline_keyboard": [[{"text": content["bonus_button"], "url": config["bonus_url"]}]]})
    try:
        api.call("editMessageReplyMarkup", chat_id=message["chat"]["id"], message_id=message["message_id"], reply_markup={"inline_keyboard": []})
    except APIError:
        pass


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = load_config()
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN environment variable is required")
    api = Telegram(token)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    api.call("getMe")
    api.call("deleteWebhook", drop_pending_updates=False)
    LOG.info("Bot started (long polling)")
    offset = 0
    while not stop.is_set():
        try:
            updates = api.call("getUpdates", offset=offset, timeout=25, allowed_updates=["message", "callback_query"])
            for update in updates:
                if stop.is_set():
                    break
                try:
                    handle_update(api, config, update)
                except APIError as error:
                    LOG.warning("Update failed: Telegram code %s", error.code)
                    if error.code == 429:
                        stop.wait(max(1, error.retry_after))
                    # A failed individual message must not block other users.
                offset = update["update_id"] + 1
        except APIError as error:
            if error.code in {401, 409}:
                raise SystemExit(f"Telegram error {error.code}: check token or stop other bot instances") from None
            LOG.warning("Polling interrupted: Telegram code %s", error.code)
            stop.wait(max(3, error.retry_after))


if __name__ == "__main__":
    main()
