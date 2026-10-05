"""Test-wide isolation from the developer's real .env.

cli.main() and whatsapp_webhook (at import time) call load_dotenv(), which copies the real .env --
AWS profile, API keys, WhatsApp/Twilio tokens -- into os.environ for every test that runs after
it. On CI there is no .env, so tests passed there and failed (or worse, reached real services)
locally depending on test order. conftest.py is imported before any test module, so replacing
dotenv.load_dotenv here also covers the `from dotenv import load_dotenv` bindings in src/.
"""

import dotenv


def _no_dotenv(*args, **kwargs):
    return False


dotenv.load_dotenv = _no_dotenv
