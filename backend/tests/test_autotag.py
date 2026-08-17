"""Offline auto-tagger: keyword → controlled-vocabulary tag selection."""
from __future__ import annotations

from app.extraction import autotag
from app.seed import TAXONOMY

# The real seeded vocabulary — what an actual install offers the tagger.
ALLOWED = {cat: list(names) for cat, names in TAXONOMY.items()}


def suggest(title="", desc="", ings=None, steps=None, total_time=None):
    return autotag.suggest_tags(
        title=title,
        description=desc,
        ingredient_names=ings or [],
        steps=steps or [],
        total_time=total_time,
        allowed_by_category=ALLOWED,
    )


def test_protein_and_method_from_ingredients_and_steps():
    out = suggest(
        title="Grilled Chicken Thighs",
        ings=["4 chicken thighs", "2 tbsp olive oil"],
        steps=["Grill over medium heat until charred."],
    )
    assert "Chicken" in out["Protein"]
    assert "Grill" in out["Method"]
    # A protein with no specific course → Main.
    assert "Main" in out["Course"]


def test_specific_course_suppresses_main():
    out = suggest(title="Chicken Noodle Soup", ings=["chicken", "egg noodles"])
    assert "Soup" in out["Course"]
    assert "Main" not in out.get("Course", [])


def test_cuisine_and_dessert_no_main():
    out = suggest(title="Classic Tiramisu", desc="An Italian dessert", ings=["mascarpone", "espresso"])
    assert "Dessert" in out["Course"]
    assert "Main" not in out.get("Course", [])


def test_short_stems_do_not_overmatch():
    # "ham" must not fire on "hamburger"; "egg" must not fire on "eggplant".
    out = suggest(title="Hamburger Helper", ings=["eggplant", "ground beef"])
    assert "Pork" not in out.get("Protein", [])  # no real ham
    assert "Egg" not in out.get("Protein", [])  # eggplant is not egg
    assert "Beef" in out["Protein"]


def test_plural_matches():
    out = suggest(ings=["black beans", "2 eggs"])
    assert "Beans/Legumes" in out["Protein"]
    assert "Egg" in out["Protein"]


def test_time_signal():
    assert "Quick (<30 min)" in suggest(title="Fast Pasta", total_time=20).get("Time", [])
    assert "Time" not in suggest(title="Slow Braise", total_time=180)


def test_only_emits_existing_vocab():
    # A vocabulary missing "Grill" must not receive it even when keywords match.
    trimmed = {**ALLOWED, "Method": ["Oven/Roast", "Stovetop"]}
    out = autotag.suggest_tags(
        title="Grilled steak", description="", ingredient_names=["steak"],
        steps=["grill it"], total_time=None, allowed_by_category=trimmed,
    )
    assert "Grill" not in out.get("Method", [])


def test_merge_prefers_primary_then_unions():
    merged = autotag.merge_tag_names(
        {"Protein": ["Chicken"]}, {"Protein": ["Chicken", "Cheese"], "Method": ["Grill"]}
    )
    assert merged["Protein"] == ["Chicken", "Cheese"]
    assert merged["Method"] == ["Grill"]
