from typing import Optional, Tuple

from project_code.entry_exit import SwingLevels, update_last_swing_levels


def update_swings_from_bars(
    bars: list,
    N_candidates: list,
    N_confirmation: int,
    min_move_threshold: float,
    min_bars_between_swings: int,
    swing_levels: SwingLevels,
    last_applied_index: int,
    last_swing_high_bar_index: Optional[int] = None,
    last_swing_low_bar_index: Optional[int] = None,
) -> Tuple[SwingLevels, int, Optional[int], Optional[int]]:
    """Run swing detection on recent bars and return (swing_levels, last_applied_index).

    Pure-Python implementation — no pandas overhead on every bar.
    """
    max_n = max(N_candidates)
    lookback = max_n + N_confirmation + 50
    start = max(0, len(bars) - lookback)
    n = len(bars) - start

    if n < N_confirmation + max_n:
        return swing_levels, last_applied_index, last_swing_high_bar_index, last_swing_low_bar_index

    high_idx = last_swing_high_bar_index
    low_idx = last_swing_low_bar_index

    closes = [bars[start + i].close for i in range(n)]
    highs = [bars[start + i].high for i in range(n)]
    lows = [bars[start + i].low for i in range(n)]

    result_map: dict[int, tuple[float, float]] = {}
    last_swing_pos = -min_bars_between_swings - 1

    for N in N_candidates:
        for i in range(N_confirmation, n):
            idx = i - N_confirmation
            if (idx - last_swing_pos) < min_bars_between_swings:
                continue
            left = max(0, idx - N)
            right = idx + 1
            candidate = closes[idx]
            w = closes[left:right]
            mx = max(w)
            mn = min(w)

            if candidate == mx:
                if min_move_threshold == 0 or (candidate - mn) / candidate >= min_move_threshold:
                    result_map[idx] = (1.0, highs[idx])
                    last_swing_pos = idx
            elif candidate == mn:
                if min_move_threshold == 0 or (mx - candidate) / candidate >= min_move_threshold:
                    result_map[idx] = (-1.0, lows[idx])
                    last_swing_pos = idx

    for local_idx in sorted(result_map.keys()):
        global_idx = start + local_idx
        if global_idx <= last_applied_index:
            continue
        highlow, level = result_map[local_idx]
        swing_levels = update_last_swing_levels(
            swing_levels, highlow_flag=highlow, level=level,
        )
        last_applied_index = global_idx
        if highlow == 1.0:
            high_idx = global_idx
        elif highlow == -1.0:
            low_idx = global_idx

    return swing_levels, last_applied_index, high_idx, low_idx
