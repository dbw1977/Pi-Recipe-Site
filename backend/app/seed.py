"""Seed the controlled tag vocabulary from spec §8.

CLAUDE.md rule 7: controlled vocabulary. The AI tagger (Chunk B) picks only from these;
new tags are added by hand in the UI, never invented per-import. Seeding uses
INSERT OR IGNORE so it is idempotent and never disturbs user-added tags.
"""
from __future__ import annotations

import sqlite3

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


def seed_taxonomy(conn: sqlite3.Connection) -> None:
    for category, tags in TAXONOMY.items():
        conn.execute("INSERT OR IGNORE INTO tag_category(name) VALUES (?)", (category,))
        row = conn.execute(
            "SELECT id FROM tag_category WHERE name = ?", (category,)
        ).fetchone()
        category_id = row["id"]
        for name in tags:
            conn.execute(
                "INSERT OR IGNORE INTO tag(category_id, name) VALUES (?, ?)",
                (category_id, name),
            )
