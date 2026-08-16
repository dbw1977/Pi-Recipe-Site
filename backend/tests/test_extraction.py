"""Unit tests for the pure extraction logic (no network, no keys)."""
from __future__ import annotations

from app.extraction.draft import (
    ExtractedRecipe,
    TagIndex,
    parse_extracted_json,
    to_recipe_input,
)
from app.extraction.ingredients import parse_ingredient_line


def test_parse_ingredient_basic():
    p = parse_ingredient_line("1 1/2 tbsp honey")
    assert p.quantity == 1.5 and p.unit == "tbsp" and p.name == "honey" and p.scalable == 1


def test_parse_ingredient_unicode_and_note():
    p = parse_ingredient_line("¼ cup olive oil (extra virgin)")
    assert p.quantity == 0.25 and p.unit == "cup" and p.name == "olive oil"
    assert p.note == "extra virgin"


def test_parse_ingredient_two_word_unit():
    p = parse_ingredient_line("2 fl oz milk")
    assert p.unit == "fl oz" and p.quantity == 2 and p.name == "milk"


def test_parse_ingredient_to_taste_not_scalable():
    p = parse_ingredient_line("salt and pepper to taste")
    assert p.scalable == 0


def test_parse_ingredient_trailing_note():
    p = parse_ingredient_line("2 cloves garlic, minced")
    assert p.quantity == 2 and p.unit == "clove" and p.name == "garlic" and p.note == "minced"


def test_parse_ingredient_no_quantity():
    p = parse_ingredient_line("sliced steak")
    assert p.quantity is None and p.unit is None and p.name == "sliced steak"


def test_parse_extracted_json_strips_fences_and_prose():
    raw = 'Here you go:\n```json\n{"title": "X", "steps": ["a"]}\n```'
    ex = parse_extracted_json(raw)
    assert ex.title == "X" and ex.steps == ["a"]


def test_parse_extracted_json_raises_on_garbage():
    import pytest

    with pytest.raises(ValueError):
        parse_extracted_json("not json at all")


def _tag_index() -> TagIndex:
    return TagIndex([
        {"id": 1, "name": "Salad", "category": "Course"},
        {"id": 2, "name": "Beef", "category": "Protein"},
        {"id": 3, "name": "Grill", "category": "Method"},
    ])


def test_tag_resolution_constrains_to_vocabulary():
    idx = _tag_index()
    # "Sandwich" is not in the vocabulary and must be dropped (CLAUDE.md rule 7).
    ids = idx.resolve({"Course": ["Salad", "Sandwich"], "Protein": ["Beef"], "Method": ["Grill"]})
    assert sorted(ids) == [1, 2, 3]


def test_tag_resolution_tolerates_wrong_dimension():
    idx = _tag_index()
    # "Beef" filed under the wrong dimension still resolves by name.
    assert idx.resolve({"Course": ["Beef"]}) == [2]


def test_to_recipe_input_marks_draft_and_structures():
    idx = _tag_index()
    ex = ExtractedRecipe(
        title="Steak Salad",
        groups=[{"name": "Dressing", "ingredients": [
            {"quantity": 2, "unit": "tbsp", "name": "dijon", "scalable": 1},
            {"quantity": None, "unit": None, "name": "salt", "note": "to taste", "scalable": 0},
        ]}],
        steps=["Mix.", ""],
        equipment=[{"name": "whisk", "inferred": 1}],
        tags={"Course": ["Salad"], "Protein": ["Beef"]},
    )
    r = to_recipe_input(ex, source_type="url", tag_index=idx, source_url="http://x", hero_image="a.jpg")
    assert r.status == "draft"
    assert r.source_type == "url" and r.source_url == "http://x" and r.hero_image == "a.jpg"
    assert len(r.groups) == 1 and len(r.groups[0].ingredients) == 2
    assert r.steps == [s for s in r.steps]  # empty step filtered
    assert len(r.steps) == 1
    assert r.equipment[0].inferred == 1
    assert sorted(r.tag_ids) == [1, 2]
