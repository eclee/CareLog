"""Validation and display rules for measured values."""

from decimal import Decimal, InvalidOperation


def weight_kg(raw):
    """Accept a finite weight in kg with no more than two meaningful decimals."""
    try:
        value = Decimal(str(raw).strip())
        rounded = value.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError("體重必須是有效數字") from None
    if not value.is_finite() or not 20 <= value <= 300 or value != rounded:
        raise ValueError("體重須為 20 至 300 公斤，且最多兩位小數")
    return float(rounded)
