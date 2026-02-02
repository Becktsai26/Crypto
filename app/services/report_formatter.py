from typing import Dict, List

class ReportFormatter:
    @staticmethod
    def format_daily_report(report_date: str, stats: Dict, analysis: Dict, trades: List[Dict]) -> str:
        """
        Formats the daily trading report into a Line Notify friendly message.
        """
        # Header
        lines = [f"📊 今日交易回顧 ({report_date})"]
        lines.append(f"交易筆數：{stats['count']}")
        lines.append("")

        # Stats
        lines.append("🔢 R績效")
        total_r_sign = '+' if stats['total_r'] > 0 else ''
        lines.append(f"總R：{total_r_sign}{stats['total_r']}R")

        avg_r_sign = '+' if stats['avg_r'] > 0 else ''
        lines.append(f"平均R：{avg_r_sign}{stats['avg_r']}R")

        lines.append(f"勝率：{stats['win_rate']}%")
        lines.append(f"最大連續虧損：{stats['max_consecutive_loss']}")
        lines.append(f"最大回撤：{stats['max_drawdown']}R")
        lines.append("")

        # Classification (Gemini)
        # If Gemini failed or no analysis returned, show fallback
        cls = analysis.get("classification", {})
        if cls:
            lines.append("⚠️ 錯誤模式")
            # Order is important for consistency
            categories = ["FOMO", "提早出場", "停損放大", "無系統進場", "無明顯錯誤"]
            for cat in categories:
                count = cls.get(cat, 0)
                lines.append(f"{cat}：{count}")
            lines.append("")

            major = analysis.get("major_mistake")
            if major:
                lines.append("🔥 最主要燒錢錯誤")
                lines.append(major)
                lines.append("")
        else:
             # Fallback if analysis failed or empty
             lines.append("⚠️ 錯誤模式")
             lines.append("（AI 分析暫時無法使用）")
             lines.append("")

        # Trade List
        if trades:
            lines.append("🧾 今日清單")
            for i, t in enumerate(trades, 1):
                r_val = float(t.get('r', 0))
                r_sign = '+' if r_val > 0 else ''
                r_str = f"{r_sign}{r_val}R"

                note = t.get("note", "")
                note_str = f"（{note}）" if note else ""

                pair = t.get('pair', 'Unknown')
                direction = t.get('direction', '')

                lines.append(f"{i}) {pair} {direction} {r_str}{note_str}")

        return "\n".join(lines)

    @staticmethod
    def format_no_trades(report_date: str) -> str:
        return f"📊 今日交易回顧 ({report_date})\n\n今日無交易 💤"
