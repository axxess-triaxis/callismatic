"""Generates a handful of short synthetic voicemail recordings for the demo.

Uses an offline TTS engine (pyttsx3, wrapping the OS's own speech engine) so
producing demo *input* audio needs no extra API key. The pipeline itself
still transcribes these with real AssemblyAI -- nothing about the
transcription step is simulated, only the input audio is.

Each filename embeds a fake E.164 phone number (see
callismatic.triage.caller_number_from_filename) so the demo can exercise
caller-number-driven behavior -- blocking, callback -- without a live phone
line. Run: `python demo/generate_samples.py`
"""

from __future__ import annotations

from pathlib import Path

import pyttsx3

OUT_DIR = Path(__file__).parent.parent / "sample_voicemails"

SCRIPTS = {
    "scam_gift_card_+15550001111.wav": (
        "This is an urgent automated notice from the Federal Fraud Prevention Department. "
        "We have detected suspicious activity linked to your identity. Your account will be "
        "suspended within twenty four hours unless you verify your information. To resolve "
        "this immediately, purchase a five hundred dollar Google Play gift card and call back "
        "with the code. Failure to comply will result in a warrant for your arrest."
    ),
    "new_lead_kitchen_remodel_+15550002222.wav": (
        "Hi, my name is Daniel Ortiz. I got your number from a friend who said you handle "
        "kitchen remodels. We're looking to redo our kitchen sometime this fall, probably a "
        "mid-size budget. Could someone call me back to talk through what's possible and maybe "
        "set up a time to look at the space? Thanks."
    ),
    "appointment_confirm_+15550003333.wav": (
        "Hi, this is the front desk at Lakeside Dental calling to confirm your cleaning "
        "appointment tomorrow at two thirty PM. If that time still works for you, no need to "
        "do anything. If you need to reschedule, just give us a call back. Thanks, see you soon."
    ),
    "important_client_contract_+15550004444.wav": (
        "Hi, this is Priya from Summit Partners. We got the draft agreement you sent over, but "
        "legal flagged a couple of clauses around the liability cap that we need to discuss "
        "before we can sign. Can you give me a call back today or tomorrow? It's fairly time "
        "sensitive since we're hoping to close this out by end of week."
    ),
    "package_delivery_+15550005555.wav": (
        "Hi, this is Sarah from Metro Package Delivery. We attempted to deliver your package "
        "today but no one was available to sign for it. Please call us back to let us know if "
        "it's okay to leave it at the door next time, or if you'd like us to try again tomorrow "
        "between nine and noon."
    ),
    # SerpApi India Hackathon 2026 samples: real, public organisations (so web intelligence
    # has something real to find) but fictional people and fictional +1555 numbers -- no real
    # person's name or number appears anywhere in the repo or the demo.
    "trai_disconnection_scam_+15550007777.wav": (
        "This is a call from TRAI, the Telecom Regulatory Authority of India. Your mobile number "
        "will be disconnected within two hours because illegal activity has been registered "
        "against your Aadhaar. To avoid disconnection, press nine now or call this number back "
        "immediately to speak with our cyber cell officer."
    ),
    "zomato_partnership_lead_+15550008888.wav": (
        "Hi, this is Ananya from Zomato's restaurant partnerships team. We noticed your new cafe "
        "and would love to talk about listing it on Zomato, with a launch offer for your first "
        "month. Could you call me back sometime this week? Thanks so much."
    ),
}


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    engine = pyttsx3.init()
    engine.setProperty("rate", 165)
    for file_name, text in SCRIPTS.items():
        engine.save_to_file(text, str(OUT_DIR / file_name))
    engine.runAndWait()
    print(f"Wrote {len(SCRIPTS)} sample voicemails to {OUT_DIR}")


if __name__ == "__main__":
    main()
