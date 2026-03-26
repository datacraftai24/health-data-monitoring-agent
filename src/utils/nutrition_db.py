"""Common food nutrition database — seed data for South Asian + common foods."""

# Per 100g serving unless otherwise noted
NUTRITION_DB: dict[str, dict] = {
    # Indian breads
    "roti": {
        "calories": 297, "protein_g": 9.0, "carbs_g": 56.0, "fat_g": 3.7,
        "fiber_g": 2.0, "gi": "medium", "serving_g": 40,
    },
    "paratha": {
        "calories": 326, "protein_g": 7.5, "carbs_g": 45.0, "fat_g": 13.0,
        "fiber_g": 1.5, "gi": "medium", "serving_g": 80,
    },
    "paneer_paratha": {
        "calories": 290, "protein_g": 10.0, "carbs_g": 35.0, "fat_g": 12.0,
        "fiber_g": 1.5, "gi": "medium", "serving_g": 100,
    },
    "naan": {
        "calories": 310, "protein_g": 9.0, "carbs_g": 54.0, "fat_g": 5.0,
        "fiber_g": 2.0, "gi": "high", "serving_g": 90,
    },
    # Rice
    "white_rice": {
        "calories": 130, "protein_g": 2.7, "carbs_g": 28.0, "fat_g": 0.3,
        "fiber_g": 0.4, "gi": "high", "serving_g": 150,
    },
    "brown_rice": {
        "calories": 123, "protein_g": 2.7, "carbs_g": 26.0, "fat_g": 1.0,
        "fiber_g": 1.8, "gi": "medium", "serving_g": 150,
    },
    # Dals & curries
    "dal_tadka": {
        "calories": 120, "protein_g": 7.0, "carbs_g": 16.0, "fat_g": 3.5,
        "fiber_g": 3.5, "gi": "low", "serving_g": 150,
    },
    "kadhi": {
        "calories": 95, "protein_g": 3.5, "carbs_g": 8.0, "fat_g": 5.5,
        "fiber_g": 0.5, "gi": "low", "serving_g": 150,
    },
    "paneer_bhurji": {
        "calories": 265, "protein_g": 18.0, "carbs_g": 4.0, "fat_g": 20.0,
        "fiber_g": 0.5, "gi": "low", "serving_g": 150,
    },
    "chole": {
        "calories": 160, "protein_g": 9.0, "carbs_g": 24.0, "fat_g": 4.0,
        "fiber_g": 6.0, "gi": "low", "serving_g": 150,
    },
    # Chillas / crepes
    "besan_chilla": {
        "calories": 180, "protein_g": 10.0, "carbs_g": 18.0, "fat_g": 7.0,
        "fiber_g": 3.0, "gi": "low", "serving_g": 100,
    },
    "sooji_chilla": {
        "calories": 200, "protein_g": 5.0, "carbs_g": 30.0, "fat_g": 6.0,
        "fiber_g": 1.0, "gi": "high", "serving_g": 100,
    },
    "moong_dal_chilla": {
        "calories": 150, "protein_g": 11.0, "carbs_g": 16.0, "fat_g": 4.0,
        "fiber_g": 3.0, "gi": "low", "serving_g": 100,
    },
    # Protein sources
    "eggs_boiled": {
        "calories": 155, "protein_g": 13.0, "carbs_g": 1.1, "fat_g": 11.0,
        "fiber_g": 0, "gi": "low", "serving_g": 50,
    },
    "chicken_breast_grilled": {
        "calories": 165, "protein_g": 31.0, "carbs_g": 0, "fat_g": 3.6,
        "fiber_g": 0, "gi": "low", "serving_g": 150,
    },
    "paneer": {
        "calories": 265, "protein_g": 18.0, "carbs_g": 1.2, "fat_g": 21.0,
        "fiber_g": 0, "gi": "low", "serving_g": 100,
    },
    "greek_yogurt": {
        "calories": 59, "protein_g": 10.0, "carbs_g": 3.6, "fat_g": 0.7,
        "fiber_g": 0, "gi": "low", "serving_g": 150,
    },
    # Fruits
    "banana": {
        "calories": 89, "protein_g": 1.1, "carbs_g": 23.0, "fat_g": 0.3,
        "fiber_g": 2.6, "gi": "medium", "serving_g": 120,
    },
    "apple": {
        "calories": 52, "protein_g": 0.3, "carbs_g": 14.0, "fat_g": 0.2,
        "fiber_g": 2.4, "gi": "low", "serving_g": 180,
    },
    # Sweets (common)
    "ladoo": {
        "calories": 450, "protein_g": 6.0, "carbs_g": 55.0, "fat_g": 23.0,
        "fiber_g": 1.0, "gi": "high", "serving_g": 40,
    },
    "gulab_jamun": {
        "calories": 380, "protein_g": 4.0, "carbs_g": 50.0, "fat_g": 18.0,
        "fiber_g": 0.5, "gi": "high", "serving_g": 50,
    },
}


def lookup_food(name: str) -> dict | None:
    """Look up a food item by name. Returns nutrition data or None."""
    key = name.lower().replace(" ", "_").replace("-", "_")
    return NUTRITION_DB.get(key)


def get_all_foods() -> dict[str, dict]:
    """Return the full nutrition database."""
    return NUTRITION_DB
