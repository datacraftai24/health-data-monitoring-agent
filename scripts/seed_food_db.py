"""Seed the food response database with common South Asian foods.

This populates baseline nutrition data for common foods. Individual glucose
responses will be learned per-user over time.

Usage:
    python -m scripts.seed_food_db
"""

from src.utils.nutrition_db import NUTRITION_DB


def main():
    print("Common foods in MetaboCoach nutrition database:")
    print("=" * 60)

    for name, data in sorted(NUTRITION_DB.items()):
        gi = data.get("gi", "?")
        cal = data["calories"]
        protein = data["protein_g"]
        carbs = data["carbs_g"]
        serving = data.get("serving_g", 100)
        print(
            f"  {name:<25} {cal:>4} cal | {protein:>5.1f}g P | "
            f"{carbs:>5.1f}g C | GI: {gi:<6} | Serving: {serving}g"
        )

    print(f"\nTotal: {len(NUTRITION_DB)} foods")
    print("\nThese serve as baseline estimates. Per-user glucose responses")
    print("are learned automatically from correlated glucose + meal data.")


if __name__ == "__main__":
    main()
