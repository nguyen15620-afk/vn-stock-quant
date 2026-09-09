import streamlit as st
import pandas as pd
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data_loader import load_historical_data
from strategy import compute_indicators, generate_signals
from backtester import run_backtest

st.set_page_config(page_title="VN Stock Quant", layout="wide")

st.title("📈 VN Stock Recommendation Tool")

# Constants
VN30 = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG", 
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "STB", "TCB", 
    "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE", "SSI"
]

tab1, tab2 = st.tabs(["🔍 Phân tích Chi tiết", "🚀 Quét Tín hiệu Toàn thị trường (Screener)"])

with tab1:
    st.sidebar.header("Cài đặt (Settings)")
    ticker = st.sidebar.text_input("Mã cổ phiếu (Ticker / VNINDEX)", value="FPT").upper()
    months = st.sidebar.slider("Dữ liệu lịch sử (Tháng)", min_value=3, max_value=24, value=6, step=1)

    if st.button("Phân tích chi tiết"):
        with st.spinner("Đang tải dữ liệu và tính toán..."):
            # 1. Load Data
            df = load_historical_data(ticker, months=months)
            
            if df.empty:
                st.error(f"Không thể tải dữ liệu cho mã {ticker}.")
            else:
                # 2. Compute Indicators
                df = compute_indicators(df)
                
                # 3. Generate Signals
                df = generate_signals(df)
                
                # 4. Run Backtest
                bt_results = run_backtest(df)
                
                # 5. Display Latest Info
                latest = df.iloc[-1]
                prev = df.iloc[-2] if len(df) > 1 else latest
                
                st.subheader(f"📊 Kết quả cho {ticker} (Ngày: {latest['time'].strftime('%Y-%m-%d')})")
                
                # Highlight Signal
                signal_color = "green" if latest['signal'] == 'Buy' else "red" if latest['signal'] == 'Sell' else "gray"
                st.markdown(f"### Tín hiệu hiện tại: <span style='color:{signal_color}'>{latest['signal']}</span>", unsafe_allow_html=True)
                if latest['reason']:
                    st.info(f"Lý do: {latest['reason']}")
                elif latest['signal'] == 'Hold':
                    st.info("Chưa có tín hiệu mới, tiếp tục nắm giữ hoặc đứng ngoài theo xu hướng trước đó.")
                    
                # Metrics Row
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Điểm Sức Mạnh", f"{int(latest['score'])}/100", f"{int(latest['score'] - prev['score'])}")
                col2.metric("Close", f"{latest['close']:,.0f}", f"{latest['close'] - prev['close']:,.0f}")
                col3.metric("RSI (14)", f"{latest['rsi']:.1f}", f"{latest['rsi'] - prev['rsi']:.1f}")
                col4.metric("MACD Hist", f"{latest['macd_hist']:.2f}", f"{latest['macd_hist'] - prev['macd_hist']:.2f}")
                col5.metric("Volume", f"{latest['volume']:,.0f}", f"{latest['volume'] - latest['vol_sma20']:,.0f} so với SMA20")
                
                st.markdown("---")
                
                # 6. Plotly Interactive Chart
                st.subheader("📈 Biểu đồ Kỹ thuật")
                
                fig = make_subplots(
                    rows=4, cols=1, shared_xaxes=True,
                    vertical_spacing=0.02,
                    row_heights=[0.5, 0.15, 0.15, 0.2],
                    subplot_titles=("Giá & Bollinger Bands / Ichimoku", "MACD", "RSI & StochRSI", "Volume")
                )
                
                # Row 1: Candlestick & Overlays
                fig.add_trace(go.Candlestick(
                    x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
                    name="Price"
                ), row=1, col=1)
                
                fig.add_trace(go.Scatter(x=df['time'], y=df['bb_mid'], line=dict(color='blue', width=1), name="BB Mid"), row=1, col=1)
                fig.add_trace(go.Scatter(x=df['time'], y=df['bb_up'], line=dict(color='gray', width=1, dash='dash'), name="BB Up"), row=1, col=1)
                fig.add_trace(go.Scatter(x=df['time'], y=df['bb_low'], line=dict(color='gray', width=1, dash='dash'), name="BB Low"), row=1, col=1)
                
                # Ichimoku Cloud
                fig.add_trace(go.Scatter(x=df['time'], y=df['ichi_senkou_a'], line=dict(color='rgba(0,255,0,0)'), showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(x=df['time'], y=df['ichi_senkou_b'], fill='tonexty', fillcolor='rgba(128,128,128,0.2)', line=dict(color='rgba(0,0,0,0)'), name="Ichi Cloud"), row=1, col=1)
                
                # Buy/Sell markers
                buy_signals = df[df['signal'] == 'Buy']
                sell_signals = df[df['signal'] == 'Sell']
                
                fig.add_trace(go.Scatter(x=buy_signals['time'], y=buy_signals['low'] * 0.98, mode='markers', marker=dict(symbol='triangle-up', color='green', size=12), name='Buy Signal'), row=1, col=1)
                fig.add_trace(go.Scatter(x=sell_signals['time'], y=sell_signals['high'] * 1.02, mode='markers', marker=dict(symbol='triangle-down', color='red', size=12), name='Sell Signal'), row=1, col=1)
                
                # Row 2: MACD
                colors = ['green' if val >= 0 else 'red' for val in df['macd_hist']]
                fig.add_trace(go.Bar(x=df['time'], y=df['macd_hist'], marker_color=colors, name="MACD Hist"), row=2, col=1)
                fig.add_trace(go.Scatter(x=df['time'], y=df['macd'], line=dict(color='blue', width=1), name="MACD"), row=2, col=1)
                fig.add_trace(go.Scatter(x=df['time'], y=df['macd_signal'], line=dict(color='orange', width=1), name="MACD Signal"), row=2, col=1)
                
                # Row 3: RSI & StochRSI
                fig.add_trace(go.Scatter(x=df['time'], y=df['rsi'], line=dict(color='purple', width=1), name="RSI"), row=3, col=1)
                fig.add_trace(go.Scatter(x=df['time'], y=df['stoch_rsi_k'], line=dict(color='blue', width=1), name="Stoch K"), row=3, col=1)
                fig.add_trace(go.Scatter(x=df['time'], y=df['stoch_rsi_d'], line=dict(color='orange', width=1, dash='dot'), name="Stoch D"), row=3, col=1)
                
                # Row 4: Volume
                fig.add_trace(go.Bar(x=df['time'], y=df['volume'], marker_color='lightblue', name="Volume"), row=4, col=1)
                fig.add_trace(go.Scatter(x=df['time'], y=df['vol_sma9'], line=dict(color='orange', width=1), name="Vol SMA9"), row=4, col=1)
                
                fig.update_layout(height=900, xaxis_rangeslider_visible=False, template='plotly_white')
                st.plotly_chart(fig, use_container_width=True)
                
                # 7. Backtest Results
                st.markdown("---")
                st.subheader("🔍 Kết quả Backtest")
                
                col_b1, col_b2, col_b3, col_b4 = st.columns(4)
                col_b1.metric("Lợi nhuận Chiến lược", f"{bt_results['total_return_pct']:.2f}%")
                col_b2.metric("Lợi nhuận Mua & Giữ", f"{bt_results['market_return_pct']:.2f}%")
                col_b3.metric("Số lệnh đã đóng", f"{bt_results['total_trades']}")
                col_b4.metric("Tỷ lệ Thắng (Win rate)", f"{bt_results['win_rate_pct']:.1f}%")
                
                with st.expander("Dữ liệu Lịch sử & Tín hiệu"):
                    st.dataframe(df[['time', 'close', 'signal', 'reason', 'rsi', 'macd_hist', 'stoch_rsi_k', 'volume']].tail(50))
                    
            st.success("Hoàn thành!")

with tab2:
    st.subheader("🚀 Bộ quét tín hiệu nhóm VN30")
    st.write("Hệ thống sẽ tải dữ liệu và kiểm tra các điều kiện Mua/Bán cho toàn bộ 30 mã cổ phiếu lớn nhất thị trường. Việc này có thể mất 10-30 giây.")
    
    use_yf = st.checkbox("⚡ Chế độ Quét Nhanh (Sử dụng dữ liệu Yahoo Finance - Rất khuyên dùng trên Cloud)", value=True)
    
    if st.button("Bắt đầu Quét", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        results = []
        
        for i, sym in enumerate(VN30):
            status_text.text(f"Đang quét {sym} ({i+1}/{len(VN30)})...")
            
            # Use 4 months to calculate long indicators like Ichimoku 52 safely
            df_scan = load_historical_data(sym, months=4, use_yfinance_only=use_yf) 
            if not df_scan.empty:
                df_scan = compute_indicators(df_scan)
                df_scan = generate_signals(df_scan)
                
                latest_scan = df_scan.iloc[-1]
                
                results.append({
                    "Mã CP": sym,
                    "Điểm (0-100)": int(latest_scan['score']),
                    "Vị thế hiện tại": latest_scan['trend_status'],
                    "Tín hiệu hôm nay": latest_scan['signal'],
                    "Lý do": latest_scan['reason'] if latest_scan['reason'] else "-",
                    "Ngày": latest_scan['time'].strftime('%Y-%m-%d'),
                    "Giá Close": f"{latest_scan['close']:,.0f}"
                })
                
            progress_bar.progress((i + 1) / len(VN30))
            
        status_text.text("Đã quét xong!")
        
        if results:
            df_results = pd.DataFrame(results)
            # Sort by Score descending
            df_results = df_results.sort_values(by="Điểm (0-100)", ascending=False).reset_index(drop=True)
            
            st.markdown("### 📋 Bảng Xếp Hạng Sức Mạnh VN30")
            
            # Lọc các danh mục
            df_strong = df_results[df_results["Điểm (0-100)"] >= 75]
            df_neutral = df_results[df_results["Điểm (0-100)"] == 50]
            df_weak = df_results[df_results["Điểm (0-100)"] <= 25]
            
            if not df_strong.empty:
                st.success(f"🟢 Nhóm MẠNH (Uptrend) - Tích cực nắm giữ ({len(df_strong)} mã):")
                st.dataframe(df_strong.style.apply(lambda x: ['background: #e6ffe6' for _ in x], axis=1), use_container_width=True)
                
            if not df_neutral.empty:
                st.warning(f"🟡 Nhóm TRUNG LẬP - Đang tích lũy/Đi ngang ({len(df_neutral)} mã):")
                st.dataframe(df_neutral.style.apply(lambda x: ['background: #ffffe6' for _ in x], axis=1), use_container_width=True)
                
            if not df_weak.empty:
                st.error(f"🔴 Nhóm YẾU (Downtrend) - Nên đứng ngoài ({len(df_weak)} mã):")
                st.dataframe(df_weak.style.apply(lambda x: ['background: #ffe6e6' for _ in x], axis=1), use_container_width=True)
                
            st.markdown("---")
            st.markdown("**Ghi chú Tín hiệu hôm nay:** Chỉ báo 'Buy' hoặc 'Sell' xuất hiện khi cổ phiếu có điểm bứt phá hoặc gãy nền trong đúng phiên hôm nay.")
        else:
            st.warning("Không có dữ liệu trả về trong quá trình quét.")
