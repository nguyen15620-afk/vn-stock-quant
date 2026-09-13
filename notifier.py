import os
import requests

def send_telegram_alert(ticker: str, decision: str, summary: str):
    """
    Gửi thông báo Telegram khi có tín hiệu MUA.
    Cần cấu hình TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID trong biến môi trường.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("Telegram bot token or chat ID is missing. Skipping alert.")
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    message = (
        f"🚀 <b>TÍN HIỆU {decision} - {ticker}</b>\n\n"
        f"{summary}"
    )
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"✅ Đã gửi cảnh báo Telegram cho mã {ticker}")
    except Exception as e:
        print(f"❌ Lỗi gửi Telegram: {e}")
