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

st.set_page_config(page_title="VN Stock AI Minimalist", layout="wide")

from data_loader import load_historical_data
from data_fetcher import get_fundamental_data, get_macro_flow, get_latest_news
from strategy import compute_indicators
from ai_agents import analyze_stock_async, configure_gemini, QuotaExceededError
from notifier import send_telegram_alert

async def process_entire_watchlist(tickers, risk_profile, months, enable_telegram, status_container):
    summary_data = []
    detailed_results = {}
    
    for ticker in tickers:
        status_container.write(f"▶️ Bắt đầu phân tích {ticker}...")
        
        df = load_historical_data(ticker, months=months)
        fa_data = get_fundamental_data(ticker)
        market_data_str = get_macro_flow()
        news_data_str = get_latest_news(ticker)
        
        if df.empty:
            status_container.error(f"Không thể tải dữ liệu cho mã {ticker}. Bỏ qua.")
            continue
            
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
            status_container.error(f"⚠️ Hết tài nguyên (Quota Exceeded) khi phân tích {ticker}. Dừng tiến trình.")
            break
        except Exception as e:
            status_container.error(f"Lỗi khi chạy AI cho {ticker}: {e}")
            continue
            
        master = ai_results.get("master_decision", {})
        rec = master.get("recommendation", "N/A").upper()
        
        order_action = master.get("order_action", rec).upper()
        target_price = master.get("target_price", current_price)
        volume_percent = master.get("volume_percent", master.get("allocation_pct", 0))
        
        tcinvest_action = f"{ticker} - {order_action} - Tỷ trọng: {volume_percent}% - Giá: {target_price}"
        
        summary_data.append({
            "Mã CP": ticker,
            "Khuyến nghị": rec,
            "Action (TCInvest Order)": tcinvest_action,
            "Tỷ trọng (%)": master.get("allocation_pct", 0),
            "Cắt lỗ (SL)": master.get("stop_loss", 0),
            "Chốt lời (TP)": master.get("take_profit", 0)
        })
        
        detailed_results[ticker] = {
            "ai_results": ai_results,
            "df": df,
            "master": master
        }
        
        # Gửi thông báo Telegram
        if enable_telegram and rec == "MUA":
            send_telegram_alert(ticker, rec, master.get("reasoning", ""))
            
    return summary_data, detailed_results

st.title("⚡ Trợ lý AI Giao dịch Chứng khoán (Gemini Pro)")

api_key_input = st.text_input("🔑 Nhập Google GenAI API Key:", type="password", placeholder="Paste API Key của bạn vào đây...")
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
    st.sidebar.info("Vui lòng cấu hình TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID trong file .env để nhận tin nhắn.")

# Input Section
col_input1, col_input2, col_input3 = st.columns([1, 1, 2])
with col_input1:
    tickers_input = st.text_input("Nhập mã cổ phiếu (cách nhau bởi dấu phẩy):", value="FPT").upper()
with col_input2:
    months = st.slider("Dữ liệu (tháng):", 3, 12, 6)
with col_input3:
    st.write("")
    st.write("")
    analyze_btn = st.button("🚀 Phân tích Đa chiều (Multi-Agent)", type="primary")
    st.caption("⚡ Hệ thống tích hợp Smart Rate Limiter: Tự động điều phối lưu lượng không lo lỗi 429!")

if analyze_btn:
    if not api_key_input:
        st.error("⚠️ Bạn cần nhập API Key để chạy AI Agents!")
        st.stop()
        
    configure_gemini(api_key_input)
    
    tickers = [t.strip() for t in tickers_input.split(',') if t.strip()]
    if not tickers:
        st.error("⚠️ Vui lòng nhập ít nhất 1 mã cổ phiếu hợp lệ.")
        st.stop()

    status = st.status(f"🔍 Đang phân tích Watchlist {len(tickers)} mã...", expanded=True)
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
        with st.expander(f"Phân tích {ticker} - {data['master'].get('recommendation', 'N/A').upper()}"):
            ai_results = data['ai_results']
            df = data['df']
            master = data['master']
            
            col_z1, col_z2, col_z3 = st.columns([2, 1.2, 1.2])
            
            with col_z1:
                st.markdown("**📊 Diễn biến Giá & Khối lượng**")
                fig = make_subplots(
                    rows=2, cols=1, shared_xaxes=True,
                    vertical_spacing=0.03, row_heights=[0.7, 0.3]
                )
                fig.add_trace(go.Candlestick(
                    x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Price"
                ), row=1, col=1)
                fig.add_trace(go.Bar(
                    x=df['time'], y=df['volume'], marker_color='rgba(0, 150, 255, 0.5)', name="Volume"
                ), row=2, col=1)
                fig.add_trace(go.Scatter(
                    x=df['time'], y=df['vol_sma20'], line=dict(color='orange', width=1), name="Vol SMA20"
                ), row=2, col=1)
                
                fig.update_layout(
                    height=400, xaxis_rangeslider_visible=False, 
                    margin=dict(l=0, r=0, t=10, b=0),
                    template='plotly_white'
                )
                st.plotly_chart(fig, use_container_width=True)
                
            with col_z2:
                st.markdown("**🧠 Phân tích AI Đa luồng**")
                st.info(f"**📈 Technical:**\n\n{ai_results.get('tech_analysis', 'Lỗi')}")
                st.info(f"**🏢 Fundamental:**\n\n{ai_results.get('fa_analysis', 'Lỗi')}")
                st.info(f"**🌐 Macro:**\n\n{ai_results.get('macro_analysis', 'Lỗi')}")
                
            with col_z3:
                st.markdown("**🎯 Quyết định (Master Agent)**")
                rec_color = "green" if master.get('recommendation', 'N/A').upper() == "MUA" else "red" if master.get('recommendation', 'N/A').upper() == "BÁN" else "gray"
                st.markdown(f"<h3 style='text-align: center; color: {rec_color}; border: 2px solid {rec_color}; padding: 10px; border-radius: 5px;'>{master.get('recommendation', 'N/A').upper()}</h3>", unsafe_allow_html=True)
                
                c1, c2 = st.columns(2)
                c1.metric("Tỷ trọng", f"{master.get('allocation_pct', 0)}%")
                c2.metric("Tâm lý", master.get('market_sentiment', 'N/A'))
                
                c3, c4 = st.columns(2)
                c3.metric("SL", f"{master.get('stop_loss', 0):,.0f} ₫")
                c4.metric("TP", f"{master.get('take_profit', 0):,.0f} ₫")
                
                st.markdown("**Lý do:**")
                st.write(master.get("reasoning", ""))
