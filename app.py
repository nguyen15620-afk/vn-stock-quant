import streamlit as st
import pandas as pd
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

from data_loader import load_historical_data, load_fundamentals
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

tab1, tab2, tab3 = st.tabs(["📊 Tổng quan Thị trường", "🔍 Phân tích Chi tiết", "🚀 Quét Tín hiệu (Screener)"])

with tab1:
    st.header("📊 Bảng Điều Khiển: Sức Khỏe Thị Trường")
    st.write("Đánh giá xu hướng chung của thị trường (dựa trên rổ VN30) để quyết định tỷ trọng giải ngân an toàn.")
    
    # VNINDEX data is blocked on vnstock Cloud, and not supported on Yahoo Finance.
    # We use the E1VFVN30 ETF as a perfect proxy for the market trend using Yahoo Finance.
    df_vnindex = load_historical_data("E1VFVN30", months=6, use_yfinance_only=True)
    if not df_vnindex.empty:
        df_vnindex = compute_indicators(df_vnindex)
        df_vnindex = generate_signals(df_vnindex)
        
        latest_vn = df_vnindex.iloc[-1]
        prev_vn = df_vnindex.iloc[-2] if len(df_vnindex) > 1 else latest_vn
        
        # Layout metrics and Market Health
        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("Quỹ VN30 ETF (Đại diện VNINDEX)", f"{latest_vn['close']:,.0f}", f"{latest_vn['close'] - prev_vn['close']:,.0f}")
            
        with col2:
            # Market condition based on ETF trend
            score = latest_vn['score']
            if score >= 75:
                st.success(f"🟢 **TRẠNG THÁI: UPTREND MẠNH ({score}/100 điểm)**\n\n**Chiến lược:** Thị trường ủng hộ, tự tin giải ngân và ưu tiên nắm giữ cổ phiếu khỏe.")
            elif score == 50:
                st.warning(f"🟡 **TRẠNG THÁI: ĐI NGANG / TÍCH LŨY ({score}/100 điểm)**\n\n**Chiến lược:** Thị trường phân hóa, chỉ giao dịch với tỷ trọng nhỏ (30-50%) tại các mã có điểm sức mạnh cao.")
            else:
                st.error(f"🔴 **TRẠNG THÁI: DOWNTREND / RỦI RO ({score}/100 điểm)**\n\n**Chiến lược:** Cẩn trọng! Thị trường đang yếu, ưu tiên phòng thủ và cầm tiền mặt (Cash is King).")
        
        st.markdown("---")
        
        # Beautiful Candlestick Chart for Market
        fig_vn = go.Figure()
        fig_vn.add_trace(go.Candlestick(
            x=df_vnindex['time'], open=df_vnindex['open'], high=df_vnindex['high'], 
            low=df_vnindex['low'], close=df_vnindex['close'], name="VN30 ETF"
        ))
        fig_vn.add_trace(go.Scatter(x=df_vnindex['time'], y=df_vnindex['bb_mid'], line=dict(color='orange', width=2), name="Đường Hỗ trợ/Kháng cự (SMA20)"))
        
        fig_vn.update_layout(
            title="Biểu đồ Nhịp đập Thị trường (6 Tháng) - So sánh giá với Đường SMA20", 
            height=500, 
            xaxis_rangeslider_visible=False,
            margin=dict(l=0, r=0, t=40, b=0)
        )
        fig_vn.update_yaxes(autorange=True, fixedrange=False)
        
        st.plotly_chart(fig_vn, use_container_width=True)
    else:
        st.warning("Đang tải dữ liệu thị trường...")

with tab2:
    st.sidebar.header("Cài đặt (Settings)")
    ticker = st.sidebar.text_input("Mã cổ phiếu (Ticker / VNINDEX)", value="FPT").upper()
    months = st.sidebar.slider("Dữ liệu lịch sử (Tháng)", min_value=3, max_value=24, value=6, step=1)
    interval = st.sidebar.selectbox("Khung thời gian", options=["1d", "1wk", "1h"], format_func=lambda x: {"1d": "Ngày (Daily)", "1wk": "Tuần (Weekly)", "1h": "Giờ (Hourly)"}[x])

    st.sidebar.markdown("---")
    st.sidebar.subheader("🧪 Tùy chỉnh Backtest")
    strategy_options = ["trend", "turtle", "ichimoku", "mean_reversion", "momentum"]
    strategy_labels = {
        "trend": "Xu hướng (MACD + RSI + BB)", 
        "turtle": "Turtle Trading (Đột phá 20 ngày)", 
        "ichimoku": "Ichimoku (Phá Mây Kumo)", 
        "mean_reversion": "Bắt đáy (RSI Oversold)", 
        "momentum": "Động lượng (EMA Crossover)"
    }
    strategy_type = st.sidebar.selectbox("Chiến lược", options=strategy_options, format_func=lambda x: strategy_labels[x])
    take_profit = st.sidebar.number_input("Chốt lời (%) - Nhập 0 để tắt", min_value=0.0, max_value=100.0, value=15.0, step=1.0) / 100.0
    stop_loss = st.sidebar.number_input("Cắt lỗ (%) - Nhập 0 để tắt", min_value=0.0, max_value=100.0, value=7.0, step=1.0) / 100.0
    use_market_filter = st.sidebar.checkbox("🛡️ Chặn Mua khi VNINDEX < MA50", value=True)

    if st.button("Phân tích chi tiết"):
        with st.spinner("Đang tải dữ liệu và tính toán..."):
            # 1. Load Data
            df = load_historical_data(ticker, months=months, interval=interval)
            
            market_regime_series = None
            if use_market_filter:
                # Always fetch at least 6 months to ensure MA50 has enough data
                fetch_months = max(months, 6)
                df_vnindex = load_historical_data("VNINDEX", months=fetch_months, interval=interval)
                if not df_vnindex.empty:
                    df_vnindex['sma50'] = df_vnindex['close'].rolling(50).mean()
                    # Index by time for alignment
                    df_vnindex.set_index('time', inplace=True)
                    market_regime_series = df_vnindex['close'] > df_vnindex['sma50']
            
            if df.empty:
                st.error(f"Không thể tải dữ liệu cho mã {ticker}.")
            else:
                st.subheader(f"📈 Phân tích Kỹ thuật & Cơ bản: {ticker}")
                
                # Load Fundamentals (FA)
                fa_data = load_fundamentals(ticker)
                if fa_data:
                    with st.expander("📊 Chỉ số Cơ bản (FA) - Nguồn: Yahoo Finance", expanded=True):
                        fa1, fa2, fa3, fa4 = st.columns(4)
                        fa1.metric("P/E (Trailing)", f"{fa_data.get('PE', 0):.2f}" if fa_data.get('PE') else "N/A")
                        fa2.metric("EPS (VNĐ)", f"{fa_data.get('EPS', 0):,.0f}" if fa_data.get('EPS') else "N/A")
                        fa3.metric("ROE (%)", f"{fa_data.get('ROE', 0)*100:.2f}%" if fa_data.get('ROE') else "N/A")
                        fa4.metric("Tăng trưởng DT", f"{fa_data.get('RevenueGrowth', 0)*100:.2f}%" if fa_data.get('RevenueGrowth') else "N/A")
                
                # Align df index by time so we can pass aligned regime series
                df.set_index('time', inplace=True, drop=False)
                
                # 2. Compute Indicators
                df = compute_indicators(df)
                
                # 3. Generate Signals
                df = generate_signals(df, strategy_type=strategy_type, market_regime=market_regime_series)
                
                # 4. Run Backtest
                bt_results = run_backtest(df, take_profit_pct=take_profit, stop_loss_pct=stop_loss)
                
                # 5. Display Latest Info
                latest = df.iloc[-1]
                prev = df.iloc[-2] if len(df) > 1 else latest
                
                # Dynamic translation for Signal UX
                raw_signal = latest['signal']
                display_signal = raw_signal
                signal_color = "gray"
                
                if raw_signal == 'Buy':
                    display_signal = "🟢 MUA MỚI (Buy)"
                    signal_color = "#00cc00"
                elif raw_signal == 'Sell':
                    display_signal = "🔴 BÁN / CẮT LỖ (Sell)"
                    signal_color = "#ff3333"
                else: # Hold
                    score = latest['score']
                    if score >= 75:
                        display_signal = "📈 NẮM GIỮ CỔ PHIẾU (Hold Position)"
                        signal_color = "#33cc33"
                    elif score <= 25:
                        display_signal = "🛡️ ĐỨNG NGOÀI (Hold Cash)"
                        signal_color = "#ff9999"
                    else:
                        display_signal = "👀 QUAN SÁT (Watch)"
                        signal_color = "#cccccc"
                
                st.markdown(f"### Tín hiệu hôm nay: <span style='color:{signal_color}'>{display_signal}</span>", unsafe_allow_html=True)
                if latest['reason']:
                    st.info(f"Trạng thái / Lý do: {latest['reason']}")
                    
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
                st.subheader("🔍 Kết quả Backtest & Hiệu quả Đầu tư")
                
                col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns(5)
                col_b1.metric("Lợi nhuận Chiến lược", f"{bt_results['total_return_pct']:.2f}%")
                col_b2.metric("Lợi nhuận Mua & Giữ", f"{bt_results['market_return_pct']:.2f}%")
                col_b3.metric("Max Drawdown (Sụt giảm)", f"{bt_results['max_drawdown_pct']:.2f}%")
                col_b4.metric("Số lệnh đã đóng", f"{bt_results['total_trades']}")
                col_b5.metric("Tỷ lệ Thắng (Win rate)", f"{bt_results['win_rate_pct']:.1f}%")
                
                # Equity Curve
                df_bt = bt_results['df_backtest']
                fig_eq = go.Figure()
                fig_eq.add_trace(go.Scatter(x=df_bt['time'], y=df_bt['portfolio_value'], mode='lines', name='Chiến lược Quant', line=dict(color='green', width=2)))
                fig_eq.add_trace(go.Scatter(x=df_bt['time'], y=df_bt['market_portfolio_value'], mode='lines', name='Mua & Giữ (Buy & Hold)', line=dict(color='gray', dash='dash')))
                
                fig_eq.update_layout(
                    title="Đường cong Vốn (Equity Curve) - Khởi điểm 100 triệu VNĐ",
                    yaxis_title="Giá trị Tài khoản (VNĐ)",
                    height=400,
                    template='plotly_dark',
                    hovermode="x unified",
                    margin=dict(l=0, r=0, t=40, b=0)
                )
                st.plotly_chart(fig_eq, use_container_width=True)
                
                with st.expander("Dữ liệu Lịch sử & Tín hiệu"):
                    st.dataframe(df[['time', 'close', 'signal', 'reason', 'rsi', 'macd_hist', 'stoch_rsi_k', 'volume']].tail(50))
                    
            st.success("Hoàn thành!")

with tab3:
    st.subheader("🚀 Bộ quét tín hiệu Cổ phiếu")
    
    scan_mode = st.radio("Phạm vi quét:", ["Rổ VN30", "Danh mục cá nhân (Watchlist)"], horizontal=True)
    
    if scan_mode == "Danh mục cá nhân (Watchlist)":
        custom_tickers_input = st.text_input("Nhập các mã cổ phiếu cách nhau bằng dấu phẩy (VD: SSI, VND, HPG, FPT):", value="SSI, VND, HPG")
        tickers_to_scan = [t.strip().upper() for t in custom_tickers_input.split(",") if t.strip()]
    else:
        tickers_to_scan = VN30

    st.write(f"Hệ thống sẽ tải dữ liệu và kiểm tra các điều kiện Mua/Bán cho toàn bộ {len(tickers_to_scan)} mã cổ phiếu. Việc này có thể mất 10-30 giây.")
    
    col_opt1, col_opt2, col_opt3, col_opt4 = st.columns(4)
    with col_opt1:
        scan_interval = st.selectbox("Khung thời gian quét:", options=["1d", "1wk", "1h"], format_func=lambda x: {"1d": "Ngày (Daily)", "1wk": "Tuần (Weekly)", "1h": "Giờ (Hourly)"}[x])
    with col_opt2:
        use_yf = st.checkbox("⚡ Quét Nhanh (Yahoo Finance)", value=True)
    with col_opt3:
        use_fa_filter = st.checkbox("🛡️ Lọc Cơ bản (P/E<25, ROE>10%)", value=False)
    with col_opt4:
        use_market_filter_scan = st.checkbox("🛡️ Chặn Mua khi VNINDEX xấu", value=True)
    
    if st.button("Bắt đầu Quét", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        market_regime_series = None
        if use_market_filter_scan:
            status_text.text("Đang tải dữ liệu VNINDEX...")
            df_vnindex = load_historical_data("VNINDEX", months=6, interval=scan_interval)
            if not df_vnindex.empty:
                df_vnindex['sma50'] = df_vnindex['close'].rolling(50).mean()
                df_vnindex.set_index('time', inplace=True)
                market_regime_series = df_vnindex['close'] > df_vnindex['sma50']
        
        results = []
        
        for i, sym in enumerate(tickers_to_scan):
            status_text.text(f"Đang quét {sym} ({i+1}/{len(tickers_to_scan)})...")
            
            passed_fa = True
            pe_val = "N/A"
            roe_val = "N/A"
            if use_fa_filter:
                fa = load_fundamentals(sym)
                pe = fa.get("PE")
                roe = fa.get("ROE")
                pe_val = round(pe, 1) if pe else "N/A"
                roe_val = f"{roe*100:.1f}%" if roe else "N/A"
                
                if pe and roe:
                    if pe >= 25 or pe <= 0 or roe <= 0.1:
                        passed_fa = False
                else:
                    passed_fa = False # Missing data
            
            if passed_fa:
                # Use 6 months to calculate long indicators like Ichimoku 52 safely and SMA50
                df_scan = load_historical_data(sym, months=6, use_yfinance_only=use_yf, interval=scan_interval) 
                if not df_scan.empty:
                    df_scan.set_index('time', inplace=True, drop=False)
                    df_scan = compute_indicators(df_scan)
                    df_scan = generate_signals(df_scan, market_regime=market_regime_series)
                    
                    latest_scan = df_scan.iloc[-1]
                    
                    raw_signal = latest_scan['signal']
                    if raw_signal == 'Buy':
                        display_signal = "🟢 MUA MỚI"
                    elif raw_signal == 'Sell':
                        display_signal = "🔴 BÁN / CẮT LỖ"
                    else:
                        score = latest_scan['score']
                        if score >= 75:
                            display_signal = "📈 NẮM GIỮ"
                        elif score <= 25:
                            display_signal = "🛡️ ĐỨNG NGOÀI"
                        else:
                            display_signal = "👀 QUAN SÁT"
                    
                    res_dict = {
                        "Mã CP": sym,
                        "Điểm (0-100)": int(latest_scan['score']),
                        "Vị thế hiện tại": latest_scan['trend_status'],
                        "Tín hiệu hôm nay": display_signal,
                        "Lý do": latest_scan['reason'] if latest_scan['reason'] else "-",
                        "Ngày": latest_scan['time'].strftime('%Y-%m-%d'),
                        "Giá Close": f"{latest_scan['close']:,.0f}"
                    }
                    if use_fa_filter:
                        res_dict["P/E"] = pe_val
                        res_dict["ROE"] = roe_val
                        
                    results.append(res_dict)
                
            progress_bar.progress((i + 1) / len(tickers_to_scan))
            
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
# Force Streamlit reload
# Reload app.py
