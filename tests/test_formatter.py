import pytest
from app.services.report_formatter import ReportFormatter

def test_format_no_trades():
    msg = ReportFormatter.format_no_trades("2023-10-27")
    assert "今日無交易" in msg
    assert "2023-10-27" in msg

def test_format_daily_report():
    stats = {
        "count": 2, "total_r": 1.5, "avg_r": 0.75, "win_rate": 50.0,
        "max_consecutive_loss": 1, "max_drawdown": -1.0
    }
    analysis = {
        "classification": {"FOMO": 1, "無明顯錯誤": 1},
        "major_mistake": "FOMO"
    }
    trades = [
        {"pair": "BTC", "direction": "Long", "r": 2.5, "note": "Good"},
        {"pair": "ETH", "direction": "Short", "r": -1.0, "note": "Bad"}
    ]

    msg = ReportFormatter.format_daily_report("2023-10-27", stats, analysis, trades)

    assert "今日交易回顧" in msg
    assert "+1.5R" in msg
    assert "FOMO：1" in msg
    assert "BTC Long +2.5R" in msg
    assert "ETH Short -1.0R" in msg
