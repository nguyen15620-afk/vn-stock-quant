import streamlit as st

# Cấu hình trang Streamlit (Bắt buộc là lệnh Streamlit đầu tiên)
st.set_page_config(
    page_title="VN Stock Quant & AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

try:
    import nest_asyncio
    nest_asyncio.apply()
except Exception:
    pass

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import asyncio
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# Load biến môi trường
load_dotenv()


# Nạp Design System & Custom CSS chuyên nghiệp
from styles import CUSTOM_CSS
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Nạp các thành phần giao diện & modules cốt lõi
from ui_components import (
    render_header,
    render_watchlist_cards,
    render_master_decision_card,
    render_agent_reports,
    render_advanced_chart,
    render_kpi_dashboard,
    render_equity_comparison_chart,
    render_financial_metrics_bar
)
from data_loader import load_historical_data, load_fundamentals, VN30
from data_fetcher import get_fundamental_data, get_macro_flow, get_latest_news
from strategy import compute_indicators, generate_signals
from ai_agents import analyze_stock_async, configure_gemini, QuotaExceededError, CascadeExecutionError
from notifier import send_telegram_alert, send_telegram_message
from backtester import run_backtest
from alert_bot import run_quant_scan, heartbeat_check
from gemini_bridge_client import is_edge_cdp_available, ask_gemini_4_argon_sync, ask_gemini_via_api

# ==============================================================================
# HÀM XỬ LÝ DỮ LIỆU BATCH ĐỒNG THỜI (ASYNC CONCURRENT)
# ==============================================================================

async def process_single_ticker(ticker: str, risk_profile: str, months: int, enable_telegram: bool, sem: asyncio.Semaphore, status_container):
    async with sem:
        status_container.write(f"▶️ Đang phân tích dữ liệu đa chiều cho mã **{ticker}**...")
        df = load_historical_data(ticker, months=months)
        if df.empty:
            status_container.warning(f"Không thể tải dữ liệu nến cho mã {ticker}. Bỏ qua.")
            return None, None
            
        fa_data = get_fundamental_data(ticker)
        market_data_str = get_macro_flow()
        news_data_str = get_latest_news(ticker)
        
        df = compute_indicators(df)
        current_price = df.iloc[-1]['close']
        
        tech_data_str = df[['time', 'close', 'volume', 'rsi', 'macd_hist']].tail(30).to_string(index=False)
        fa_data_str = json.dumps(fa_data, ensure_ascii=False) if isinstance(fa_data, dict) else str(fa_data)
        
        try:
            ai_results = await analyze_stock_async(
                ticker=ticker, 
                current_price=current_price, 
                tech_data=tech_data_str, 
                fa_data=fa_data_str, 
                market_data=market_data_str,
                news_data=news_data_str,
                risk_profile=risk_profile
            )
        except QuotaExceededError as qe:
            status_container.error(f"⚠️ Hết Quota API trên toàn bộ cascade khi phân tích {ticker}: {qe}")
            raise qe
        except CascadeExecutionError as ce:
            status_container.error(f"❌ Không thể phân tích mã {ticker} do lỗi kết nối LLM: {ce}")
            raise ce
        except Exception as e:
            status_container.error(f"Lỗi khi điều phối AI cho {ticker}: {e}")
            return None, None
            
        master = ai_results.get("master_decision", {})
        rec = str(master.get("recommendation", "GIỮ")).upper()
        order_action = str(master.get("order_action", rec)).upper()
        
        try:
            alloc_pct = int(master.get("allocation_pct", 0))
            alloc_pct = max(0, min(100, alloc_pct))
        except Exception:
            alloc_pct = 0

        try:
            vol_pct = int(master.get("volume_percent", alloc_pct))
            vol_pct = max(0, min(100, vol_pct))
        except Exception:
            vol_pct = alloc_pct

        try:
            target_price = float(master.get("target_price", current_price))
        except Exception:
            target_price = current_price

        try:
            sl_price = float(master.get("stop_loss", 0.0))
        except Exception:
            sl_price = 0.0

        try:
            tp_price = float(master.get("take_profit", 0.0))
        except Exception:
            tp_price = 0.0
        
        tcinvest_action = f"{ticker} - {order_action} - Tỷ trọng: {vol_pct}% - Giá: {target_price:,.0f}"
        
        summary_item = {
            "Mã CP": ticker,
            "Khuyến nghị": rec,
            "Action (TCInvest Order)": tcinvest_action,
            "Tỷ trọng (%)": alloc_pct,
            "Cắt lỗ (SL)": f"{sl_price:,.0f} ₫" if sl_price > 0 else "-",
            "Chốt lời (TP)": f"{tp_price:,.0f} ₫" if tp_price > 0 else "-",
            "Giá hiện tại": f"{current_price:,.0f} ₫"
        }
        
        detail_item = {
            "ai_results": ai_results,
            "df": df,
            "master": master,
            "fa_data": fa_data,
            "current_price": current_price
        }
        
        # Gửi thông báo Telegram nếu bật
        if enable_telegram and rec == "MUA":
            send_telegram_alert(ticker, rec, master.get("reasoning", ""))
            
        return summary_item, detail_item

async def process_entire_watchlist(tickers, risk_profile, months, enable_telegram, status_container):
    summary_data = []
    detailed_results = {}
    
    # Sử dụng Semaphore(3) để tối ưu tải và tôn trọng RPM
    sem = asyncio.Semaphore(3)
    tasks = [process_single_ticker(ticker, risk_profile, months, enable_telegram, sem, status_container) for ticker in tickers]
    
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                status_container.error(f"Lỗi khi xử lý {tickers[i]}: {res}")
            elif res and res[0] is not None:
                summary_data.append(res[0])
                detailed_results[tickers[i]] = res[1]
    except QuotaExceededError:
        status_container.error("⚠️ Quota API đã chạm giới hạn, dừng toàn bộ tiến trình.")
    except CascadeExecutionError:
        status_container.error("❌ Gặp sự cố kết nối tới các model AI trên toàn bộ cascade.")
        
    return summary_data, detailed_results

def run_async(coro):
    """Thực thi coroutine bất đồng bộ an toàn trong mọi môi trường Streamlit/Thread."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


# ==============================================================================
# SIDEBAR CONFIGURATION
# ==============================================================================

with st.sidebar:
    st.markdown("### ⚙️ Cấu Hình Hệ Thống")
    
    # API Key Input
    default_api_key = os.getenv("GEMINI_API_KEY", "")
    api_key_input = st.text_input(
        "🔑 Google GenAI API Key:",
        value=default_api_key,
        type="password",
        help="Lấy API Key miễn phí tại aistudio.google.com. Tự động nạp từ file .env nếu có."
    )
    if api_key_input:
        api_key_input = api_key_input.strip()

    st.markdown("---")
    st.markdown("#### 🎯 Khẩu Vị Rủi Ro")
    risk_profile = st.selectbox(
        "Hồ sơ rủi ro danh mục:",
        ["Thận trọng", "Cân bằng", "Mạo hiểm"],
        index=1,
        help="Thận trọng: Tỷ trọng 10-20%, SL chặt | Cân bằng: 20-40% | Mạo hiểm: 40-70%"
    )

    st.markdown("---")
    st.markdown("#### 🔔 Cảnh Báo Telegram")
    enable_telegram = st.checkbox("Bật gửi cảnh báo MUA qua Telegram", value=False)
    if enable_telegram:
        tg_bot_set = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
        tg_chat_set = bool(os.getenv("TELEGRAM_CHAT_ID"))
        if not (tg_bot_set and tg_chat_set):
            st.warning("⚠️ Chưa cấu hình TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID trong .env!")
        else:
            if st.button("🧪 Gửi tin nhắn thử nghiệm", use_container_width=True):
                ok = send_telegram_message("⚡ <b>VN Stock Quant Assistant</b>: Kết nối Telegram Bot thành công!")
                if ok:
                    st.success("✅ Đã gửi tin nhắn test thành công!")
                else:
                    st.error("❌ Gửi tin nhắn thất bại, hãy kiểm tra lại Token/Chat ID.")

    st.markdown("---")
    st.markdown("#### 🤖 Kiến Trúc Model Cascade")
    st.caption("• **Sub-Agents (3 Agent con):**\n  `gemini-3.5-flash` ➔ `3-flash-preview` ➔ `3.5-flash-lite` ➔ `3.6-flash`")
    st.caption("• **Master CIO (Ra Quyết Định):**\n  `gemini-3.5-flash` ➔ `3.6-flash` ➔ `3-flash-preview` ➔ `3.8` ➔ Fallback `3.5-Lite`")


# ==============================================================================
# TOP HEADER BAR
# ==============================================================================

render_header(
    api_key_configured=bool(api_key_input),
    master_model="gemini-3.5-flash",
    sub_model="gemini-3.5-flash"
)

# ==============================================================================
# MAIN NAVIGATION TABS (3 TABS)
# ==============================================================================

tab_ai, tab_argon, tab_backtest, tab_alert = st.tabs([
    "🚀 Phân Tích Đa Tác Tử AI (Multi-Agent)",
    "⚡ Tham Vấn Gemini 4 Argon (Edge CDP)",
    "📈 Kiểm Định Chiến Lược Quant (Backtest)",
    "🔔 Quản Lý & Cấu Hình Alert Bot"
])


# ==============================================================================
# TAB 1: PHÂN TÍCH ĐA TÁC TỬ AI (MULTI-AGENT)
# ==============================================================================

with tab_ai:
    # Vùng chọn nhanh mã cổ phiếu (Quick Pick Chips)
    st.markdown("##### 📌 Chọn nhanh mã Bluechip hoặc nhập tùy chỉnh:")
    
    # Quản lý danh sách mã đã chọn trong session_state
    if "selected_tickers_str" not in st.session_state:
        st.session_state.selected_tickers_str = "FPT, HPG"
        
    quick_tickers = ["FPT", "HPG", "VHM", "SSI", "MWG", "TCB", "VCB", "VND", "MSN"]
    chip_cols = st.columns(len(quick_tickers))
    for i, t in enumerate(quick_tickers):
        with chip_cols[i]:
            if st.button(t, key=f"chip_{t}", use_container_width=True):
                cur_list = [x.strip() for x in st.session_state.selected_tickers_str.split(",") if x.strip()]
                if t in cur_list:
                    cur_list.remove(t)
                else:
                    cur_list.append(t)
                st.session_state.selected_tickers_str = ", ".join(cur_list)
                st.rerun()

    # Hàng điều khiển quét phân tích
    col_input1, col_input2, col_input3 = st.columns([2.0, 1.2, 1.2])
    
    with col_input1:
        tickers_input = st.text_input(
            "Danh sách mã cần phân tích (ngăn cách bởi dấu phẩy):",
            value=st.session_state.selected_tickers_str,
            key="main_tickers_input"
        ).upper()
        # Đồng bộ ngược vào session_state
        st.session_state.selected_tickers_str = tickers_input

    with col_input2:
        months_preset = st.selectbox(
            "Chu kỳ dữ liệu:",
            ["12 Tháng (Khuyến nghị chuẩn)", "6 Tháng (Ngắn hạn)", "24 Tháng (Dài hạn)"],
            index=0
        )
        months_val = 12 if "12" in months_preset else (6 if "6" in months_preset else 24)

    with col_input3:
        st.write("")
        st.write("")
        analyze_btn = st.button("🚀 Quét Phân Tích Đồng Thời", type="primary", use_container_width=True)

    # Thực thi phân tích AI khi nhấn nút
    if analyze_btn:
        if not api_key_input:
            st.error("⚠️ Bạn cần cung cấp Google GenAI API Key (ở sidebar hoặc file .env) để chạy AI Agents!")
            st.stop()
            
        configure_gemini(api_key_input)
        
        tickers = [t.strip() for t in tickers_input.split(',') if t.strip()]
        if not tickers:
            st.error("⚠️ Vui lòng nhập ít nhất 1 mã cổ phiếu hợp lệ.")
            st.stop()

        status_box = st.status(f"🔍 Đang điều phối phân tích song song {len(tickers)} mã cổ phiếu...", expanded=True)
        summary_data, detailed_results = run_async(
            process_entire_watchlist(tickers, risk_profile, months_val, enable_telegram, status_box)
        )
        status_box.update(label="✅ Đã hoàn tất phân tích đa tác tử cho toàn bộ Watchlist!", state="complete", expanded=False)
        
        # Lưu kết quả vào session_state để không bị mất khi tương tác với UI
        st.session_state.last_summary_data = summary_data
        st.session_state.last_detailed_results = detailed_results

    # Hiển thị kết quả nếu đã có dữ liệu
    if "last_summary_data" in st.session_state and st.session_state.last_summary_data:
        summary_data = st.session_state.last_summary_data
        detailed_results = st.session_state.last_detailed_results
        
        st.markdown("---")
        st.markdown("### 📋 Tổng Quan Khuyến Nghị Watchlist")
        
        # 1. Thẻ Card Grid
        render_watchlist_cards(summary_data)
        
        # 2. Bảng tổng hợp dạng bảng dữ liệu
        with st.expander("📊 Xem bảng dữ liệu tổng hợp chi tiết", expanded=False):
            summary_df = pd.DataFrame(summary_data)
            def highlight_rec(val):
                if val == 'MUA': return 'background-color: rgba(16, 185, 129, 0.2); color: #34D399; font-weight: bold'
                if val == 'BÁN': return 'background-color: rgba(244, 63, 94, 0.2); color: #FB7185; font-weight: bold'
                return 'background-color: rgba(245, 158, 11, 0.2); color: #FBBF24; font-weight: bold'
                
            styled_df = summary_df.style.map(highlight_rec, subset=['Khuyến nghị'])
            st.dataframe(
                styled_df, 
                use_container_width=True,
                column_config={
                    "Action (TCInvest Order)": st.column_config.TextColumn(
                        "Action (TCInvest Order)",
                        help="Copy & paste cú pháp này vào ứng dụng TCBS",
                        width="large"
                    )
                }
            )
            
        st.markdown("---")
        st.markdown("### 🔍 Phân Tích Chuyên Sâu Từng Mã Cổ Phiếu")
        
        for ticker, data in detailed_results.items():
            rec_val = data['master'].get('recommendation', 'N/A').upper()
            with st.expander(f"📊 Báo cáo {ticker} — Khuyến nghị: {rec_val}", expanded=True):
                ai_results = data['ai_results']
                df_stock = data['df']
                master = data['master']
                fa_dict = data.get('fa_data', {})
                current_price = data.get('current_price', 0.0)
                
                # Layout 2 Cột Chuyên Nghiệp: Trái (Chart + FA) | Phải (Master Decision + 3 Agent Reports)
                col_left, col_right = st.columns([1.75, 1.25])
                
                with col_left:
                    # Tùy chọn chỉ báo cho Subplot
                    sub_c1, sub_c2 = st.columns([2.2, 1])
                    with sub_c1:
                        st.markdown(f"📈 **Biểu đồ Kỹ thuật {ticker}** (OHLCV, Bollinger Bands, EMA)")
                    with sub_c2:
                        subchart_type = st.radio(
                            "Chỉ báo phụ:",
                            ["MACD", "RSI"],
                            horizontal=True,
                            label_visibility="collapsed",
                            key=f"subchart_{ticker}"
                        )
                    
                    render_advanced_chart(df_stock, ticker, subchart_type=subchart_type)
                    
                    # Thẻ thông số cơ bản (FA Ratios) thiết kế Fintech chuyên nghiệp
                    render_financial_metrics_bar(fa_dict)
                                
                with col_right:
                    # Quyết định Master Agent
                    render_master_decision_card(
                        master=master,
                        ticker=ticker,
                        current_price=current_price,
                        models_used=ai_results.get("models_used", {})
                    )
                    
                    st.markdown("##### 🧠 Báo Cáo Chuyên Viên AI:")
                    render_agent_reports(ai_results)


# ==============================================================================
# TAB 2: THAM VẤN GEMINI 4 ARGON (EDGE CDP BRIDGE)
# ==============================================================================

with tab_argon:
    st.markdown("### ⚡ Tham Vấn Chiến Lược Chuyên Sâu Cùng Gemini AI")
    st.caption("Thẩm định hành vi nến nội phiên, Close Location Value (CLV), bẫy Bull-trap và chiến lược trước giờ ATC.")
    
    # Bộ chọn chế độ AI (Local Edge CDP vs Cloud Mode API)
    col_mode_sel, col_mode_cfg = st.columns([2.0, 1.0])
    with col_mode_sel:
        ai_mode = st.radio(
            "Phương thức kết nối AI:",
            ["🖥️ Edge CDP Bridge (Miễn phí qua Web Gemini 4 Argon)", "☁️ Cloud Mode (Chạy qua Gemini API Key)"],
            horizontal=True,
            help="Edge CDP Bridge kết nối tab Edge trên máy cá nhân. Cloud Mode gọi trực tiếp API của Google phù hợp khi dùng trên Streamlit Cloud."
        )

    # Nếu dùng Edge CDP, cho phép cấu hình URL (mặc định 127.0.0.1:9222 hoặc Tunnel)
    custom_endpoint = "http://127.0.0.1:9222"
    if "Edge CDP Bridge" in ai_mode:
        with st.expander("⚙️ Cấu hình địa chỉ Bridge (Nếu dùng Tunnel từ xa)", expanded=False):
            custom_endpoint = st.text_input(
                "CDP Endpoint URL:",
                value="http://127.0.0.1:9222",
                help="Nếu dùng trên máy: giữ nguyên http://127.0.0.1:9222. Nếu dùng trên Streamlit Cloud: nhập URL Ngrok hoặc Cloudflare Tunnel."
            ).strip()

        cdp_status = is_edge_cdp_available(base_url=custom_endpoint)
        col_stat1, col_stat2 = st.columns([2.2, 0.8])
        with col_stat1:
            if cdp_status.get("available") and cdp_status.get("tab_found"):
                st.markdown("""
                <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid #10B981; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;">
                    <span style="color: #34D399; font-weight: 700; font-size: 15px;">🟢 ĐÃ KẾT NỐI GEMINI 4 ARGON PRO (EDGE CDP PORT 9222)</span>
                    <div style="color: #CBD5E1; font-size: 13px; margin-top: 4px;">Sẵn sàng thẩm định hành vi nến, bẫy bull-trap nội phiên, dòng tiền khối ngoại và tư vấn chiến lược phiên ATC.</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                err = cdp_status.get("error", "Chưa bật cổng 9222 hoặc thiếu tab gemini.google.com")
                st.markdown(f"""
                <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid #F59E0B; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;">
                    <span style="color: #FBBF24; font-weight: 700; font-size: 15px;">⚠️ CHƯA KẾT NỐI ĐƯỢC VỚI TRÌNH DUYỆT EDGE TRÊN MÁY TÍNH CỦA BẠN</span>
                    <div style="color: #CBD5E1; font-size: 13px; margin-top: 6px;">
                        • <strong>Lý do:</strong> Nếu bạn đang mở link <code>*.streamlit.app</code> (Streamlit Cloud), máy chủ đám mây không thể tự động kết nối cổng 127.0.0.1 trên máy tính của bạn.<br>
                        • <strong>Cách 1 (Khuyên dùng):</strong> Chạy ứng dụng cục bộ trên máy tính của bạn bằng lệnh <code>streamlit run app.py</code> (truy cập <code>http://localhost:8501</code>).<br>
                        • <strong>Cách 2 (Tiện lợi nhất trên Cloud):</strong> Chuyển sang nút <strong>☁️ Cloud Mode</strong> ở trên và nhập API Key ở thanh bên (sidebar) để phân tích ngay.<br>
                        • <strong>Cách 3:</strong> Mở tunnel bằng lệnh <code>ngrok http 9222</code> trên máy và dán URL vào mục cấu hình phía trên.
                    </div>
                </div>
                """, unsafe_allow_html=True)
        with col_stat2:
            if st.button("🔄 Kiểm Tra Lại", key="btn_check_cdp_argon", use_container_width=True):
                st.rerun()
    else:
        # Cloud Mode qua API
        if api_key_input:
            st.markdown("""
            <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid #38BDF8; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;">
                <span style="color: #38BDF8; font-weight: 700; font-size: 15px;">☁️ CHẾ ĐỘ CLOUD MODE (GEMINI API) ĐÃ SẴN SÀNG</span>
                <div style="color: #CBD5E1; font-size: 13px; margin-top: 4px;">Sử dụng Google GenAI API Key cấu hình ở thanh bên (sidebar). Hoạt động hoàn hảo trên mọi thiết bị và máy chủ Cloud.</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid #EF4444; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;">
                <span style="color: #F87171; font-weight: 700; font-size: 15px;">⚠️ CHƯA CUNG CẤP GOOGLE GENAI API KEY</span>
                <div style="color: #CBD5E1; font-size: 13px; margin-top: 4px;">Vui lòng nhập API Key ở thanh bên (sidebar) bên trái để kích hoạt Cloud Mode.</div>
            </div>
            """, unsafe_allow_html=True)

    # Form nhập mã phân tích
    col_arg1, col_arg2, col_arg3 = st.columns([1.2, 1.8, 1.0])
    with col_arg1:
        argon_ticker = st.text_input("Mã cổ phiếu cần tham vấn:", value="FPT", key="argon_ticker_input").upper().strip()
    with col_arg2:
        argon_focus = st.multiselect(
            "Trọng tâm phân tích chuyên sâu:",
            [
                "Hành vi nến nội phiên (CLV & Bẫy Bull-trap)",
                "Dòng tiền Khối ngoại & Tự doanh",
                "Sóng ngành đồng thuận (Sector Synergy)",
                "Khuyến nghị phiên ATC (Mua ATC/Chờ rung lắc)",
                "Cắt lỗ động theo ATR & MA50"
            ],
            default=[
                "Hành vi nến nội phiên (CLV & Bẫy Bull-trap)",
                "Dòng tiền Khối ngoại & Tự doanh",
                "Khuyến nghị phiên ATC (Mua ATC/Chờ rung lắc)"
            ]
        )
    with col_arg3:
        st.write("")
        st.write("")
        ask_argon_btn = st.button("⚡ Phân Tích Ngay", key="btn_ask_argon_main", type="primary", use_container_width=True)

    if ask_argon_btn:
        is_cdp_mode = "Edge CDP Bridge" in ai_mode
        if is_cdp_mode and (not cdp_status.get("available") or not cdp_status.get("tab_found")):
            st.error("⚠️ Không thể kết nối với Edge CDP trên máy tính của bạn. Bạn hãy chuyển sang chế độ '☁️ Cloud Mode' ở trên để phân tích qua API Key!")
        elif not is_cdp_mode and not api_key_input:
            st.error("⚠️ Vui lòng nhập Google GenAI API Key ở thanh bên (sidebar) để chạy Cloud Mode!")
        else:
            with st.spinner(f"Đang trích xuất dữ liệu nến, volume, chỉ báo của {argon_ticker} và phân tích chiến lược ATC..."):
                df_stock = load_historical_data(argon_ticker, months=6)
                if df_stock.empty:
                    st.error(f"Không thể tải dữ liệu nến cho mã {argon_ticker}.")
                else:
                    df_stock = compute_indicators(df_stock)
                    latest = df_stock.iloc[-1]
                    high_val = float(latest.get('high', latest['close']))
                    low_val = float(latest.get('low', latest['close']))
                    close_val = float(latest['close'])
                    clv = (close_val - low_val) / (high_val - low_val) if high_val > low_val else 0.8
                    vol_curr = float(latest.get('volume', 0))
                    vol_ma20 = float(latest.get('vol_sma20', vol_curr)) if 'vol_sma20' in latest else vol_curr
                    vol_ratio = (vol_curr / vol_ma20) if vol_ma20 > 0 else 1.5
                    
                    fa = load_fundamentals(argon_ticker)
                    
                    # VNINDEX
                    df_vni = load_historical_data("VNINDEX", months=6)
                    vni_val = float(df_vni.iloc[-1]['close']) if not df_vni.empty else 1280.0
                    vni_ma50 = float(df_vni['close'].rolling(50).mean().iloc[-1]) if not df_vni.empty else 1260.0
                    vni_status = "UPTREND (TRÊN MA50)" if vni_val > vni_ma50 else "DOWNTREND/SIDEWAY"
                    
                    prompt = (
                        f"=== [PERSONA: SENIOR QUANTITATIVE TRADING STRATEGIST] ===\n"
                        f"Bạn là Giám đốc Chiến lược Giao dịch Định lượng Chứng khoán Việt Nam (am hiểu quy tắc T+2.5 và phiên ATC).\n\n"
                        f"### DỮ LIỆU CỔ PHIẾU {argon_ticker} TẠI THỜI ĐIỂM CẬN PHIÊN ATC:\n"
                        f"- Thị trường chung VN-INDEX: {vni_val:,.1f} | MA50: {vni_ma50:,.1f} ({vni_status})\n"
                        f"- Giá đóng cửa hiện tại: {close_val:,.0f} ₫ (Biên độ nến: High {high_val:,.0f} - Low {low_val:,.0f})\n"
                        f"- Close Location Value (CLV): {clv:.2f} (Tỷ lệ đóng nến trong biên độ ngày: CLV>0.7 là lực mua áp đảo, CLV<0.4 là nến bị bán dội ngược)\n"
                        f"- Volume nến hiện tại so với MA20 Volume: {vol_ratio:.1f}x\n"
                        f"- RSI(14): {float(latest.get('rsi', 50)):.1f} | MACD Hist: {float(latest.get('macd_hist', 0)):.2f}\n"
                        f"- Chỉ số cơ bản: P/E={fa.get('PE', 'N/A')} | ROE={fa.get('ROE', 0)*100 if isinstance(fa.get('ROE'), (int, float)) else 'N/A'}%\n"
                        f"- Các khía cạnh trọng tâm: {', '.join(argon_focus)}\n\n"
                        f"### YÊU CẦU THỰC HIỆN:\n"
                        f"1. Phân tích giải phẫu cây nến hôm nay: Có hiện tượng rút chân thật hay bẫy Bull-trap xả hàng cận ATC?\n"
                        f"2. Đánh giá xác suất thành công hàng về T+2.5.\n"
                        f"3. ĐƯA RA QUYẾT ĐỊNH DỨT KHOÁT: MUA ATC / ĐẶT LỆNH LO CHỜ RUNG LẮC / BỎ QUA.\n"
                        f"4. Thiết lập Kế hoạch giao dịch chi tiết: Tỷ trọng giải ngân (% NAV), Vùng giá giải ngân, Ngưỡng Cắt Lỗ Động và Mục Tiêu Chốt Lời.\n\n"
                        f"Hãy trình bày trực diện, chuyên nghiệp, có cấu trúc bullet point rõ ràng."
                    )
                    
                    if is_cdp_mode:
                        success, verdict = ask_gemini_4_argon_sync(prompt, timeout_sec=65, base_url=custom_endpoint)
                    else:
                        success, verdict = ask_gemini_via_api(prompt, api_key=api_key_input)
                        
                    if success:
                        st.session_state.last_argon_verdict = verdict
                        st.session_state.last_argon_ticker = argon_ticker
                        st.session_state.last_argon_mode = ai_mode
                    else:
                        st.error(f"❌ Không thể nhận phản hồi từ AI: {verdict}")

    if "last_argon_verdict" in st.session_state and st.session_state.last_argon_verdict:
        st.markdown("---")
        mode_label = st.session_state.get('last_argon_mode', ai_mode)
        st.markdown(f"#### 🧠 Bản Đánh Giá Chiến Lược Chuyên Sâu: **{st.session_state.last_argon_ticker}** ({mode_label})")
        st.markdown(f"""
        <div class="fintech-card" style="border-left: 4px solid #38BDF8; line-height: 1.8;">
        {st.session_state.last_argon_verdict}
        </div>
        """, unsafe_allow_html=True)


# ==============================================================================
# TAB 3: KIỂM ĐỊNH CHIẾN LƯỢC QUANT (BACKTEST)
# ==============================================================================

with tab_backtest:
    st.markdown("### 📊 Kiểm Định Chiến Lược Lịch Sử (Quantitative Backtest)")
    st.caption("Khớp lệnh tại giá Open nến T+1 sau tín hiệu ngày T (Zero Lookahead Bias) | Khấu trừ thuế bán 0.1% và phí môi giới 0.3% trọn vòng")
    
    col_bt1, col_bt2, col_bt3, col_bt4 = st.columns([1.2, 1.4, 1.4, 1.0])
    
    with col_bt1:
        bt_ticker = st.text_input("Mã kiểm định:", value="FPT", key="bt_ticker_input").upper()
        
    with col_bt2:
        preset_options = {
            "3 Năm (36T - Chu kỳ đầy đủ)": 36,
            "1 Năm (12T - Ngắn hạn)": 12,
            "2 Năm (24T - Trung hạn)": 24,
            "5 Năm (60T - Lịch sử dài)": 60
        }
        selected_preset = st.selectbox("Preset chu kỳ kiểm định:", list(preset_options.keys()), index=0)
        chosen_months = preset_options[selected_preset]
        
    with col_bt3:
        bt_strategy = st.selectbox(
            "Chiến lược giao dịch:", 
            ["trend", "momentum", "mean_reversion"], 
            format_func=lambda x: {
                "trend": "📈 Trend Following (Xu hướng EMA/MACD)",
                "momentum": "🚀 Momentum Breakout (Bùng nổ BB/Vol)",
                "mean_reversion": "🔄 Mean Reversion (Bắt đáy RSI/BB)"
            }[x]
        )
        
    with col_bt4:
        st.write("")
        st.write("")
        bt_btn = st.button("▶️ Chạy Kiểm Định", type="primary", use_container_width=True)

    if bt_btn:
        with st.spinner(f"Đang trích xuất dữ liệu và mô phỏng giao dịch {bt_ticker} ({chosen_months} tháng)..."):
            df_bt = load_historical_data(bt_ticker, months=chosen_months)
            if df_bt.empty:
                st.error(f"Không thể tải dữ liệu nến lịch sử cho mã {bt_ticker}.")
            else:
                df_bt = compute_indicators(df_bt)
                df_bt = generate_signals(df_bt, strategy_type=bt_strategy)
                bt_results = run_backtest(df_bt, initial_capital=100_000_000)
                
                # Lưu vào session state
                st.session_state.last_bt_results = bt_results
                st.session_state.last_bt_df = df_bt
                st.session_state.last_bt_ticker = bt_ticker

    if "last_bt_results" in st.session_state:
        bt_results = st.session_state.last_bt_results
        df_bt = st.session_state.last_bt_df
        t_name = st.session_state.last_bt_ticker
        
        st.markdown("---")
        # 1. 6 KPI Cards
        render_kpi_dashboard(bt_results)
        
        st.markdown("---")
        # 2. Biểu đồ Tăng trưởng Vốn (Equity Curve)
        eq_df = bt_results.get('equity_curve', pd.DataFrame())
        if not eq_df.empty:
            render_equity_comparison_chart(eq_df)
            
        # 3. Thống kê theo năm & Danh sách lệnh giao dịch
        col_y, col_tr = st.columns([1.1, 1.9])
        
        with col_y:
            st.markdown("##### 📅 Hiệu Suất Từng Năm (Yearly Breakdown)")
            yearly_data = bt_results.get('yearly_breakdown', [])
            if yearly_data:
                yearly_df = pd.DataFrame(yearly_data)
                st.dataframe(yearly_df, use_container_width=True)
            else:
                st.info("Chưa có thống kê theo năm.")
                
        with col_tr:
            st.markdown("##### 📑 Lịch Sử Khớp Lệnh Chi Tiết")
            trades = bt_results.get('trades', [])
            if trades:
                trades_df = pd.DataFrame(trades)
                st.dataframe(trades_df, use_container_width=True)
            else:
                st.info("Không phát sinh lệnh giao dịch nào trong khoảng thời gian đã chọn.")


# ==============================================================================
# TAB 4: QUẢN LÝ & CẤU HÌNH ALERT BOT (DUAL-STAGE QUANT + AI)
# ==============================================================================

with tab_alert:
    st.markdown("### 🔔 Quản Lý & Giám Sát Dual-Stage Alert Bot")
    st.caption("Cơ chế cảnh báo 2 pha trước phiên ATC: Pha 1 (14:26 - Quant Signals) và Pha 2 (14:28 - Thẩm định chiến lược bởi Gemini 4 Argon Pro).")
    
    col_bot1, col_bot2 = st.columns([1.5, 1.5])
    
    with col_bot1:
        st.markdown("""
        <div class="fintech-card">
            <h4 style="margin-top:0; color:#38BDF8;">🤖 Lịch Trình Tự Động Hóa Vận Hành</h4>
            <div style="font-size:13px; line-height:1.8; color:#CBD5E1;">
                <div>• <strong>14:15:</strong> Pre-flight Heartbeat kiểm tra kết nối Edge CDP (Port 9222).</div>
                <div>• <strong>14:25:</strong> Quant Engine lọc toàn bộ 30 mã VN30 (Trend + MTF + FA).</div>
                <div>• <strong>14:26 (Pha 1):</strong> Bắn danh sách mã thô sang Telegram để NĐT chuẩn bị app.</div>
                <div>• <strong>14:28 (Pha 2):</strong> Gemini 4 Argon trả về nhận định ATC, tỷ trọng & cắt lỗ động.</div>
                <div>• <strong>14:30 - 14:45:</strong> Phiên ATC diễn ra, NĐT vào lệnh tự tin với đầy đủ góc nhìn AI.</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    with col_bot2:
        st.markdown("""
        <div class="fintech-card">
            <h4 style="margin-top:0; color:#10B981;">🚀 Kiểm Tra & Kích Hoạt Thủ Công</h4>
            <p style="font-size:13px; color:#94A3B8;">Chạy kiểm tra kết nối Heartbeat hoặc quét toàn bộ quy trình Dual-Stage ngay lập tức.</p>
        </div>
        """, unsafe_allow_html=True)
        
        col_btn_hb, col_btn_scan = st.columns(2)
        with col_btn_hb:
            btn_heartbeat = st.button("💓 Test Heartbeat 14:15", use_container_width=True)
        with col_btn_scan:
            enable_ai_check = st.checkbox("Bật Pha 2 (Gemini 4)", value=True)
            run_scan_btn = st.button("▶️ Quét Dual-Stage Ngay", type="primary", use_container_width=True)

    if btn_heartbeat:
        with st.spinner("Đang kiểm tra kết nối Heartbeat tới Edge CDP..."):
            status = is_edge_cdp_available()
            if status.get("available") and status.get("tab_found"):
                st.success("✅ [HEARTBEAT OK] Edge CDP Port 9222 sẵn sàng và tìm thấy tab Gemini (Argon)!")
            else:
                st.error(f"❌ [HEARTBEAT FAILED] {status.get('error', 'Chưa mở Edge hoặc thiếu tab Gemini')}")

    # Khi người dùng nhấn nút quét thủ công
    if run_scan_btn:
        with st.spinner("Đang thực thi quy trình quét Dual-Stage (Pha 1 Quant + Pha 2 Gemini 4 Argon)..."):
            try:
                market_status, buy_signals, msg_p1, ai_verdict = run_quant_scan(enable_ai_verdict=enable_ai_check)
                
                st.markdown("---")
                st.markdown("#### 📊 Kết Quả Quét Dual-Stage Trực Tiếp:")
                st.info(f"**Trạng thái VN-INDEX:** {market_status}")
                
                if buy_signals:
                    st.success(f"🎉 Pha 1 phát hiện **{len(buy_signals)}** mã đạt tiêu chuẩn MUA:")
                    b_cols = st.columns(min(len(buy_signals), 3))
                    for b_idx, s in enumerate(buy_signals):
                        with b_cols[b_idx % min(len(buy_signals), 3)]:
                            st.markdown(f"""
                            <div class="watchlist-card" style="border-color:#10B981;">
                                <div style="font-size:18px; font-weight:800; color:#34D399;">🚀 {s['ticker']}</div>
                                <div style="font-size:14px; margin-top:4px;">Giá: <strong>{s['price']:,.0f} ₫</strong></div>
                                <div style="font-size:12px; color:#94A3B8; margin-top:4px;">
                                    CLV: <strong>{s['clv']:.2f}</strong> | Vol: <strong>{s['vol_ratio']:.1f}x</strong>
                                </div>
                                <div style="font-size:12px; color:#94A3B8; margin-top:2px;">
                                    Điểm: <strong>{s['score']}/100</strong> | P/E: {s['pe']:.1f} | ROE: {s['roe']*100:.1f}%
                                </div>
                                <div style="font-size:12px; color:#E2E8F0; margin-top:6px; background:#0F141C; padding:6px; border-radius:4px;">
                                    {s['reason']}
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                    if ai_verdict:
                        st.markdown("---")
                        st.markdown("#### 🧠 Pha 2: Thẩm Định Chiến Lược ATC Từ Gemini 4 Argon Pro:")
                        st.markdown(f"""
                        <div class="fintech-card" style="border-left: 4px solid #38BDF8; line-height: 1.8;">
                        {ai_verdict}
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.warning("Không có mã VN30 nào đạt tiêu chuẩn MUA trong phiên hôm nay.")
            except Exception as e:
                st.error(f"Lỗi khi thực thi quét: {e}")

    # Xem danh sách mã VN30 được theo dõi
    with st.expander("📋 Danh mục 30 mã cổ phiếu trong rổ VN30 đang được giám sát", expanded=False):
        vn30_cols = st.columns(6)
        for idx, sym in enumerate(VN30):
            vn30_cols[idx % 6].markdown(f"`{sym}`")

    # Xem nhật ký hoạt động gần nhất (Log Viewer)
    st.markdown("---")
    st.markdown("#### 📜 Nhật Ký Hoạt Động (Logs Viewer)")
    
    log_file_path = "logs/quant_alert.log"
    if os.path.exists(log_file_path):
        try:
            with open(log_file_path, "r", encoding="utf-8") as f:
                log_lines = f.readlines()
                last_logs = "".join(log_lines[-30:]) if log_lines else "Nhật ký hiện đang rỗng."
            st.code(last_logs, language="log")
        except Exception as e:
            st.warning(f"Không thể đọc file log: {e}")
    else:
        st.info("Chưa có file nhật ký `logs/quant_alert.log`. Nhật ký sẽ xuất hiện sau lần quét đầu tiên.")
