import os
import sys
import time
import schedule
import pandas as pd
from datetime import datetime
import pytz
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Load biến môi trường
load_dotenv()

# Thiết lập thư mục logs
os.makedirs("logs", exist_ok=True)
logger = logging.getLogger("AlertBot")
logger.setLevel(logging.INFO)

# Handler console
c_handler = logging.StreamHandler(sys.stdout)
c_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
logger.addHandler(c_handler)

# Handler rotating file log
f_handler = RotatingFileHandler("logs/quant_alert.log", maxBytes=2*1024*1024, backupCount=5, encoding="utf-8")
f_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
logger.addHandler(f_handler)

from data_loader import load_historical_data, load_fundamentals, VN30
from strategy import compute_indicators, generate_signals
from notifier import send_telegram_message
from gemini_bridge_client import is_edge_cdp_available, ask_gemini_4_argon_sync, format_candidates_payload

def heartbeat_check():
    """Kiểm tra kết nối tới Edge CDP lúc 14:15 để đảm bảo Gemini 4 Argon sẵn sàng trước giờ G."""
    logger.info("--- [14:15] Thực hiện Pre-flight Heartbeat Check tới Gemini 4 Argon ---")
    status = is_edge_cdp_available()
    if not status.get("available") or not status.get("tab_found"):
        err_msg = status.get("error", "Không xác định")
        warn_text = (
            f"⚠️ <b>[CẢNH BÁO HỆ THỐNG - 14:15]</b>\n"
            f"Cầu nối Gemini 4 Argon (Edge CDP Port 9222) chưa sẵn sàng!\n"
            f"• Chi tiết: <code>{err_msg}</code>\n"
            f"• Hành động: Vui lòng chạy <code>start_edge_debug.bat</code> và mở tab Gemini trước 14:25 để nhận phân tích ATC đầy đủ."
        )
        logger.warning(warn_text)
        send_telegram_message(warn_text)
    else:
        logger.info(f"✅ Edge CDP Bridge đang hoạt động tốt (Tab: {status.get('model')}). Sẵn sàng cho phiên ATC!")

def run_quant_scan(enable_ai_verdict: bool = True):
    """
    Chạy kịch bản Dual-Stage Alert:
    - Pha 1 (14:26): Bắn tín hiệu kỹ thuật thô từ Python sang Telegram.
    - Pha 2 (14:28): Nén dữ liệu gửi sang Gemini 4 Argon và bắn nhận định chiến lược ATC.
    """
    logger.info(f"--- Bắt đầu quy trình quét Dual-Stage lúc {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    
    # 1. Quét VNINDEX để lấy Market Regime
    market_regime_series = None
    df_vnindex = load_historical_data("VNINDEX", months=6)
    vnindex_val = 0.0
    vnindex_ma50 = 0.0
    if not df_vnindex.empty:
        df_vnindex['sma50'] = df_vnindex['close'].rolling(50).mean()
        df_vnindex['date_str'] = df_vnindex['time'].dt.strftime('%Y-%m-%d')
        df_vnindex.set_index('date_str', inplace=True)
        market_regime_series = df_vnindex['close'] > df_vnindex['sma50']
        
        last_vn = df_vnindex.iloc[-1]
        vnindex_val = float(last_vn['close'])
        vnindex_ma50 = float(last_vn['sma50'])
        market_status = "TÍCH CỰC (BULL MARKET)" if vnindex_val > vnindex_ma50 else "THẬN TRỌNG (BEAR/SIDEWAY)"
    else:
        market_status = "KHÔNG RÕ"

    buy_signals = []
    
    # 2. Quét VN30
    tickers_to_scan = VN30
    for i, sym in enumerate(tickers_to_scan):
        logger.info(f"Đang phân tích {sym} ({i+1}/{len(tickers_to_scan)})...")
        
        # Lọc FA cơ bản (ROE > 10%, P/E < 25)
        fa = load_fundamentals(sym)
        pe = fa.get("PE")
        roe = fa.get("ROE")
        
        if not (pe and roe and 0 < pe < 25 and roe > 0.1):
            continue
            
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
            # Tính Close Location Value (CLV)
            high_val = float(latest_scan.get('high', latest_scan['close']))
            low_val = float(latest_scan.get('low', latest_scan['close']))
            close_val = float(latest_scan['close'])
            clv = (close_val - low_val) / (high_val - low_val) if high_val > low_val else 0.8
            
            # Tỷ lệ volume so với MA20
            vol_curr = float(latest_scan.get('volume', 0))
            vol_ma20 = float(latest_scan.get('vol_sma20', vol_curr)) if 'vol_sma20' in latest_scan else vol_curr
            vol_ratio = (vol_curr / vol_ma20) if vol_ma20 > 0 else 1.5

            buy_signals.append({
                'ticker': sym,
                'price': close_val,
                'high': high_val,
                'low': low_val,
                'clv': clv,
                'vol_ratio': vol_ratio,
                'rsi': float(latest_scan.get('rsi', 50)),
                'macd_hist': float(latest_scan.get('macd_hist', 0)),
                'score': latest_scan['score'],
                'reason': latest_scan['reason'],
                'pe': pe,
                'roe': roe
            })

    # Sắp xếp các mã có điểm kỹ thuật cao nhất lên đầu (Top 5)
    buy_signals.sort(key=lambda x: x['score'], reverse=True)
    top_candidates = buy_signals[:5]

    # ==========================================
    # PHA 1: CẢNH BÁO QUANT THÔ (14:26)
    # ==========================================
    msg_p1 = f"⚡ <b>[CẢNH BÁO QUANT PHA 1 - 14:26]</b>\n"
    msg_p1 += f"📊 VN-INDEX: <b>{vnindex_val:,.1f}</b> (MA50: {vnindex_ma50:,.1f}) - {market_status}\n"
    msg_p1 += f"📋 Bộ lọc: Trend Following + MTF Tuần + P/E&lt;25 + ROE&gt;10%\n"
    msg_p1 += "------------------------------------\n"
    
    if not top_candidates:
        msg_p1 += "❌ Không có mã VN30 nào đạt chuẩn MUA phiên hôm nay.\n"
        msg_p1 += "💡 Khuyến nghị: Giữ tỷ trọng tiền mặt, quan sát thị trường."
        send_telegram_message(msg_p1)
        logger.info("--- Hoàn tất quét (Không có mã mua) ---")
        return market_status, [], msg_p1, ""
    else:
        msg_p1 += f"🎯 Phát hiện <b>{len(top_candidates)}</b> mã tiềm năng:\n\n"
        for s in top_candidates:
            msg_p1 += f"🚀 <b>{s['ticker']}</b> - Giá: {s['price']:,.0f} ₫ (Điểm: {s['score']}/100)\n"
            msg_p1 += f"   • Nến CLV: {s['clv']:.2f} | Vol: {s['vol_ratio']:.1f}x MA20\n"
            msg_p1 += f"   • Tín hiệu: {s['reason']}\n\n"
        msg_p1 += "⏳ <i>Đang nạp dữ liệu sang Gemini 4 Argon Pro thẩm định chiến lược ATC...</i>"
        send_telegram_message(msg_p1)
        logger.info("Đã gửi cảnh báo Pha 1 qua Telegram.")

    # ==========================================
    # PHA 2: THẨM ĐỊNH CHIẾN LƯỢC AI (14:28)
    # ==========================================
    ai_verdict = ""
    if enable_ai_verdict and top_candidates:
        logger.info("Bắt đầu Pha 2: Gửi dữ liệu sang Gemini 4 Argon...")
        payload = format_candidates_payload(top_candidates, vnindex_val, vnindex_ma50, market_status)
        
        prompt = (
            "=== [CHUYÊN GIA CHIẾN LƯỢC CHỨNG KHOÁN VIỆT NAM (GEMINI 4 ARGON PRO)] ===\n\n"
            f"{payload}\n\n"
            "Hãy đóng vai Quantitative Trading Strategist, đưa ra nhận định chốt trước phiên ATC (14:30 - 14:45):\n"
            "1. Đánh giá nhanh rủi ro T+2.5 hôm nay (thứ mấy trong tuần) và VN-INDEX.\n"
            "2. Với từng mã trong Top trên: Nhận định MUA ATC / CHỜ RUNG LẮC / BỎ QUA (xét CLV nến nội phiên, bẫy bull-trap, thanh khoản).\n"
            "3. Kế hoạch cụ thể: Tỷ trọng giải ngân (% NAV), Giá mua mục tiêu, Cắt lỗ động và Chốt lời.\n\n"
            "Định dạng ngắn gọn, súc tích, chuyên nghiệp cho bản tin Telegram."
        )
        
        success, ai_verdict = ask_gemini_4_argon_sync(prompt, timeout_sec=60)
        if success and ai_verdict:
            msg_p2 = f"🧠 <b>[KHUYẾN NGHỊ CHIẾN LƯỢC GEMINI 4 ARGON - 14:28]</b> ⚡\n\n"
            msg_p2 += ai_verdict.strip()
            msg_p2 += "\n\n💡 <i>Khuyến nghị độc quyền từ Gemini 4 Argon Pro trước phiên ATC.</i>"
            send_telegram_message(msg_p2)
            logger.info("Đã gửi khuyến nghị chiến lược Pha 2 từ Gemini 4 Argon qua Telegram.")
        else:
            logger.warning(f"Không thể lấy nhận định từ Gemini 4 Argon: {ai_verdict}")
            msg_fallback = (
                "⚠️ <b>[THÔNG BÁO TỪ GEMINI BRIDGE - 14:28]</b>\n"
                "Không thể kết nối với Gemini 4 Argon trong thời gian quy định (Timeout hoặc Edge chưa mở).\n"
                "👉 Quý nhà đầu tư vui lòng chủ động ra quyết định theo tín hiệu kỹ thuật tại <b>Pha 1</b>."
            )
            send_telegram_message(msg_fallback)

    logger.info("--- Hoàn tất quy trình quét Dual-Stage ---")
    return market_status, top_candidates, msg_p1, ai_verdict

def job_heartbeat():
    heartbeat_check()

def job_quant_scan():
    run_quant_scan(enable_ai_verdict=True)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        logger.info("Chạy chế độ TEST DUAL-STAGE...")
        run_quant_scan(enable_ai_verdict=True)
        sys.exit(0)
        
    if len(sys.argv) > 1 and sys.argv[1] == "--heartbeat":
        heartbeat_check()
        sys.exit(0)

    logger.info("🤖 Bot Telegram Quant Trading & Gemini 4 Argon đã khởi động.")
    logger.info("Lịch trình vận hành:")
    logger.info("  • 14:15 - Pre-flight Heartbeat check kết nối Edge CDP")
    logger.info("  • 14:25 - Quét Quant VN30 & Bắn cảnh báo Pha 1 (14:26) + Pha 2 AI (14:28)")

    for day in [schedule.every().monday, schedule.every().tuesday, schedule.every().wednesday, schedule.every().thursday, schedule.every().friday]:
        day.at("14:15").do(job_heartbeat)
        day.at("14:25").do(job_quant_scan)

    while True:
        schedule.run_pending()
        time.sleep(30)
