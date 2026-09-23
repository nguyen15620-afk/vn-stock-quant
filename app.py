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
    render_equity_comparison_chart
)
from data_loader import load_historical_data, VN30
from data_fetcher import get_fundamental_data, get_macro_flow, get_latest_news
from strategy import compute_indicators, generate_signals
from ai_agents import analyze_stock_async, configure_gemini, QuotaExceededError, CascadeExecutionError
from notifier import send_telegram_alert, send_telegram_message
from backtester import run_backtest
from alert_bot import run_quant_scan

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
    st.caption("• **Sub-Agents (3 Agent con):**\n  `gemini-3.5-flash-lite` (15 RPM, 500 RPD) ➔ `3.1-flash-lite` ➔ `3.6-flash`")
    st.caption("• **Master CIO (Ra Quyết Định):**\n  `gemini-3.6-flash` (5 RPM, 20 RPD) ➔ `3.5-flash` ➔ `3.8` ➔ `3.7` ➔ Fallback `3.5-Lite` (500 RPD)")


# ==============================================================================
# TOP HEADER BAR
# ==============================================================================

render_header(
    api_key_configured=bool(api_key_input),
    master_model="gemini-3.6-flash",
    sub_model="gemini-3.5-flash-lite"
)

# ==============================================================================
# MAIN NAVIGATION TABS (3 TABS)
# ==============================================================================

tab_ai, tab_backtest, tab_alert = st.tabs([
    "🚀 Phân Tích Đa Tác Tử AI (Multi-Agent)",
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
                    sub_c1, sub_c2 = st.columns([2, 1])
                    with sub_c1:
                        st.markdown(f"**Biểu đồ kỹ thuật {ticker}** (OHLCV, Bollinger Bands, EMA)")
                    with sub_c2:
                        subchart_type = st.radio(
                            "Chỉ báo phụ:",
                            ["MACD", "RSI"],
                            horizontal=True,
                            key=f"subchart_{ticker}"
                        )
                    
                    render_advanced_chart(df_stock, ticker, subchart_type=subchart_type)
                    
                    # Thẻ thông số cơ bản (FA Ratios)
                    if isinstance(fa_dict, dict) and any(k in fa_dict for k in ["P/E", "P/B", "ROE", "EPS", "Vốn hóa"]):
                        st.markdown("**🏢 Chỉ số Tài chính & Định giá:**")
                        fa_cols = st.columns(min(len(fa_dict), 4))
                        fa_keys = [k for k in fa_dict.keys() if k not in ["Mã CP", "Nguồn dữ liệu", "Lưu ý phân tích"]][:4]
                        for idx, k in enumerate(fa_keys):
                            with fa_cols[idx]:
                                st.metric(k, str(fa_dict[k]))
                                
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
# TAB 2: KIỂM ĐỊNH CHIẾN LƯỢC QUANT (BACKTEST)
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
# TAB 3: QUẢN LÝ & CẤU HÌNH ALERT BOT
# ==============================================================================

with tab_alert:
    st.markdown("### 🔔 Quản Lý & Giám Sát Quant Alert Bot")
    st.caption("Hệ thống tự động quét bộ lọc Quant cho toàn bộ rổ VN30 trước phiên ATC lúc 14:30 hàng ngày và gửi thông báo qua Telegram.")
    
    col_bot1, col_bot2 = st.columns([1.5, 1.5])
    
    with col_bot1:
        st.markdown("""
        <div class="fintech-card">
            <h4 style="margin-top:0; color:#38BDF8;">🤖 Trạng Thái Hoạt Động Của Bot</h4>
            <div style="font-size:13px; line-height:1.7; color:#CBD5E1;">
                <div>• <strong>Lịch trình:</strong> Tự động quét lúc <strong>14:30</strong> các ngày Thứ 2 đến Thứ 6</div>
                <div>• <strong>Mục tiêu quét:</strong> Rổ 30 cổ phiếu đầu ngành <strong>VN30</strong></div>
                <div>• <strong>Bộ lọc Cơ bản:</strong> P/E &lt; 25 và ROE &gt; 10%</div>
                <div>• <strong>Bộ lọc Kỹ thuật:</strong> Trend Following + Khung Tuần MTF</div>
                <div>• <strong>Bộ lọc Vĩ mô:</strong> Market Regime (VN-INDEX &gt; SMA50)</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    with col_bot2:
        st.markdown("""
        <div class="fintech-card">
            <h4 style="margin-top:0; color:#10B981;">🚀 Kích Hoạt Quét Thủ Công Ngay</h4>
            <p style="font-size:13px; color:#94A3B8;">Chạy quét toàn bộ 30 mã VN30 ngay lập tức và gửi thông báo qua kênh Telegram đã cấu hình.</p>
        </div>
        """, unsafe_allow_html=True)
        
        run_scan_btn = st.button("▶️ Chạy Quét VN30 & Gửi Cảnh Báo Ngay", type="primary", use_container_width=True)

    # Khi người dùng nhấn nút quét thủ công
    if run_scan_btn:
        with st.spinner("Đang quét toàn bộ rổ VN30 và tính toán tín hiệu Quant..."):
            try:
                market_status, buy_signals, telegram_msg = run_quant_scan()
                
                st.markdown("---")
                st.markdown("#### 📊 Kết Quả Quét Trực Tiếp:")
                st.info(f"**Trạng thái VN-INDEX:** {market_status}")
                
                if buy_signals:
                    st.success(f"🎉 Phát hiện **{len(buy_signals)}** mã đạt tiêu chuẩn MUA:")
                    b_cols = st.columns(min(len(buy_signals), 3))
                    for b_idx, s in enumerate(buy_signals):
                        with b_cols[b_idx % min(len(buy_signals), 3)]:
                            st.markdown(f"""
                            <div class="watchlist-card" style="border-color:#10B981;">
                                <div style="font-size:18px; font-weight:800; color:#34D399;">🚀 {s['ticker']}</div>
                                <div style="font-size:14px; margin-top:4px;">Giá: <strong>{s['price']:,.0f} ₫</strong></div>
                                <div style="font-size:12px; color:#94A3B8; margin-top:4px;">
                                    Điểm: <strong>{s['score']}/100</strong> | P/E: {s['pe']:.1f} | ROE: {s['roe']*100:.1f}%
                                </div>
                                <div style="font-size:12px; color:#E2E8F0; margin-top:6px; background:#0F141C; padding:6px; border-radius:4px;">
                                    {s['reason']}
                                </div>
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
