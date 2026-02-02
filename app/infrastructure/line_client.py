import requests
from app.config.settings import settings
from app.config.logging import logger

class LineNotifyClient:
    API_URL = "https://notify-api.line.me/api/notify"

    def __init__(self):
        self.token = settings.LINE_NOTIFY_TOKEN

    def send_message(self, message: str):
        if not self.token:
            logger.warning("LINE_NOTIFY_TOKEN is not set. Skipping message.")
            return

        headers = {"Authorization": f"Bearer {self.token}"}
        # Line Notify max message length is 1000 characters.
        # We might need to split if it's too long, but for now we assume it fits.
        payload = {"message": message}

        # Retry logic: Try once, if fail, try again.
        max_retries = 2
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(self.API_URL, headers=headers, data=payload, timeout=10)
                response.raise_for_status()
                logger.info("Line Notify message sent successfully.")
                return
            except Exception as e:
                error_msg = str(e)
                if isinstance(e, requests.exceptions.HTTPError):
                    error_msg = f"{e} Response: {e.response.text}"

                logger.warning(f"Failed to send Line Notify message (Attempt {attempt}/{max_retries}): {error_msg}")
                if attempt == max_retries:
                    logger.error("All retry attempts failed for Line Notify.")
