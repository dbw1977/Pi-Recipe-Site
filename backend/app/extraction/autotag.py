"""Deterministic, offline auto-tagger (spec §8, CLAUDE.md rule 7).

Scans a recipe's own words — title, description, ingredient names, steps — and picks
tags from the *controlled vocabulary* by keyword. This runs on every import (merged with
any tags the AI suggested), so drafts land in the review screen with tags already
selected and the cook just confirms them instead of choosing from scratch.

Two hard rules from CLAUDE.md:
  - Rule 7: only ever emit tags that already exist in this install. A keyword rule that
    names a tag the vocabulary doesn't have is silently skipped — never invented.
  - We favour precision over recall: these tags arrive pre-checked, so a confident match
    is worth more than a broad guess the cook would have to untick.

`suggest_tags` returns a {category: [names]} dict, already filtered to the allowed
vocabulary, ready to merge with the AI's suggestions and hand to `TagIndex.resolve`.
"""
from __future__ import annotations

import re

# category -> tag name -> keyword stems. Matching is word-boundary + optional plural
# (so "bean" hits "beans", but "ham" never hits "hamburger"). Keep stems specific: a
# short, ambiguous stem here becomes a mis-tag on someone's dinner.
_RULES: dict[str, dict[str, list[str]]] = {
    "Protein": {
        "Beef": ["beef", "steak", "sirloin", "ribeye", "brisket", "chuck roast", "ground beef"],
        "Chicken": ["chicken"],
        "Pork": ["pork", "bacon", "ham", "sausage", "prosciutto", "pancetta", "chorizo", "andouille"],
        "Lamb": ["lamb"],
        "Turkey": ["turkey"],
        "Fish": ["fish", "salmon", "tuna", "cod", "tilapia", "halibut", "trout", "mahi", "snapper", "anchovy"],
        "Shellfish": ["shrimp", "prawn", "crab", "lobster", "scallop", "clam", "mussel", "oyster", "calamari", "squid"],
        "Egg": ["egg"],
        "Tofu/Tempeh": ["tofu", "tempeh", "seitan"],
        "Beans/Legumes": ["bean", "lentil", "chickpea", "garbanzo", "black bean", "kidney bean"],
        "Cheese": ["cheese", "parmesan", "cheddar", "mozzarella", "feta", "gouda", "ricotta"],
        "Pasta": ["pasta", "spaghetti", "penne", "macaroni", "noodle", "lasagna", "fettuccine", "linguine", "gnocchi"],
        "Grain/Rice": ["rice", "quinoa", "barley", "farro", "couscous", "bulgur", "polenta"],
    },
    "Course": {
        "Breakfast": ["breakfast", "pancake", "waffle", "omelet", "omelette", "french toast", "granola", "oatmeal"],
        "Brunch": ["brunch"],
        "Salad": ["salad"],
        "Soup": ["soup", "stew", "chili", "chowder", "bisque", "broth"],
        "Dessert": ["dessert", "cake", "cookie", "brownie", "pie", "tart", "ice cream", "cheesecake", "cupcake", "pudding", "mousse", "frosting"],
        "Snack": ["snack"],
        "Drink": ["cocktail", "smoothie", "margarita", "latte", "lemonade", "mocktail"],
        "Sauce/Dressing": ["dressing", "vinaigrette", "sauce", "aioli", "salsa", "pesto", "chutney"],
        "Marinade": ["marinade", "marinate"],
        "Bread/Baked": ["bread", "loaf", "muffin", "biscuit", "focaccia", "scone", "bagel", "dinner roll", "croissant"],
        "Appetizer": ["appetizer", "bruschetta", "deviled egg"],
    },
    "Cuisine": {
        "Mexican": ["taco", "tortilla", "enchilada", "quesadilla", "salsa", "guacamole", "burrito", "fajita", "carnitas"],
        "Italian": ["pasta", "spaghetti", "risotto", "parmesan", "mozzarella", "pesto", "marinara", "lasagna", "gnocchi", "carbonara"],
        "Indian": ["curry", "masala", "tikka", "naan", "tandoori", "paneer", "biryani"],
        "Thai": ["thai", "lemongrass", "fish sauce", "pad thai", "coconut milk"],
        "Chinese": ["hoisin", "stir-fry", "stir fry", "bok choy", "szechuan", "sichuan", "five spice"],
        "Japanese": ["miso", "teriyaki", "dashi", "sushi", "ramen", "tempura"],
        "Korean": ["gochujang", "kimchi", "bulgogi", "gochugaru"],
        "Middle Eastern": ["hummus", "tahini", "falafel", "pita", "za'atar", "shawarma", "harissa"],
        "Greek": ["tzatziki", "gyro"],
        "French": ["baguette", "béarnaise", "beurre blanc", "coq au vin", "ratatouille"],
        "Cajun/Creole": ["cajun", "creole", "andouille", "jambalaya", "gumbo", "remoulade"],
        "BBQ": ["barbecue", "pulled pork", "baby back"],
        "Southern": ["grits", "collard"],
    },
    "Method": {
        "Grill": ["grill", "grilled", "grilling"],
        "Oven/Roast": ["roast", "roasted", "bake", "baked", "oven", "broil"],
        "Stovetop": ["skillet", "sauté", "saute", "stovetop", "simmer", "sear", "pan-fry", "pan fry", "saucepan"],
        "Slow Cooker": ["slow cooker", "crockpot", "crock pot", "crock-pot"],
        "Pressure Cooker": ["pressure cooker", "instant pot"],
        "Air Fryer": ["air fryer", "air-fry", "air fry"],
        "Smoker": ["smoker", "smoked"],
        "Sous Vide": ["sous vide"],
        "No-Cook": ["no-cook", "no cook"],
        "Sheet Pan": ["sheet pan", "sheet-pan"],
        "One-Pot": ["one pot", "one-pot", "one pan", "one-pan", "dutch oven"],
    },
    "Dietary": {
        "Vegetarian": ["vegetarian"],
        "Vegan": ["vegan"],
        "Gluten-Free": ["gluten-free", "gluten free"],
        "Dairy-Free": ["dairy-free", "dairy free"],
        "Nut-Free": ["nut-free", "nut free"],
        "Low-Carb/Keto": ["keto", "low-carb", "low carb"],
        "Paleo": ["paleo"],
        "High-Protein": ["high-protein", "high protein"],
    },
    "Occasion": {
        "Holiday": ["holiday", "thanksgiving", "christmas", "easter"],
        "Game Day": ["game day", "super bowl", "tailgate"],
        "Summer": ["summer"],
        "Party": ["party"],
    },
}

# A Course that already says what kind of dish it is; if one of these fired we don't
# also slap on a generic "Main".
_SPECIFIC_COURSES = {
    "Breakfast", "Brunch", "Salad", "Soup", "Dessert", "Snack", "Drink",
    "Sauce/Dressing", "Marinade", "Bread/Baked", "Appetizer", "Side",
}
_MEAT_PROTEINS = {"Beef", "Chicken", "Pork", "Lamb", "Turkey", "Fish", "Shellfish"}


def _compile(stem: str) -> re.Pattern:
    # Word boundary + optional simple plural. Multi-word stems match verbatim (+ plural).
    return re.compile(r"\b" + re.escape(stem) + r"(?:s|es)?\b", re.IGNORECASE)


# Pre-compile once at import time.
_COMPILED: dict[str, dict[str, list[re.Pattern]]] = {
    cat: {name: [_compile(s) for s in stems] for name, stems in names.items()}
    for cat, names in _RULES.items()
}


def suggest_tags(
    *,
    title: str | None,
    description: str | None,
    ingredient_names: list[str],
    steps: list[str],
    total_time: int | None,
    allowed_by_category: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Keyword-match a recipe against the vocabulary. Returns {category: [tag names]}.

    Only names actually present in `allowed_by_category` are returned (rule 7)."""
    haystack = " \n ".join(
        p for p in [title or "", description or "", *ingredient_names, *steps] if p
    ).lower()

    # Fast membership check, case-insensitive, per category.
    allowed = {
        cat: {n.lower(): n for n in names} for cat, names in allowed_by_category.items()
    }

    def keep(cat: str, name: str) -> str | None:
        return allowed.get(cat, {}).get(name.lower())

    out: dict[str, list[str]] = {}
    for cat, names in _COMPILED.items():
        for name, patterns in names.items():
            canonical = keep(cat, name)
            if canonical is None:
                continue  # not in this install's vocabulary — skip, never invent
            if any(p.search(haystack) for p in patterns):
                out.setdefault(cat, []).append(canonical)

    # Time: a stated total under 30 min is our one numeric signal.
    if total_time and total_time < 30:
        canonical = keep("Time", "Quick (<30 min)")
        if canonical:
            out.setdefault("Time", []).append(canonical)

    # If we found a protein but no course that pins down the dish, call it a Main.
    proteins = set(out.get("Protein", []))
    courses = set(out.get("Course", []))
    if proteins & _MEAT_PROTEINS and not (courses & _SPECIFIC_COURSES):
        canonical = keep("Course", "Main")
        if canonical:
            out.setdefault("Course", []).append(canonical)

    return out


def merge_tag_names(
    primary: dict[str, list[str]], extra: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Union two {category: [names]} dicts, keeping `primary`'s order first."""
    merged: dict[str, list[str]] = {c: list(v) for c, v in (primary or {}).items()}
    for cat, names in (extra or {}).items():
        bucket = merged.setdefault(cat, [])
        for n in names:
            if n not in bucket:
                bucket.append(n)
    return merged
