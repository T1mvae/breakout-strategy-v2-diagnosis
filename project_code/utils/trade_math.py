import math
from typing import Optional, Tuple

from project_code.entry_exit import PositionDirection


def realized_close_pnl(
    *,
    direction: PositionDirection,
    entry_price: float,
    fill_price: float,
    qty_closed: float,
) -> float:
    qty = abs(float(qty_closed))
    if qty <= 0:
        return 0.0
    if direction == PositionDirection.LONG:
        return (float(fill_price) - float(entry_price)) * qty
    return (float(entry_price) - float(fill_price)) * qty


def round_price_for_security(security, price: float) -> float:
    tick = float(security.SymbolProperties.MinimumPriceVariation)
    if tick <= 0:
        return float(price)
    return float(round(price / tick) * tick)


def round_quantity_for_security(security, qty: float, qty_decimals: int) -> float:
    if qty == 0:
        return 0.0

    lot = float(security.SymbolProperties.LotSize)
    abs_qty = abs(float(qty))
    if lot > 0:
        steps = math.floor(abs_qty / lot)
        abs_qty = steps * lot

    abs_qty = float(round(abs_qty, qty_decimals))
    if abs_qty <= 0:
        return 0.0
    return abs_qty if qty > 0 else -abs_qty


def safe_final_price(
    bars: list, qc_price: float
) -> Tuple[Optional[float], Optional[str]]:
    """Return (price, fallback_msg) for end-of-algo accounting.

    Returns None price when no trustworthy value is available.
    fallback_msg is set when QC price was rejected in favour of last bar close.
    """
    last_close = bars[-1].close if bars else None
    qc = float(qc_price)
    if last_close is not None and last_close > 0:
        if qc > 0 and 0.1 * last_close <= qc <= 10.0 * last_close:
            return qc, None
        return last_close, f"QC={qc:.2f} rejected, using last bar close={last_close:.2f}"
    if qc > 0 and qc < 1e7:
        return qc, None
    return None, None


def is_valid_entry_levels(
    direction: PositionDirection,
    entry: float,
    sl: float,
    tp: Optional[float],
) -> bool:
    """Check that entry / SL / TP are on the correct sides."""
    if entry <= 0 or sl <= 0:
        return False
    if direction == PositionDirection.LONG:
        if not (sl < entry):
            return False
        if tp is not None and not (entry < tp):
            return False
        return True
    if not (entry < sl):
        return False
    if tp is not None and not (tp < entry):
        return False
    return True
