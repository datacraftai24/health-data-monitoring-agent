"""Glucose math utilities — rate of change, trend analysis, conversions."""


def mmol_to_mgdl(mmol: float) -> float:
    """Convert mmol/L to mg/dL."""
    return round(mmol * 18.0182, 1)


def mgdl_to_mmol(mgdl: float) -> float:
    """Convert mg/dL to mmol/L."""
    return round(mgdl / 18.0182, 1)


def trend_arrow_to_label(arrow: int | None) -> str | None:
    """Convert LibreLink trend arrow integer to human-readable label.

    1 = falling fast, 2 = falling, 3 = stable, 4 = rising, 5 = rising fast
    """
    mapping = {
        1: "falling_fast",
        2: "falling",
        3: "stable",
        4: "rising",
        5: "rising_fast",
    }
    return mapping.get(arrow) if arrow else None


def is_in_range(glucose: float, low: float = 3.9, high: float = 9.0) -> bool:
    """Check if glucose value is within target range."""
    return low <= glucose <= high


def classify_glucose(glucose: float) -> str:
    """Classify a glucose reading."""
    if glucose < 3.0:
        return "very_low"
    elif glucose < 3.9:
        return "low"
    elif glucose <= 9.0:
        return "normal"
    elif glucose <= 10.0:
        return "elevated"
    elif glucose <= 13.9:
        return "high"
    else:
        return "very_high"


def estimated_a1c(avg_glucose_mmol: float) -> float:
    """Estimate HbA1c from average glucose (mmol/L).

    Uses the ADAG formula: eA1C = (avg_glucose_mgdl + 46.7) / 28.7
    """
    avg_mgdl = mmol_to_mgdl(avg_glucose_mmol)
    return round((avg_mgdl + 46.7) / 28.7, 1)
