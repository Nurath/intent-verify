from decimal import Decimal, ROUND_HALF_UP
def round_price(x):
    """Round a price to 2 decimals, half up."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
