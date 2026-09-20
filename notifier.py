import os
import requests
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def send_telegram_message(message: str) -> bool:
    """
    Gửi tin nhắn tùy chỉnh qua Telegram Bot (hỗ trợ HTML parse mode).
    Cần cấu hình TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID trong biến môi trường hoặc .env.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id or bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.warning("Telegram bot token hoặc chat ID chưa được cấu hình. Bỏ qua gửi tin nhắn.")
        return False
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Đã gửi tin nhắn Telegram thành công.")
        return True
    except Exception as e:
        logger.error(f"Lỗi gửi tin nhắn Telegram: {e}")
        return False

def send_telegram_alert(ticker: str, decision: str, summary: str) -> bool:
    """
    Gửi thông báo Telegram khi có tín hiệu MUA hoặc BÁN.
    """
    message = (
        f"🚀 <b>TÍN HIỆU {decision} - {ticker}</b>\n\n"
        f"{summary}"
    )
    return send_telegram_message(message)
