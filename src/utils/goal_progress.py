import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .logger import log


BAR_FILLED = "▓"
BAR_EMPTY = "░"
BAR_LENGTH = 16
MILESTONE_THRESHOLDS = (25, 50, 75, 100)
STATE_FILE = Path(__file__).resolve().parents[2] / "runtime" / "discord_goal_state.json"


def build_monthly_goal_progress(current_pnl: float, target_pnl: float, now: datetime) -> Dict[str, float]:
    if target_pnl <= 0:
        raise ValueError("target_pnl must be greater than 0")

    raw_pct = (current_pnl / target_pnl) * 100
    display_pct = max(raw_pct, 0.0)
    bar_pct = min(display_pct, 100.0)
    filled_cells = min(max(round(bar_pct / 100 * BAR_LENGTH), 0), BAR_LENGTH)

    return {
        "month_label": f"{now.month}月",
        "current": current_pnl,
        "target": target_pnl,
        "raw_pct": raw_pct,
        "display_pct": display_pct,
        "bar": (BAR_FILLED * filled_cells) + (BAR_EMPTY * (BAR_LENGTH - filled_cells)),
        "remaining": max(target_pnl - current_pnl, 0.0),
        "surplus": max(current_pnl - target_pnl, 0.0),
        "achieved": current_pnl >= target_pnl,
    }


def format_currency(value: float) -> str:
    return f"${round(value):,.0f}"


def format_signed_currency(value: float) -> str:
    rounded = round(value)
    sign = "+" if rounded >= 0 else "-"
    return f"{sign}${abs(rounded):,}"


def load_goal_milestone_state() -> Dict[str, List[int]]:
    if not STATE_FILE.exists():
        return {}

    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning(f"Failed to load Discord goal milestone state: {exc}")
        return {}

    if not isinstance(state, dict):
        log.warning("Discord goal milestone state is not a JSON object. Resetting state.")
        return {}

    normalized_state: Dict[str, List[int]] = {}
    for month_key, milestones in state.items():
        if not isinstance(month_key, str) or not isinstance(milestones, list):
            continue

        normalized_values: List[int] = []
        for milestone in milestones:
            try:
                normalized_values.append(int(milestone))
            except (TypeError, ValueError):
                continue

        normalized_state[month_key] = sorted(set(normalized_values))

    return normalized_state


def save_goal_milestone_state(state: Dict[str, List[int]]) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        serializable_state = {
            month_key: sorted(set(int(value) for value in milestones))
            for month_key, milestones in state.items()
            if isinstance(month_key, str)
        }
        STATE_FILE.write_text(
            json.dumps(serializable_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning(f"Failed to save Discord goal milestone state: {exc}")


def get_newly_crossed_milestones(progress: Dict[str, float], month_key: str, state: Dict[str, List[int]]) -> List[int]:
    sent_milestones = {
        int(value)
        for value in state.get(month_key, [])
        if isinstance(value, (int, float, str))
    }
    return [
        milestone
        for milestone in MILESTONE_THRESHOLDS
        if progress["display_pct"] >= milestone and milestone not in sent_milestones
    ]

