"""The spec §13 steak-salad fixture, shaped for the create-recipe API."""
from __future__ import annotations


def steak_salad_payload(tag_ids: list[int] | None = None) -> dict:
    return {
        "title": "Apple Cheddar Steak Salad",
        "description": "Steak Salad Sundays Part 63 — an apple cheddar moment.",
        "source_type": "instagram",
        "source_name": "chacekitchen",
        "source_handle": "@chacekitchen",
        "servings_base": 2,
        "servings_unit": "salads",
        "status": "published",
        "groups": [
            {
                "name": "For the salad",
                "sort_order": 0,
                "ingredients": [
                    {"quantity": None, "unit": None, "name": "sliced steak", "scalable": 0},
                    {"quantity": None, "unit": None, "name": "butter lettuce", "scalable": 0},
                    {"quantity": None, "unit": None, "name": "honeycrisp apple slices", "scalable": 0},
                    {"quantity": None, "unit": None, "name": "sliced shallot", "scalable": 0},
                    {"quantity": None, "unit": None, "name": "avocado slices", "scalable": 0},
                    {"quantity": None, "unit": None, "name": "sweet and spicy pecans", "scalable": 0},
                    {"quantity": None, "unit": None, "name": "cheddar cubes", "note": "used habanero cheddar (Cabot)", "scalable": 0},
                    {"quantity": None, "unit": None, "name": "cheddar crisps", "note": "used Tillamook", "scalable": 0},
                    {"quantity": None, "unit": None, "name": "honey dijon dressing", "note": "see below", "scalable": 0},
                ],
            },
            {
                "name": "Honey dijon dressing",
                "sort_order": 1,
                "ingredients": [
                    {"quantity": 0.25, "unit": "cup", "name": "olive oil", "scalable": 1},
                    {"quantity": 1, "unit": "tbsp", "name": "apple cider vinegar", "scalable": 1},
                    {"quantity": 2, "unit": "tbsp", "name": "dijon", "scalable": 1},
                    {"quantity": 1.5, "unit": "tbsp", "name": "honey", "scalable": 1},
                    {"quantity": 2, "unit": "clove", "name": "garlic", "note": "minced", "scalable": 1},
                    {"quantity": 1, "unit": "tbsp", "name": "fresh dill", "scalable": 1},
                    {"quantity": 1, "unit": "tbsp", "name": "fresh chives", "scalable": 1},
                    {"quantity": None, "unit": None, "name": "salt and pepper", "note": "to taste", "scalable": 0},
                ],
            },
        ],
        "steps": [],
        "equipment": [
            {"name": "grill or grill pan", "inferred": 1},
            {"name": "chef's knife", "inferred": 1},
            {"name": "cutting board", "inferred": 1},
            {"name": "mixing bowl", "inferred": 1},
            {"name": "whisk", "inferred": 1},
        ],
        "tag_ids": tag_ids or [],
    }
