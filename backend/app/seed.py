"""Seed the controlled tag vocabulary from spec §8 (recipes) and §14 (places).

CLAUDE.md rule 7: controlled vocabulary. The AI tagger (Chunk B) picks only from these;
new tags are added by hand in the UI, never invented per-import. Seeding uses
INSERT OR IGNORE so it is idempotent and never disturbs user-added tags.
"""
from __future__ import annotations

import sqlite3

from . import config

# Ordered so the UI can render dimensions in a sensible sequence.
TAXONOMY: dict[str, list[str]] = {
    "Course": [
        "Breakfast", "Brunch", "Lunch", "Dinner", "Appetizer", "Side", "Salad",
        "Soup", "Main", "Dessert", "Snack", "Drink", "Sauce/Dressing", "Marinade",
        "Bread/Baked",
    ],
    "Cuisine": [
        "American", "Italian", "Mexican", "French", "Mediterranean", "Middle Eastern",
        "Indian", "Thai", "Chinese", "Japanese", "Korean", "Vietnamese", "Greek",
        "Spanish", "Cajun/Creole", "Southern", "BBQ", "Other",
    ],
    "Protein": [
        "Beef", "Chicken", "Pork", "Lamb", "Turkey", "Fish", "Shellfish", "Egg",
        "Tofu/Tempeh", "Beans/Legumes", "Vegetable", "Cheese", "Pasta", "Grain/Rice",
    ],
    "Dietary": [
        "Vegetarian", "Vegan", "Gluten-Free", "Dairy-Free", "Nut-Free",
        "Low-Carb/Keto", "Paleo", "High-Protein",
    ],
    "Method": [
        "Grill", "Oven/Roast", "Stovetop", "Slow Cooker", "Pressure Cooker",
        "Air Fryer", "Smoker", "Sous Vide", "No-Cook", "Sheet Pan", "One-Pot",
    ],
    "Time": [
        "Quick (<30 min)", "Weeknight", "Make-Ahead", "Meal Prep", "Weekend Project",
    ],
    "Occasion": [
        "Summer", "Fall/Winter", "Holiday", "Game Day", "Party", "Date Night",
    ],
}

# Chunk D (spec §14): dimensions that belong to the Places collection. City/Area is
# user-driven (seeded only with the configured home city); Cuisine is SHARED with recipes.
PLACE_TAXONOMY: dict[str, list[str]] = {
    "Place Type": [
        "Restaurant", "Takeout", "Cafe", "Coffee", "Bar", "Brewery", "Food Truck",
        "Bakery", "Dessert", "Deli", "Fast Food", "Fine Dining",
    ],
    "Price": ["$", "$$", "$$$", "$$$$"],
    "City/Area": [],  # grows as you save places; the home city (if set) is seeded below
}

# Which collection each dimension belongs to. Anything not listed defaults to 'recipe'.
CATEGORY_COLLECTION: dict[str, str] = {
    "Cuisine": "both",       # shared: "Thai" means the same whether cooked or ordered
    "City/Area": "place",
    "Place Type": "place",
    "Price": "place",
}


def _seed_category(conn: sqlite3.Connection, category: str, tags: list[str]) -> None:
    conn.execute("INSERT OR IGNORE INTO tag_category(name) VALUES (?)", (category,))
    row = conn.execute("SELECT id FROM tag_category WHERE name = ?", (category,)).fetchone()
    category_id = row["id"]
    conn.execute(
        "UPDATE tag_category SET collection = ? WHERE id = ?",
        (CATEGORY_COLLECTION.get(category, "recipe"), category_id),
    )
    for name in tags:
        conn.execute(
            "INSERT OR IGNORE INTO tag(category_id, name) VALUES (?, ?)",
            (category_id, name),
        )


def seed_taxonomy(conn: sqlite3.Connection) -> None:
    for category, tags in TAXONOMY.items():
        _seed_category(conn, category, tags)
    for category, tags in PLACE_TAXONOMY.items():
        _seed_category(conn, category, tags)

    # Seed the configured home city so new places default to it (spec §14).
    home = (config.HOME_CITY or "").strip()
    if home:
        cid = conn.execute("SELECT id FROM tag_category WHERE name = 'City/Area'").fetchone()["id"]
        conn.execute("INSERT OR IGNORE INTO tag(category_id, name) VALUES (?, ?)", (cid, home))
