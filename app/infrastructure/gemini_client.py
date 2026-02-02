import google.generativeai as genai
from app.config.settings import settings
from app.config.logging import logger
import json
import typing

class GeminiClient:
    def __init__(self):
        if not settings.GEMINI_API_KEY:
             logger.warning("GEMINI_API_KEY is not set.")
        else:
             genai.configure(api_key=settings.GEMINI_API_KEY)
             # Using gemini-1.5-flash as it is fast and cost-effective for this task
             self.model = genai.GenerativeModel('gemini-1.5-flash')

    def analyze_trades(self, trades: list[dict]) -> dict:
        if not settings.GEMINI_API_KEY:
            return {}

        # Prepare trade data for prompt, keeping only relevant fields to save tokens
        clean_trades = [
            {k: v for k, v in t.items() if k in ['pair', 'direction', 'r', 'note']}
            for t in trades
        ]

        prompt = f"""
        Analyze the following trading journal entries for today.

        Input Data:
        {json.dumps(clean_trades, indent=2, ensure_ascii=False)}

        Task:
        1. Classify each trade error pattern based on the 'note' and 'r' value. Categories:
           - FOMO (Fear Of Missing Out)
           - 提早出場 (Early Exit)
           - 停損放大 (Stop Loss Expanded / Did not respect stop loss)
           - 無系統進場 (No System Entry / Random entry)
           - 無明顯錯誤 (No Obvious Error / Followed rules)
        2. Identify the SINGLE most "Burning Error" (最主要燒錢錯誤). This should be the error category that caused the most accumulated loss (negative R) or is the most frequent if losses are similar.

        Output Format (JSON Only):
        {{
          "classification": {{
            "FOMO": count,
            "提早出場": count,
            "停損放大": count,
            "無系統進場": count,
            "無明顯錯誤": count
          }},
          "major_mistake": "Name of the major error category (e.g. FOMO)"
        }}
        """

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"Gemini analysis failed: {e}")
            return {}
