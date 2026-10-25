"""Indian number-plate normaliser and repair. Event time is not this module's job."""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import product

PLATE_RE = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}$")

# An Indian registration is: state (2 letters), RTO district (1-2 digits),
# series (1-3 letters), number (3-4 digits). Knowing which positions must be
# digits and which must be letters lets us repair the classic OCR confusions
# instead of discarding an otherwise correct read.
#
# Ordered most-common-first so an ambiguous length resolves to the usual shape.
_LAYOUTS: tuple[tuple[int, int, int], ...] = tuple(
    sorted(
        product((2, 1), (2, 1, 3), (4, 3)),
        key=lambda c: (c != (2, 2, 4), c != (2, 1, 4), c),
    )
)

# Glyph pairs OCR engines routinely swap. Applied only where the layout forces
# the character class, so a digit position can never receive a letter.
_TO_DIGIT = {"O": "0", "D": "0", "Q": "0", "U": "0",
             "I": "1", "L": "1", "J": "1",
             "Z": "2", "E": "3", "A": "4", "S": "5",
             "G": "6", "C": "6", "T": "7", "B": "8", "R": "8"}
_TO_LETTER = {"0": "O", "1": "I", "2": "Z", "3": "E",
              "4": "A", "5": "S", "6": "G", "7": "T", "8": "B"}

# Every Indian state and union territory code, plus the central government and
# military series. Repair must land on a real state: without this the substitution
# search happily turns "HELLOWORLD" into "HE11OW0810", which is exactly the
# invented-plate failure that matters most in an evidential system.
_STATE_CODES = frozenset(
    """AN AP AR AS BR CG CH DD DH DL DN GA GJ HP HR JH JK KA KL LA LD MH ML MN MP
       MZ NL OD OR PB PY RJ SK TG TN TR TS UK UA UP WB
       BH CD""".split()
)
# DH is the merged Dadra & Nagar Haveli / Daman & Diu code (2020); DD and DN stay
# for plates issued before the merger. TG is the newer Telangana code alongside
# TS. BH is the all-India Bharat series and CD diplomatic — both use layouts this
# module does not otherwise model, but the codes are real and must not be
# rejected as typos.

# An incomplete list rejects real plates, so keep an escape hatch: setting
# PLATE_REQUIRE_STATE_CODE=0 restores format-only validation.
def _require_state_code() -> bool:
    from app import config

    return (config.getenv("PLATE_REQUIRE_STATE_CODE", "1").strip().lower()
            not in {"0", "false", "no"})

# How many characters repair may change. One or two is a plausible OCR slip; more
# than that and we are rewriting the reading rather than correcting it.
MAX_CORRECTIONS = 2


def _coerce(text: str, want_digits: bool) -> str | None:
    """Force a run of characters to one class, or fail if any cannot convert."""
    out = []
    for ch in text:
        if want_digits:
            if ch.isdigit():
                out.append(ch)
            elif ch in _TO_DIGIT:
                out.append(_TO_DIGIT[ch])
            else:
                return None
        else:
            if ch.isalpha():
                out.append(ch)
            elif ch in _TO_LETTER:
                out.append(_TO_LETTER[ch])
            else:
                return None
    return "".join(out)


def repair(compact: str) -> tuple[str | None, bool]:
    """Return (plate, was_corrected) for an already-uppercased, stripped string.

    Tries each valid Indian layout that matches the string's length and coerces
    each run to its required character class. Returns the first layout that
    yields a well-formed plate.

    Repair is deliberately conservative: every character must map through a known
    confusion pair, so arbitrary text cannot be bent into a plate. A returned
    `was_corrected` of True means the reading was altered and should be treated as
    lower-confidence evidence, never as a clean read.
    """
    if not compact:
        return None, False
    if PLATE_RE.match(compact):
        # A well-formed plate whose state code does not exist is a misread, not a
        # plate. Measured on the test set: HH43CC1745, LX05BF0500 and HA0PMA2662
        # all passed the format check and were all wrong. Rejecting them costs no
        # correct readings and removes a third of the wrong ones.
        #
        # No letter-to-letter repair is attempted here. Correcting HH to MH would
        # need a confusion class wide enough to invent plates, which is the one
        # failure mode worse than returning nothing.
        if _require_state_code() and compact[:2] not in _STATE_CODES:
            return None, False
        return compact, False

    for d1, letters, d2 in _LAYOUTS:
        if len(compact) != 2 + d1 + letters + d2:
            continue
        i = 0
        state = _coerce(compact[i:i + 2], want_digits=False)
        i += 2
        district = _coerce(compact[i:i + d1], want_digits=True) if state else None
        i += d1
        series = _coerce(compact[i:i + letters], want_digits=False) if district else None
        i += letters
        number = _coerce(compact[i:i + d2], want_digits=True) if series else None
        if not number:
            continue
        candidate = f"{state}{district}{series}{number}"
        if not PLATE_RE.match(candidate):
            continue
        if state not in _STATE_CODES:
            continue
        edits = sum(1 for a, b in zip(candidate, compact) if a != b)
        if edits > MAX_CORRECTIONS:
            continue
        return candidate, edits > 0
    return None, False


@dataclass(frozen=True)
class Reading:
    """What OCR saw, what the system accepted, and why it did or did not.

    An official reviewing a hit is entitled to see the reading that was rejected
    and the reason, not just an empty result. "Nothing found" and "found text
    that is not a valid plate" are very different failures to act on.
    """

    raw: str
    plate: str | None
    corrected: bool
    reason: str

    @property
    def ok(self) -> bool:
        return self.plate is not None


#: High-security plates (HSRP) carry a small "IND" mark beside the characters,
#: and OCR reads it as part of the plate: measured on a two-row bike plate,
#: "IND" + "PBO8D" + "B3893". No state code starts with "IN", so a leading
#: label can never be part of a real plate and is safe to drop.
_HSRP_LABELS = ("INDIA", "IND")


def _repair_with_label(compact: str) -> tuple[str | None, bool, str]:
    """repair(), retried without a leading HSRP label. Returns the text used."""
    plate, corrected = repair(compact)
    if plate:
        return plate, corrected, compact
    for label in _HSRP_LABELS:
        rest = compact[len(label):]
        if compact.startswith(label) and len(rest) >= 7:
            plate, corrected = repair(rest)
            if plate:
                return plate, corrected, rest
    return None, False, compact


def inspect(raw: str | None) -> Reading:
    """Validate a reading and explain the verdict in plain language."""
    text = "" if raw is None else str(raw)
    compact = re.sub(r"[\s\-]", "", text).upper()
    if not compact:
        return Reading(text, None, False, "no text read")

    plate, corrected, used = _repair_with_label(compact)
    if plate and used != compact:
        fixes = sum(1 for a, b in zip(plate, used) if a != b)
        reason = "ignored the IND plate label" + (f"; corrected {fixes} character(s)" if fixes else "")
        return Reading(text, plate, corrected, reason)
    if plate:
        reason = (
            f"corrected {sum(1 for a, b in zip(plate, compact) if a != b)} character(s)"
            if corrected
            else "matches Indian plate format"
        )
        return Reading(text, plate, corrected, reason)

    # Explain the most specific failure we can, so the reader is actionable.
    lengths = {2 + d1 + le + d2 for d1, le, d2 in _LAYOUTS}
    if len(compact) not in lengths:
        return Reading(
            text, None, False,
            f"{len(compact)} characters; an Indian plate is "
            f"{min(lengths)}-{max(lengths)} (SS DD LL NNNN)",
        )
    head = compact[:2]
    if head.isalpha() and head not in _STATE_CODES:
        if PLATE_RE.match(compact):
            return Reading(
                text, None, False,
                f"reads as a plate but '{head}' is not an Indian state code — "
                "treated as a misread",
            )
        return Reading(text, None, False, f"'{head}' is not an Indian state code")
    return Reading(text, None, False, "does not fit the Indian plate pattern")


def normalise(raw: str | None) -> str | None:
    """Strip formatting and return a well-formed plate, repairing if needed."""
    plate, _ = normalise_ex(raw)
    return plate


def normalise_ex(raw: str | None) -> tuple[str | None, bool]:
    """normalise(), plus whether character repair was applied.

    Callers that record evidence should keep the flag: an official reviewing a
    hit is entitled to know the system changed a character to make it parse.
    """
    if raw is None:
        return None, False
    compact = re.sub(r"[\s\-]", "", str(raw)).upper()
    if not compact:
        return None, False
    plate, corrected, _ = _repair_with_label(compact)
    return plate, corrected
