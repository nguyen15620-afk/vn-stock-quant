import os
import time
import requests
import schedule
import pandas as pd
from datetime import datetime
import pytz

from data_loader import load_historical_data, load_fundamentals, VN30
from strategy import compute_indicators, generate_signals

# Lấy token từ biến môi trường hoặc điền trực tiếp
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

def send_telegram_message(message: str):
    """Gửi tin nhắn qua Telegram Bot"""
    if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("Vui lòng cấu hình TELEGRAM_BOT_TOKEN trước khi sử dụng.")
        print("Nội dung tin nhắn dự kiến gửi:\n", message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Đã gửi thông báo Telegram thành công.")
    except Exception as e:
        print(f"Lỗi khi gửi Telegram: {e}")

def run_quant_scan():
    """Chạy kịch bản quét chứng khoán và gửi báo cáo"""
    print(f"\n--- Bắt đầu quét thị trường lúc {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    
    # 1. Quét VNINDEX để lấy Market Regime
    market_regime_series = None
    df_vnindex = load_historical_data("VNINDEX", months=6)
    if not df_vnindex.empty:
        df_vnindex['sma50'] = df_vnindex['close'].rolling(50).mean()
        df_vnindex['date_str'] = df_vnindex['time'].dt.strftime('%Y-%m-%d')
        df_vnindex.set_index('date_str', inplace=True)
        market_regime_series = df_vnindex['close'] > df_vnindex['sma50']
        
        # Lấy trạng thái hiện tại
        last_vn = df_vnindex.iloc[-1]
        market_status = "TÍCH CỰC" if last_vn['close'] > last_vn['sma50'] else "TIÊU CỰC"
    else:
        market_status = "KHÔNG RÕ"

    buy_signals = []
    
    # 2. Quét VN30
    tickers_to_scan = VN30
    for i, sym in enumerate(tickers_to_scan):
        print(f"Đang phân tích {sym} ({i+1}/{len(tickers_to_scan)})...")
        
        # Lọc FA cơ bản (ROE > 10%, P/E < 25)
        fa = load_fundamentals(sym)
        pe = fa.get("PE")
        roe = fa.get("ROE")
        
        if not (pe and roe and 0 < pe < 25 and roe > 0.1):
            continue  # Bỏ qua nếu FA xấu
            
        # Lấy kỹ thuật (6 tháng)
        df_scan = load_historical_data(sym, months=6) 
        if df_scan.empty:
            continue
            
        df_scan['date_str'] = df_scan['time'].dt.strftime('%Y-%m-%d')
        df_scan.set_index('date_str', inplace=True, drop=False)
        
        df_scan = compute_indicators(df_scan)
        # Kết hợp cả Market Regime và Khung Tuần (MTF)
        df_scan = generate_signals(df_scan, strategy_type='trend', market_regime=market_regime_series, use_mtf=True)
        
        latest_scan = df_scan.iloc[-1]
        if latest_scan['signal'] == 'Buy':
            buy_signals.append({
                'ticker': sym,
                'price': latest_scan['close'],
                'score': latest_scan['score'],
                'reason': latest_scan['reason'],
                'pe': pe,
                'roe': roe
            })

    # 3. Tổng hợp tin nhắn Telegram
    msg = f"🔔 <b>BÁO CÁO QUANT TRƯỚC PHIÊN ATC ({datetime.now().strftime('%d/%m/%Y')})</b>\n"
    msg += f"📊 Trạng thái VN-INDEX: <b>{market_status}</b>\n"
    msg += f"📋 Bộ lọc: Xu hướng + Khung Tuần (MTF) + Cơ bản (P/E<25, ROE>10%)\n"
    msg += "------------------------\n"
    
    if not buy_signals:
        msg += "❌ Không có mã VN30 nào đạt tiêu chuẩn MUA ngày hôm nay."
    else:
        msg += f"✅ Phát hiện <b>{len(buy_signals)}</b> mã đạt tiêu chuẩn MUA:\n\n"
        for s in buy_signals:
            msg += f"🚀 <b>{s['ticker']}</b> - Giá: {s['price']:,.0f}\n"
            msg += f"   • Điểm s/mạnh: {s['score']}/100\n"
            msg += f"   • P/E: {s['pe']:.1f} | ROE: {s['roe']*100:.1f}%\n"
            msg += f"   • Lý do: {s['reason']}\n\n"
            
    send_telegram_message(msg)
    print("--- Hoàn tất quét ---")

def job():
    run_quant_scan()

if __name__ == "__main__":
    import sys
    
    # Nếu chạy với flag --test, chạy ngay 1 lần để test
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("Chạy chế độ TEST...")
        run_quant_scan()
        sys.exit(0)
        
    print("🤖 Bot Telegram Quant Trading đã khởi động.")
    print("Lịch trình: Quét và gửi thông báo vào 14:30 mỗi ngày (T2-T6).")
    
    # Đặt lịch 14:30
    schedule.every().monday.at("14:30").do(job)
    schedule.every().tuesday.at("14:30").do(job)
    schedule.every().wednesday.at("14:30").do(job)
    schedule.every().thursday.at("14:30").do(job)
    schedule.every().friday.at("14:30").do(job)

    while True:
        schedule.run_pending()
        time.sleep(60)
