import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import asyncio
import json
import os
from dotenv import load_dotenv

# Load .env before other imports
load_dotenv()

st.set_page_config(page_title="VN Stock AI & Quant Assistant", layout="wide")

from data_loader import load_historical_data
from data_fetcher import get_fundamental_data, get_macro_flow, get_latest_news
from strategy import compute_indicators, generate_signals
from ai_agents import analyze_stock_async, configure_gemini, QuotaExceededError
from notifier import send_telegram_alert
from backtester import run_backtest

async def process_single_ticker(ticker: str, risk_profile: str, months: int, enable_telegram: bool, sem: asyncio.Semaphore, status_container):
    async with sem:
        status_container.write(f"▶️ Đang tải dữ liệu và phân tích {ticker}...")
        df = load_historical_data(ticker, months=months)
        if df.empty:
            status_container.warning(f"Không thể tải dữ liệu cho mã {ticker}. Bỏ qua.")
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
            status_container.error(f"⚠️ Hết tài nguyên (Quota Exceeded) khi phân tích {ticker}: {qe}")
            raise qe
        except Exception as e:
            status_container.error(f"Lỗi khi chạy AI cho {ticker}: {e}")
            return None, None
            
        master = ai_results.get("master_decision", {})
        rec = master.get("recommendation", "N/A").upper()
        order_action = master.get("order_action", rec).upper()
        
        try:
            alloc_pct = int(master.get("allocation_pct", 0))
            if alloc_pct > 100: alloc_pct = 100
            elif alloc_pct < 0: alloc_pct = 0
        except Exception:
            alloc_pct = 0

        try:
            vol_pct = int(master.get("volume_percent", alloc_pct))
            if vol_pct > 100: vol_pct = 100
            elif vol_pct < 0: vol_pct = 0
        except Exception:
            vol_pct = alloc_pct

        try:
            target_price = float(master.get("target_price", current_price))
        except Exception:
            target_price = current_price

        try:
            sl_price = float(master.get("stop_loss", 0))
        except Exception:
            sl_price = 0.0

        try:
            tp_price = float(master.get("take_profit", 0))
        except Exception:
            tp_price = 0.0
        
        tcinvest_action = f"{ticker} - {order_action} - Tỷ trọng: {vol_pct}% - Giá: {target_price:,.0f}"
        
        summary_item = {
            "Mã CP": ticker,
            "Khuyến nghị": rec,
            "Action (TCInvest Order)": tcinvest_action,
            "Tỷ trọng (%)": alloc_pct,
            "Cắt lỗ (SL)": f"{sl_price:,.0f}" if sl_price > 0 else "-",
            "Chốt lời (TP)": f"{tp_price:,.0f}" if tp_price > 0 else "-"
        }
        
        detail_item = {
            "ai_results": ai_results,
            "df": df,
            "master": master
        }
        
        # Gửi thông báo Telegram nếu bật
        if enable_telegram and rec == "MUA":
            send_telegram_alert(ticker, rec, master.get("reasoning", ""))
            
        return summary_item, detail_item

async def process_entire_watchlist(tickers, risk_profile, months, enable_telegram, status_container):
    summary_data = []
    detailed_results = {}
    
    # Sử dụng Semaphore(3) để xử lý đồng thời tối đa 3 mã
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
        
    return summary_data, detailed_results

# ----------------- UI Header & Cấu hình -----------------
st.title("⚡ VN Stock AI & Quant Assistant")
st.caption("Hệ thống Phân tích Định lượng Quant & Trợ lý Đa tác tử AI cho Thị trường Chứng khoán Việt Nam")

# Tự động đọc API Key từ file .env
default_api_key = os.getenv("GEMINI_API_KEY", "")
api_key_input = st.text_input(
    "🔑 Google GenAI API Key:",
    value=default_api_key,
    type="password",
    placeholder="Nhập Gemini API Key (tự động đọc từ .env nếu có)..."
)
if api_key_input:
    api_key_input = api_key_input.strip()

# Sidebar
st.sidebar.header("⚙️ Cài đặt Cá nhân hóa")
risk_profile = st.sidebar.selectbox(
    "Khẩu vị rủi ro:",
    ["Thận trọng", "Cân bằng", "Mạo hiểm"],
    index=1
)
enable_telegram = st.sidebar.checkbox("Bật cảnh báo Telegram")
if enable_telegram:
    st.sidebar.info("Cấu hình TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID trong file .env để nhận thông báo.")

st.sidebar.markdown("---")
st.sidebar.markdown("⚡ **Hệ Thống Cascade Đa Tầng (Tối Ưu Quota)**")
st.sidebar.caption("🤖 **3 Sub-Agents:** `3.5-flash-lite` (15 RPM, 500 RPD) ➔ `3.1-flash-lite` (15 RPM, 500 RPD) ➔ `2.5-flash-lite` (10 RPM)")
st.sidebar.caption("🎯 **Master CIO:** `3.8-flash` (5 RPM, 20 RPD) ➔ `3.7` ➔ `3.6` ➔ `3.5` ➔ `3.0` ➔ `2.5` ➔ `3.5-Lite` (500 RPD)")


# Tabs phân chia tính năng chính
tab_ai, tab_backtest = st.tabs(["🚀 Phân tích Đa tác tử AI (Multi-Agent)", "📈 Kiểm định Chiến lược Quant (Backtest)"])

# ==================== TAB 1: PHÂN TÍCH AI ====================
with tab_ai:
    col_input1, col_input2, col_input3 = st.columns([1.5, 1, 1.5])
    with col_input1:
        tickers_input = st.text_input("Nhập mã cổ phiếu (cách nhau bởi dấu phẩy):", value="FPT, HPG").upper()
    with col_input2:
        months = st.slider(
            "Dữ liệu (tháng):", 
            min_value=6, 
            max_value=24, 
            value=12, 
            step=3,
            help="Tối thiểu 6 tháng (khuyến nghị 12 tháng) để đảm bảo đường MA dài hạn (SMA200) và Ichimoku tính toán chuẩn xác."
        )
    with col_input3:
        st.write("")
        st.write("")
        analyze_btn = st.button("🚀 Quét Phân Tích Đồng Thời", type="primary", use_container_width=True)

    st.caption("⚡ Hệ thống tự động điều phối đồng thời (Concurrent Batch) kết hợp Rate Limiter thông minh.")

    if analyze_btn:
        if not api_key_input:
            st.error("⚠️ Bạn cần cung cấp API Key để chạy AI Agents!")
            st.stop()
            
        configure_gemini(api_key_input)
        
        tickers = [t.strip() for t in tickers_input.split(',') if t.strip()]
        if not tickers:
            st.error("⚠️ Vui lòng nhập ít nhất 1 mã cổ phiếu hợp lệ.")
            st.stop()

        status = st.status(f"🔍 Đang phân tích Watchlist {len(tickers)} mã (tối đa 3 mã đồng thời)...", expanded=True)
        summary_data, detailed_results = asyncio.run(
            process_entire_watchlist(tickers, risk_profile, months, enable_telegram, status)
        )
        status.update(label="✅ Đã hoàn tất phân tích Watchlist!", state="complete", expanded=False)
            
        st.markdown("---")
        st.subheader("📋 Bảng Tổng hợp Watchlist")
        if summary_data:
            summary_df = pd.DataFrame(summary_data)
            def style_rec(val):
                if val == 'MUA': return 'background-color: #d4edda; color: #155724; font-weight: bold'
                if val == 'BÁN': return 'background-color: #f8d7da; color: #721c24; font-weight: bold'
                return 'background-color: #e2e3e5; color: #383d41; font-weight: bold'
                
            styled_df = summary_df.style.map(style_rec, subset=['Khuyến nghị'])
            
            st.dataframe(
                styled_df, 
                use_container_width=True,
                column_config={
                    "Action (TCInvest Order)": st.column_config.TextColumn(
                        "Action (TCInvest Order)",
                        help="Copy & paste cú pháp này trực tiếp vào ứng dụng TCInvest (TCBS)",
                        width="large"
                    )
                }
            )
        else:
            st.warning("Không có dữ liệu phân tích nào thành công.")
            
        st.markdown("---")
        st.subheader("🔍 Phân tích Chi tiết Từng mã")
        
        for ticker, data in detailed_results.items():
            with st.expander(f"Phân tích {ticker} - {data['master'].get('recommendation', 'N/A').upper()}", expanded=True):
                ai_results = data['ai_results']
                df = data['df']
                master = data['master']
                
                col_z1, col_z2, col_z3 = st.columns([2.2, 1.3, 1.3])
                
                with col_z1:
                    st.markdown("**📊 Biểu đồ Nến & Bollinger Bands / MA**")
                    fig = make_subplots(
                        rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03, row_heights=[0.7, 0.3]
                    )
                    # Nến giá
                    fig.add_trace(go.Candlestick(
                        x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Price"
                    ), row=1, col=1)
                    
                    # Bollinger Bands
                    if 'bb_high' in df.columns and 'bb_low' in df.columns:
                        fig.add_trace(go.Scatter(
                            x=df['time'], y=df['bb_high'], line=dict(color='rgba(150, 150, 150, 0.4)', width=1, dash='dash'), name="BB Upper"
                        ), row=1, col=1)
                        fig.add_trace(go.Scatter(
                            x=df['time'], y=df['bb_low'], line=dict(color='rgba(150, 150, 150, 0.4)', width=1, dash='dash'),
                            fill='tonexty', fillcolor='rgba(200, 200, 200, 0.08)', name="BB Lower"
                        ), row=1, col=1)
                        
                    # EMA 20 & EMA 50
                    if 'ema20' in df.columns:
                        fig.add_trace(go.Scatter(
                            x=df['time'], y=df['ema20'], line=dict(color='#2962FF', width=1.5), name="EMA 20"
                        ), row=1, col=1)
                    if 'ema50' in df.columns:
                        fig.add_trace(go.Scatter(
                            x=df['time'], y=df['ema50'], line=dict(color='#FF6D00', width=1.5), name="EMA 50"
                        ), row=1, col=1)
                        
                    # Volume & Vol SMA20
                    fig.add_trace(go.Bar(
                        x=df['time'], y=df['volume'], marker_color='rgba(0, 150, 255, 0.5)', name="Volume"
                    ), row=2, col=1)
                    if 'vol_sma20' in df.columns:
                        fig.add_trace(go.Scatter(
                            x=df['time'], y=df['vol_sma20'], line=dict(color='orange', width=1), name="Vol SMA20"
                        ), row=2, col=1)
                    
                    fig.update_layout(
                        height=420, xaxis_rangeslider_visible=False, 
                        margin=dict(l=0, r=0, t=10, b=0),
                        template='plotly_white'
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                with col_z2:
                    st.markdown("**🧠 Báo cáo Chuyên viên AI**")
                    st.info(f"**📈 Technical Analyst:**\n\n{ai_results.get('tech_analysis', 'Lỗi')}")
                    st.info(f"**🏢 Fundamental Analyst:**\n\n{ai_results.get('fa_analysis', 'Lỗi')}")
                    st.info(f"**🌐 Macro & Flow Analyst:**\n\n{ai_results.get('macro_analysis', 'Lỗi')}")
                    
                with col_z3:
                    st.markdown("**🎯 Quyết định Master Agent**")
                    rec_color = "#28a745" if master.get('recommendation', 'N/A').upper() == "MUA" else "#dc3545" if master.get('recommendation', 'N/A').upper() == "BÁN" else "#6c757d"
                    st.markdown(f"<h3 style='text-align: center; color: {rec_color}; border: 2px solid {rec_color}; padding: 8px; border-radius: 6px;'>{master.get('recommendation', 'N/A').upper()}</h3>", unsafe_allow_html=True)
                    
                    c1, c2 = st.columns(2)
                    c1.metric("Tỷ trọng", f"{master.get('allocation_pct', 0)}%")
                    c2.metric("Tâm lý TT", master.get('market_sentiment', 'N/A'))
                    
                    c3, c4 = st.columns(2)
                    c3.metric("Cắt lỗ (SL)", f"{master.get('stop_loss', 0):,.0f} ₫")
                    c4.metric("Chốt lời (TP)", f"{master.get('take_profit', 0):,.0f} ₫")
                    
                    st.markdown("**Lý do đầu tư:**")
                    st.write(master.get("reasoning", ""))
                    
                    models_used = ai_results.get("models_used", {})
                    if models_used:
                        st.caption(f"⚙️ Phục vụ bởi: Master (`{models_used.get('master', 'N/A')}`) | Sub (`{models_used.get('tech', 'N/A')}`)")


# ==================== TAB 2: KIỂM ĐỊNH CHIẾN LƯỢC QUANT (BACKTEST) ====================
with tab_backtest:
    st.subheader("📊 Kiểm định Lịch sử Không Lookahead Bias")
    st.caption("Khớp lệnh tại giá Open ngày T+1 sau tín hiệu ngày T | Khấu trừ thuế bán 0.1% và phí môi giới 0.3% tổng vòng")
    
    col_bt1, col_bt2, col_bt3, col_bt4 = st.columns([1, 1.4, 1.1, 1])
    with col_bt1:
        bt_ticker = st.text_input("Mã kiểm định:", value="FPT").upper()
    with col_bt2:
        preset_options = {
            "3 Năm (36T - Chu kỳ đầy đủ)": 36,
            "1 Năm (12T - Ngắn hạn)": 12,
            "2 Năm (24T - Trung hạn)": 24,
            "5 Năm (60T - Lịch sử dài)": 60
        }
        selected_preset = st.selectbox("Preset chu kỳ nhanh:", list(preset_options.keys()), index=0)
        chosen_default = preset_options[selected_preset]
        bt_months = st.slider(
            "Khoảng thời gian (tháng):", 
            min_value=12, 
            max_value=60, 
            value=chosen_default, 
            step=6,
            help="Khuyến nghị 36-60 tháng (3-5 năm) để bao quát trọn vẹn chu kỳ thị trường (Bull/Bear/Sideway) và đảm bảo ý nghĩa thống kê."
        )
    with col_bt3:
        bt_strategy = st.selectbox("Chiến lược Quant:", ["trend", "momentum", "mean_reversion"], format_func=lambda x: {
            "trend": "Trend Following (Xu hướng)",
            "momentum": "Momentum Breakout (Xung lực)",
            "mean_reversion": "Mean Reversion (Bắt đáy RSI/BB)"
        }[x])
    with col_bt4:
        st.write("")
        st.write("")
        bt_btn = st.button("▶️ Chạy Backtest", type="primary", use_container_width=True)

    if bt_btn:
        with st.spinner(f"Đang chạy kiểm định {bt_ticker} ({bt_months} tháng)..."):
            df_bt = load_historical_data(bt_ticker, months=bt_months)
            if df_bt.empty:
                st.error(f"Không thể tải dữ liệu giá cho {bt_ticker}.")
            else:
                df_bt = compute_indicators(df_bt)
                df_bt = generate_signals(df_bt, strategy_type=bt_strategy)
                bt_results = run_backtest(df_bt, initial_capital=100_000_000)
                
                # Hiển thị metrics tổng quan (6 metrics)
                m1, m2, m3, m4, m5, m6 = st.columns(6)
                m1.metric("Lợi nhuận Chiến lược", f"{bt_results['total_return_pct']:+.2f}%")
                m2.metric("Lợi nhuận Buy & Hold", f"{bt_results['benchmark_return_pct']:+.2f}%")
                m3.metric("Tỷ lệ thắng (Win Rate)", f"{bt_results['win_rate_pct']:.1f}%")
                m4.metric("Profit Factor", f"{bt_results['profit_factor']:.2f}")
                m5.metric("Max Drawdown", f"{bt_results['max_drawdown_pct']:.2f}%")
                m6.metric("Sharpe Ratio", f"{bt_results.get('sharpe_ratio', 0.0):.2f}")
                
                # Biểu đồ Đường cong Vốn (Equity Curve)
                eq_df = bt_results['equity_curve']
                if not eq_df.empty:
                    st.markdown("##### 📈 Đường cong Vốn (Equity Curve)")
                    fig_eq = go.Figure()
                    fig_eq.add_trace(go.Scatter(
                        x=eq_df['time'], y=eq_df['equity'], mode='lines',
                        name="Vốn Chiến Lược (VND)", line=dict(color='#00C853', width=2)
                    ))
                    fig_eq.update_layout(height=350, template='plotly_white', margin=dict(l=0, r=0, t=10, b=0))
                    st.plotly_chart(fig_eq, use_container_width=True)
                
                # Thống kê hiệu suất theo năm (Yearly Breakdown)
                yearly_data = bt_results.get('yearly_breakdown', [])
                if yearly_data:
                    st.markdown("##### 📅 Hiệu Suất Theo Từng Năm (Yearly Breakdown)")
                    yearly_df = pd.DataFrame(yearly_data)
                    st.dataframe(yearly_df, use_container_width=True)
                    
                # Bảng chi tiết các lệnh giao dịch
                trades = bt_results['trades']
                if trades:
                    st.markdown("##### 📑 Lịch sử Lệnh Khớp Thực Tế")
                    trades_df = pd.DataFrame(trades)
                    st.dataframe(trades_df, use_container_width=True)
                else:
                    st.info("Không phát sinh lệnh giao dịch nào trong khoảng thời gian đã chọn.")
