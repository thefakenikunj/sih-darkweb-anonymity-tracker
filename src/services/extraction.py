"""
services/extraction.py — Phase 1

Pulls structured identifiers out of raw observation text: PGP fingerprints,
crypto addresses, emails, XMPP/Jabber handles, and signature-block phrases.

Everything here is regex over plain text. Nothing is evaluated, imported, or
rendered. This module has no side effects and does not touch the database —
normalization.py decides what to do with what this returns.
"""

from __future__ import annotations

import re

from models import IdentifierType

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# 40-char hex fingerprint, optionally space-grouped in blocks of 4 (common
# PGP display format), or a bare 40-hex-char run.
_PGP_FINGERPRINT_RE = re.compile(
    r"\b(?:[0-9A-Fa-f]{4}\s){9}[0-9A-Fa-f]{4}\b|\b[0-9A-Fa-f]{40}\b"
)

# Short PGP key IDs (8 or 16 hex chars), commonly prefixed with 0x.
_PGP_KEYID_RE = re.compile(r"\b0x[0-9A-Fa-f]{8}(?:[0-9A-Fa-f]{8})?\b")

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# XMPP/Jabber addresses are syntactically like email; only tag as XMPP when
# explicitly labeled in the surrounding text (checked by caller), otherwise
# indistinguishable strings default to IdentifierType.EMAIL.
_JABBER_LABEL_RE = re.compile(r"\b(?:jabber|xmpp)\s*[:=]?\s*", re.IGNORECASE)

# Bitcoin: legacy/P2SH (1.../3...) and bech32 (bc1...).
_BTC_ADDRESS_RE = re.compile(
    r"\b(?:bc1[a-zA-HJ-NP-Z0-9]{25,60}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b"
)

# Ethereum-style 20-byte hex address.
_ETH_ADDRESS_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")

# Monero addresses (starts with 4, 8, or 9 typically, ~95 base58 chars).
_XMR_ADDRESS_RE = re.compile(r"\b[48][0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b")

# Very rough heuristic for a forum-style signature block: a line consisting
# of "--" followed by a short trailing line, or a line ending the message
# that starts with "--" or "~~" and a short handle-like token.
_SIGNATURE_LINE_RE = re.compile(r"(?:^|\n)\s*(?:--|~~)\s*(.+?)\s*$")


def _dedup(pairs: list[tuple[IdentifierType, str]]) -> list[tuple[IdentifierType, str]]:
    seen: set[tuple[IdentifierType, str]] = set()
    out: list[tuple[IdentifierType, str]] = []
    for pair in pairs:
        if pair not in seen:
            seen.add(pair)
            out.append(pair)
    return out


def extract_identifiers(raw_text: str) -> list[tuple[IdentifierType, str]]:
    """Return a deduplicated list of (IdentifierType, value) tuples found in
    raw_text. Pure function — no I/O, no DB access, no execution of the
    input in any form."""

    found: list[tuple[IdentifierType, str]] = []

    for m in _PGP_FINGERPRINT_RE.finditer(raw_text):
        # Normalize spacing so "AA11 BB22 ..." and "AA11BB22..." dedup to the
        # same identifier value.
        normalized = m.group(0).replace(" ", "").upper()
        found.append((IdentifierType.PGP_FINGERPRINT, normalized))

    for m in _PGP_KEYID_RE.finditer(raw_text):
        found.append((IdentifierType.PGP_FINGERPRINT, m.group(0).lower()))

    for m in _BTC_ADDRESS_RE.finditer(raw_text):
        found.append((IdentifierType.CRYPTO_ADDRESS, m.group(0)))

    for m in _ETH_ADDRESS_RE.finditer(raw_text):
        found.append((IdentifierType.CRYPTO_ADDRESS, m.group(0).lower()))

    for m in _XMR_ADDRESS_RE.finditer(raw_text):
        found.append((IdentifierType.CRYPTO_ADDRESS, m.group(0)))

    # Emails vs. jabber/XMPP: same shape, disambiguated by a nearby label.
    for m in _EMAIL_RE.finditer(raw_text):
        window_start = max(0, m.start() - 20)
        preceding = raw_text[window_start:m.start()]
        if _JABBER_LABEL_RE.search(preceding):
            found.append((IdentifierType.JABBER_XMPP, m.group(0).lower()))
        else:
            found.append((IdentifierType.EMAIL, m.group(0).lower()))

    for m in _SIGNATURE_LINE_RE.finditer(raw_text):
        phrase = m.group(1).strip()
        # Skip empty / overly long matches (long matches are probably not a
        # genuine short signature phrase).
        if 1 <= len(phrase) <= 64:
            found.append((IdentifierType.SIGNATURE_PHRASE, phrase))

    return _dedup(found)
