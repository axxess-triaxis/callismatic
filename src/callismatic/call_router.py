"""Routes an outbound callback to the right calling provider for the destination country.

Today there is exactly one provider registered (CALL-E), so this behaves
identically to calling `callback.place_callback` directly. The point of
this module is the extension point: CALL-E's own docs list India (and many
other countries) as "International" tier -- routed through CALL-E's
international numbers, which real-world testing in this project showed can
get silently filtered by local carriers before the destination phone ever
rings. A production version for emerging markets would register a
region-specific provider (a local SIP/VoIP partner with actual in-country
presence) per country here, with CALL-E remaining the default fallback for
anywhere without one.

This module does not itself add a new calling provider -- that requires a
real contract/integration with a regional telephony partner, which is
outside what a config change or a code review can accomplish. What it does
provide is a place to plug one in without touching any caller's code: every
provider fulfils the same three-argument `place_call(task, phone_number)`
signature as `callback.place_callback`.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol

import phonenumbers

from callismatic.callback import place_callback

JsonObject = dict[str, Any]


class CallProvider(Protocol):
    def __call__(self, task: str, phone_number: str) -> JsonObject: ...


# Country calling code (from phonenumbers) -> provider. Empty today -- CALL-E
# is the default for every country until a region-specific provider is
# integrated and registered here, e.g. `PROVIDERS_BY_COUNTRY_CODE[91] = local_india_provider`.
PROVIDERS_BY_COUNTRY_CODE: dict[int, CallProvider] = {}

DEFAULT_PROVIDER: CallProvider = place_callback


def country_code_for(phone_number: str) -> int | None:
    """Returns the E.164 country calling code for a phone number (e.g. 91 for +91...),
    or None if the number can't be parsed."""
    try:
        parsed = phonenumbers.parse(phone_number)
    except phonenumbers.NumberParseException:
        return None
    return parsed.country_code


def route_call(task: str, phone_number: str) -> JsonObject:
    """Places a callback via whichever provider is registered for the destination
    number's country, falling back to CALL-E (the default) if none is registered."""
    country_code = country_code_for(phone_number)
    provider = PROVIDERS_BY_COUNTRY_CODE.get(country_code, DEFAULT_PROVIDER) if country_code else DEFAULT_PROVIDER
    return provider(task, phone_number)
