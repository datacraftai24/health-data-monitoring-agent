"""Message formatting utilities for WhatsApp and Telegram."""


def format_glucose_status(glucose: float, trend: str | None = None) -> str:
    """Format current glucose reading for display."""
    emoji = "🩸"
    if glucose < 3.9:
        emoji = "🔴"
    elif glucose > 10.0:
        emoji = "🟡"
    else:
        emoji = "🟢"

    trend_emoji = ""
    if trend:
        trend_map = {
            "falling_fast": "⬇️⬇️",
            "falling": "⬇️",
            "stable": "➡️",
            "rising": "⬆️",
            "rising_fast": "⬆️⬆️",
        }
        trend_emoji = f" {trend_map.get(trend, '')}"

    return f"{emoji} {glucose:.1f} mmol/L{trend_emoji}"


def format_macro_summary(calories: int, protein: float, carbs: float, fat: float) -> str:
    """Format macros into a compact summary."""
    return f"{calories} cal | {protein:.0f}g P | {carbs:.0f}g C | {fat:.0f}g F"


def format_daily_progress(
    calories: int, calorie_target: int,
    protein: float, protein_target: int,
    steps: int, step_target: int = 10000,
) -> str:
    """Format daily progress bars."""
    cal_pct = min(100, int((calories / calorie_target) * 100)) if calorie_target else 0
    pro_pct = min(100, int((protein / protein_target) * 100)) if protein_target else 0
    step_pct = min(100, int((steps / step_target) * 100))

    cal_check = "✅" if cal_pct >= 80 else "⚠️" if cal_pct < 50 else ""
    pro_check = "✅" if pro_pct >= 80 else "⚠️" if pro_pct < 50 else ""
    step_check = "✅" if step_pct >= 80 else ""

    return (
        f"🍽️ Calories: {calories} / {calorie_target} {cal_check}\n"
        f"💪 Protein: {protein:.0f}g / {protein_target}g {pro_check}\n"
        f"🚶 Steps: {steps:,} / {step_target:,} {step_check}"
    )


def truncate_message(text: str, max_length: int = 1600) -> str:
    """Truncate message to fit WhatsApp/Telegram limits."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
