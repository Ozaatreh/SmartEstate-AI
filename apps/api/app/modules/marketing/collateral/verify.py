"""Last check before export: every number visible on the rendered page must be a database fact.

The page is parsed as HTML, only text a reader can see is kept (styles and attributes are ignored), and each number
in it is compared with ``FactSheet.allowed_numbers()``. Any other number — a typo in a template, a figure copied from
a reference design — stops the export with ``collateral_unverified_fact`` instead of reaching a customer.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

from app.core.errors import AppError

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")
NUMBER = re.compile(r"[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?")


class UnverifiedFact(AppError):
    status_code, code, message = 500, "collateral_unverified_fact", "The document showed a figure that isn't in the project data."


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in ("style", "script", "title", "svg"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script", "title", "svg") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def visible_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    return " ".join(p.parts)


def numbers_in(text: str) -> list[Decimal]:
    out = []
    for m in NUMBER.finditer(text.translate(ARABIC_DIGITS)):
        try:
            out.append(Decimal(m.group(0).replace(",", "")).normalize())
        except InvalidOperation:  # pragma: no cover - the pattern only matches valid numbers
            continue
    return out


def unverified_numbers(html: str, allowed: set[Decimal]) -> list[str]:
    text = visible_text(html).translate(ARABIC_DIGITS)
    return [m.group(0) for m in NUMBER.finditer(text) if Decimal(m.group(0).replace(",", "")).normalize() not in allowed]


def ensure_verified(html: str, allowed: set[Decimal]) -> None:
    bad = unverified_numbers(html, allowed)
    if bad:
        raise UnverifiedFact(details={"numbers": sorted(set(bad))})
