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
from data_fetcher import get_fundamental_data, get_macro_flow
from strategy import compute_indicators
from ai_agents import analyze_stock_async, configure_gemini, QuotaExceededError

st.title("⚡ Trợ lý AI Giao dịch Chứng khoán (Gemini Pro)")

api_key_input = st.text_input("🔑 Nhập Google GenAI API Key:", type="password", placeholder="Paste API Key của bạn vào đây...")
if api_key_input:
    api_key_input = api_key_input.strip()

# Input Section
col_input1, col_input2, col_input3 = st.columns([1, 1, 2])
with col_input1:
    ticker = st.text_input("Nhập mã cổ phiếu:", value="FPT").upper()
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
        
    # Cấu hình Gemini với API Key và tự động cấp phát Model (Dynamic Model Manager)
    configure_gemini(api_key_input)
    
    # UX Tối ưu: Trạng thái chờ
    status = st.status("🔍 Đang tiến hành lấy dữ liệu và phân tích...", expanded=True)
    
    with status:
        st.write(f"📥 Đang tải dữ liệu lịch sử giá cho {ticker}...")
        df = load_historical_data(ticker, months=months)
        
        st.write("📊 Đang đọc Báo cáo Tài chính (vnstock)...")
        fa_data = get_fundamental_data(ticker)
        
        st.write("🌐 Đang lấy dữ liệu Vĩ mô & VNINDEX...")
        market_data_str = get_macro_flow()
        
        if df.empty:
            status.update(label="❌ Lỗi: Không tải được dữ liệu giá.", state="error")
            st.error(f"Không thể tải dữ liệu cho mã {ticker}.")
            st.stop()
            
        df = compute_indicators(df)
        current_price = df.iloc[-1]['close']
        
        # Prepare data strings for AI (Nén dữ liệu để tối ưu Input Token)
        tech_data_str = df[['time', 'close', 'volume', 'rsi', 'macd_hist']].tail(30).to_string(index=False)
        fa_data_str = json.dumps(fa_data, ensure_ascii=False) if isinstance(fa_data, dict) else str(fa_data)
        
        st.write("🧠 Khởi chạy Multi-Agent AI (Technical, Fundamental, Macro)...")
        st.write("⚖️ Master Agent đang phản biện và ra quyết định...")
        
        # 2. Run Multi-Agent AI asynchronously
        try:
            ai_results = asyncio.run(analyze_stock_async(
                ticker=ticker, 
                current_price=current_price, 
                tech_data=tech_data_str, 
                fa_data=fa_data_str, 
                market_data=market_data_str
            ))
            status.update(label="✅ Phân tích hoàn tất!", state="complete", expanded=False)
        except QuotaExceededError as qe:
            status.update(label="❌ Lỗi: Hết tài nguyên (Quota Exceeded)", state="error")
            st.error("⚠️ Hệ thống đã dùng hết tài nguyên AI miễn phí trong ngày (hoặc phút). Vui lòng chờ một lát rồi thử lại, hoặc nâng cấp API Key.")
            st.stop()
        except Exception as e:
            status.update(label="❌ Lỗi trong quá trình chạy AI", state="error")
            st.error(f"Lỗi khi chạy AI Agents: {e}")
            st.stop()
            
    master = ai_results.get("master_decision", {})

    # --- Minimalist UI: 3 Zones ---
    st.markdown("---")
    
    # Create 3 columns for the 3 zones
    col_z1, col_z2, col_z3 = st.columns([2, 1.2, 1.2])
    
    # Zone 1: Price / Volume Visualization
    with col_z1:
        st.subheader("📊 Diễn biến Giá & Khối lượng")
        
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            vertical_spacing=0.03, row_heights=[0.7, 0.3]
        )
        
        # Candlestick
        fig.add_trace(go.Candlestick(
            x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            name="Price"
        ), row=1, col=1)
        
        # Volume
        fig.add_trace(go.Bar(
            x=df['time'], y=df['volume'], marker_color='rgba(0, 150, 255, 0.5)', name="Volume"
        ), row=2, col=1)
        fig.add_trace(go.Scatter(
            x=df['time'], y=df['vol_sma20'], line=dict(color='orange', width=1), name="Vol SMA20"
        ), row=2, col=1)
        
        fig.update_layout(
            height=500, xaxis_rangeslider_visible=False, 
            margin=dict(l=0, r=0, t=30, b=0),
            template='plotly_white'
        )
        st.plotly_chart(fig, use_container_width=True)
        
    # Zone 2: Multi-Agent Signals
    with col_z2:
        st.subheader("🧠 Phân tích AI Đa luồng")
        
        with st.expander("📈 Chuyên viên Kỹ thuật (Technical)", expanded=True):
            st.write(ai_results.get("tech_analysis", "Lỗi tải"))
            
        with st.expander("🏢 Chuyên viên Cơ bản (Fundamental)", expanded=True):
            st.write(ai_results.get("fa_analysis", "Lỗi tải"))
            
        with st.expander("🌐 Chuyên viên Vĩ mô (Macro & Flow)", expanded=True):
            st.write(ai_results.get("macro_analysis", "Lỗi tải"))
            
    # Zone 3: Position Management & Master Agent Conclusion
    with col_z3:
        st.subheader("🎯 Quyết định Đầu tư (Master Agent)")
        
        rec = master.get("recommendation", "N/A").upper()
        rec_color = "green" if rec == "MUA" else "red" if rec == "BÁN" else "gray"
        
        st.markdown(f"<h3 style='text-align: center; color: {rec_color}; border: 2px solid {rec_color}; padding: 10px; border-radius: 5px;'>{rec}</h3>", unsafe_allow_html=True)
        
        st.markdown("#### Kế hoạch Hành động")
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("Tỷ trọng Đề xuất", f"{master.get('allocation_pct', 0)}%")
        col_m2.metric("Tâm lý Thị trường", master.get('market_sentiment', 'N/A'))
        
        col_p1, col_p2 = st.columns(2)
        col_p1.metric("Điểm Cắt lỗ (SL)", f"{master.get('stop_loss', 0):,.0f} ₫")
        col_p2.metric("Điểm Chốt lời (TP)", f"{master.get('take_profit', 0):,.0f} ₫")
        
        st.markdown("#### Lý do (Reasoning)")
        st.info(master.get("reasoning", "Không có dữ liệu"))
