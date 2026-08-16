"""Parse free-text ingredient strings into structured rows.

`recipe-scrapers` returns ingredients as strings ("1 1/2 tbsp honey"). When no Claude key
is configured we still want usable structure, so this is a dependency-free best-effort
parser producing {quantity, unit, name, note, scalable}. It errs toward leaving text in
`name` rather than guessing wrong — the review screen (spec §6) is where the user corrects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Unicode fractions → decimal.
_UNICODE_FRACTIONS = {
    "¼": 0.25, "½": 0.5, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3,
    "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875, "⅕": 0.2, "⅖": 0.4,
}

# Units we recognize; everything else stays part of the name.
_UNITS = {
    "teaspoon": "tsp", "teaspoons": "tsp", "tsp": "tsp", "tsps": "tsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsp": "tbsp", "tbsps": "tbsp", "tbs": "tbsp",
    "cup": "cup", "cups": "cup",
    "fluid ounce": "fl oz", "fl oz": "fl oz", "floz": "fl oz",
    "ounce": "oz", "ounces": "oz", "oz": "oz",
    "pound": "lb", "pounds": "lb", "lb": "lb", "lbs": "lb",
    "gram": "g", "grams": "g", "g": "g", "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "ml": "ml", "milliliter": "ml", "l": "l", "liter": "l", "litre": "l",
    "pint": "pint", "pints": "pint", "quart": "quart", "quarts": "quart",
    "clove": "clove", "cloves": "clove", "slice": "slice", "slices": "slice",
    "can": "can", "cans": "can", "pinch": "pinch", "pinches": "pinch",
    "stick": "stick", "sticks": "stick", "sprig": "sprig", "sprigs": "sprig",
    "head": "head", "heads": "head", "stalk": "stalk", "stalks": "stalk",
    "piece": "piece", "pieces": "piece",
}

_NO_SCALE_HINTS = ("to taste", "for garnish", "for serving", "optional", "as needed")

# leading quantity: "1", "1.5", "1 1/2", "1/2", "½", "1½", "2-3"
_QTY_RE = re.compile(
    r"^\s*(?P<qty>\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?|[¼½¾⅓⅔⅛⅜⅝⅞⅕⅖]|\d*[¼½¾⅓⅔⅛⅜⅝⅞⅕⅖])\s*"
)


@dataclass
class ParsedIngredient:
    quantity: Optional[float]
    unit: Optional[str]
    name: str
    note: Optional[str]
    scalable: int


def _parse_quantity(token: str) -> Optional[float]:
    token = token.strip()
    if not token:
        return None
    # range like "2-3" → take the lower bound
    m = re.match(r"^(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)$", token)
    if m:
        return float(m.group(1))
    # mixed "1 1/2" or "1½"
    total = 0.0
    matched = False
    # unicode fraction possibly attached to a leading integer
    m = re.match(r"^(\d+)\s*([¼½¾⅓⅔⅛⅜⅝⅞⅕⅖])$", token)
    if m:
        return int(m.group(1)) + _UNICODE_FRACTIONS[m.group(2)]
    if token in _UNICODE_FRACTIONS:
        return _UNICODE_FRACTIONS[token]
    parts = token.split()
    for p in parts:
        if "/" in p:
            try:
                num, den = p.split("/")
                total += float(num) / float(den)
                matched = True
            except (ValueError, ZeroDivisionError):
                return None
        else:
            try:
                total += float(p)
                matched = True
            except ValueError:
                return None
    return total if matched else None


def parse_ingredient_line(line: str) -> ParsedIngredient:
    original = line.strip()
    text = original
    scalable = 0 if any(h in text.lower() for h in _NO_SCALE_HINTS) else 1

    # Split a trailing/leading note in parentheses or after a comma ("minced").
    note: Optional[str] = None
    paren = re.search(r"\(([^)]*)\)", text)
    if paren:
        note = paren.group(1).strip()
        text = (text[: paren.start()] + text[paren.end() :]).strip()

    quantity: Optional[float] = None
    unit: Optional[str] = None

    m = _QTY_RE.match(text)
    if m:
        quantity = _parse_quantity(m.group("qty"))
        rest = text[m.end() :].strip()
        # unit is the first word if recognized (check 2-word units like "fl oz" first)
        two = " ".join(rest.split()[:2]).lower().rstrip(".")
        one = rest.split()[0].lower().rstrip(".") if rest.split() else ""
        if two in _UNITS:
            unit = _UNITS[two]
            rest = " ".join(rest.split()[2:])
        elif one in _UNITS:
            unit = _UNITS[one]
            rest = " ".join(rest.split()[1:])
        text = rest.strip()

    # A trailing ", note" (e.g. "garlic, minced")
    if note is None and "," in text:
        head, _, tail = text.partition(",")
        if tail.strip():
            note = tail.strip()
            text = head.strip()

    name = text.strip() or original
    return ParsedIngredient(quantity=quantity, unit=unit, name=name, note=note, scalable=scalable)


def parse_ingredient_lines(lines: list[str]) -> list[ParsedIngredient]:
    return [parse_ingredient_line(l) for l in lines if l and l.strip()]
