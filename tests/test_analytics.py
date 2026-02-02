import pytest
from app.services.analytics import AnalyticsService

def test_calculate_stats_empty():
    stats = AnalyticsService.calculate_stats([])
    assert stats["count"] == 0
    assert stats["total_r"] == 0.0

def test_calculate_stats_basic():
    trades = [
        {"r": 1.0}, {"r": -0.5}, {"r": 2.0}
    ]
    stats = AnalyticsService.calculate_stats(trades)
    assert stats["count"] == 3
    assert stats["total_r"] == 2.5
    assert stats["avg_r"] == round(2.5/3, 2)
    assert stats["win_rate"] == round((2/3)*100, 1)

def test_calculate_stats_consecutive_loss():
    trades = [
        {"r": -1}, {"r": -1}, {"r": 1}, {"r": -1}, {"r": -1}, {"r": -1}
    ]
    stats = AnalyticsService.calculate_stats(trades)
    assert stats["max_consecutive_loss"] == 3

def test_calculate_stats_drawdown():
    # Equity: 0 -> 1 -> -1 (peak 1, dd 2) -> -2 (peak 1, dd 3) -> 0
    trades = [
        {"r": 1}, {"r": -2}, {"r": -1}, {"r": 2}
    ]
    # Curve: 0, 1, -1, -2, 0.
    # Peak starts at 1.
    # 1 -> peak 1, dd 0
    # -1 -> peak 1, dd 2
    # -2 -> peak 1, dd 3 (Max)
    # 0 -> peak 1, dd 1
    stats = AnalyticsService.calculate_stats(trades)
    assert stats["max_drawdown"] == -3.0
