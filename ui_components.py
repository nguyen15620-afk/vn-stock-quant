"""
ui_components.py - Reusable Fintech UI Components for VN Stock Quant Assistant
Provides modular, clean, and visually impressive components for Streamlit.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os
from datetime import datetime

def render_header(api_key_configured: bool = True, master_model: str = "gemini-3.6-flash", sub_model: str = "gemini-3.5-flash-lite"):
    """Hiển thị Header Bar cố định với thông tin thương hiệu và trạng thái Model Cascade."""
    status_dot = '<span class="pulse-dot"></span> ĐANG HOẠT ĐỘNG' if api_key_configured else '<span style="color:#F43F5E;">● CHƯA CÓ API KEY</span>'
    
    header_html = f"""
    <div class="app-header">
        <div class="app-title-group">
            <h1>⚡ VN STOCK QUANT & MULTI-AGENT AI</h1>
            <div class="app-subtitle">Hệ thống Phân tích Định lượng & Trợ lý Đầu tư Đa tác tử cho Chứng khoán Việt Nam (HOSE / HNX / UPCOM)</div>
        </div>
        <div class="header-badges">
            <div class="badge-live">{status_dot}</div>
            <div class="badge-model" title="Model CIO Master Agent">👑 {master_model}</div>
            <div class="badge-model" title="Model Sub-Agents">🤖 {sub_model}</div>
        </div>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)


def render_watchlist_cards(summary_data: list):
    """Hiển thị danh sách kết quả phân tích Watchlist theo dạng lưới thẻ Card chuyên nghiệp."""
    if not summary_data:
        st.info("Chưa có dữ liệu phân tích nào.")
        return

    cols = st.columns(min(len(summary_data), 4))
    for idx, item in enumerate(summary_data):
        col = cols[idx % min(len(summary_data), 4)]
        with col:
            ticker = item.get("Mã CP", "N/A")
            rec = str(item.get("Khuyến nghị", "GIỮ")).upper()
            action = item.get("Action (TCInvest Order)", "")
            alloc = int(item.get("Tỷ trọng (%)", 0))
            sl = item.get("Cắt lỗ (SL)", "-")
            tp = item.get("Chốt lời (TP)", "-")
            
            badge_class = "rec-badge-buy" if rec == "MUA" else ("rec-badge-sell" if rec == "BÁN" else "rec-badge-hold")
            rec_icon = "🟢" if rec == "MUA" else ("🔴" if rec == "BÁN" else "🟡")
            
            card_html = f"""
            <div class="watchlist-card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-size:18px; font-weight:800; color:#F8FAFC; letter-spacing:0.5px;">{ticker}</span>
                    <span class="{badge_class}" style="font-size:12px; padding:4px 10px;">{rec_icon} {rec}</span>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:12px; color:#94A3B8; margin-top:6px;">
                    <span>Cắt lỗ: <strong style="color:#F43F5E;">{sl}</strong></span>
                    <span>Chốt lời: <strong style="color:#34D399;">{tp}</strong></span>
                </div>
                <div style="margin-top:8px;">
                    <div style="display:flex; justify-content:space-between; font-size:11px; color:#64748B;">
                        <span>Tỷ trọng giải ngân</span>
                        <strong style="color:#38BDF8;">{alloc}%</strong>
                    </div>
                    <div class="alloc-bar-bg">
                        <div class="alloc-bar-fill" style="width: {alloc}%;"></div>
                    </div>
                </div>
                <div class="action-box" title="Cú pháp lệnh TCBS TCInvest">{action}</div>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)


def render_master_decision_card(master: dict, ticker: str, current_price: float, models_used: dict = None):
    """Hiển thị Card Quyết định của Master Agent (CIO) với phong cách fintech đẳng cấp."""
    rec = str(master.get("recommendation", "GIỮ")).upper()
    badge_class = "rec-badge-buy" if rec == "MUA" else ("rec-badge-sell" if rec == "BÁN" else "rec-badge-hold")
    rec_icon = "🚀" if rec == "MUA" else ("🔻" if rec == "BÁN" else "⏳")
    
    alloc_pct = master.get("allocation_pct", 0)
    sentiment = master.get("market_sentiment", "Neutral")
    sl_price = master.get("stop_loss", 0.0)
    tp_price = master.get("take_profit", 0.0)
    target_price = master.get("target_price", current_price)
    reasoning = master.get("reasoning", "Đang cập nhật lý do...")
    order_action = master.get("order_action", rec)
    
    sentiment_color = "#10B981" if "bull" in sentiment.lower() or "tích cực" in sentiment.lower() else ("#F43F5E" if "bear" in sentiment.lower() or "tiêu cực" in sentiment.lower() else "#F59E0B")
    
    st.markdown(f"""
    <div class="fintech-card" style="border-top: 3px solid #38BDF8;">
        <div style="text-align: center; margin-bottom: 12px;">
            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #94A3B8; margin-bottom: 4px;">🎯 QUYẾT ĐỊNH GIÁM ĐỐC ĐẦU TƯ (MASTER CIO)</div>
            <div class="{badge_class}">
                {rec_icon} {rec} ({order_action})
            </div>
        </div>
        
        <div style="background: rgba(18, 23, 33, 0.7); border: 1px solid #242F42; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px;">
                <span style="color: #94A3B8;">Tâm lý thị trường:</span>
                <strong style="color: {sentiment_color};">{sentiment}</strong>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px;">
                <span style="color: #94A3B8;">Tỷ trọng danh mục:</span>
                <strong style="color: #38BDF8;">{alloc_pct}%</strong>
            </div>
            <div class="alloc-bar-bg">
                <div class="alloc-bar-fill" style="width: {alloc_pct}%;"></div>
            </div>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-bottom: 12px; text-align: center;">
            <div style="background: rgba(244, 63, 94, 0.1); border: 1px solid rgba(244, 63, 94, 0.3); border-radius: 6px; padding: 6px;">
                <div style="font-size: 10px; color: #FDA4AF;">CẮT LỖ (SL)</div>
                <div style="font-size: 13px; font-weight: 700; color: #F43F5E; font-family: 'JetBrains Mono', monospace;">{sl_price:,.0f} ₫</div>
            </div>
            <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 6px; padding: 6px;">
                <div style="font-size: 10px; color: #BAE6FD;">GIÁ MỤC TIÊU</div>
                <div style="font-size: 13px; font-weight: 700; color: #38BDF8; font-family: 'JetBrains Mono', monospace;">{target_price:,.0f} ₫</div>
            </div>
            <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 6px; padding: 6px;">
                <div style="font-size: 10px; color: #A7F3D0;">CHỐT LỜI (TP)</div>
                <div style="font-size: 13px; font-weight: 700; color: #10B981; font-family: 'JetBrains Mono', monospace;">{tp_price:,.0f} ₫</div>
            </div>
        </div>
        
        <div style="margin-top: 10px;">
            <div style="font-size: 12px; font-weight: 700; color: #94A3B8; margin-bottom: 4px;">📝 Luận điểm & Lý do đầu tư:</div>
            <div style="font-size: 13px; line-height: 1.6; color: #E2E8F0; background: #0F141C; padding: 12px; border-radius: 6px; border: 1px solid #1E283B;">
                {reasoning}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    if models_used:
        st.caption(f"⚙️ Phục vụ bởi: Master (`{models_used.get('master', 'N/A')}`) | Sub-Agents (`{models_used.get('tech', 'N/A')}`)")


def render_agent_reports(ai_results: dict):
    """Hiển thị Báo cáo Chuyên sâu của 3 Chuyên viên AI (Technical, Fundamental, Macro)."""
    tech_text = ai_results.get("tech_analysis", "Chưa có dữ liệu.")
    fa_text = ai_results.get("fa_analysis", "Chưa có dữ liệu.")
    macro_text = ai_results.get("macro_analysis", "Chưa có dữ liệu.")
    
    st.markdown(f"""
    <div class="agent-box agent-tech">
        <div class="agent-header">
            <span>📈 Chuyên viên Kỹ thuật (Technical Analyst)</span>
            <span style="color:#38BDF8;">Hành vi giá & Động lượng</span>
        </div>
        <div class="agent-body">{tech_text}</div>
    </div>
    
    <div class="agent-box agent-fa">
        <div class="agent-header">
            <span>🏢 Chuyên viên Cơ bản (Fundamental Analyst)</span>
            <span style="color:#10B981;">Định giá & Tăng trưởng BCTC</span>
        </div>
        <div class="agent-body">{fa_text}</div>
    </div>
    
    <div class="agent-box agent-macro">
        <div class="agent-header">
            <span>🌐 Chuyên viên Vĩ mô & Dòng tiền (Macro & Flow Analyst)</span>
            <span style="color:#A855F7;">VN-INDEX & Tin tức</span>
        </div>
        <div class="agent-body">{macro_text}</div>
    </div>
    """, unsafe_allow_html=True)


def render_advanced_chart(df: pd.DataFrame, ticker: str, subchart_type: str = "MACD"):
    """
    Vẽ Biểu đồ Nến Dark Mode chuẩn Fintech với:
    - Nến Candlestick + Bollinger Bands + EMA 20, 50, SMA 200
    - Subplot 2: Khối lượng (Volume) & Vol SMA20
    - Subplot 3: Chỉ báo động lượng linh hoạt (MACD hoặc RSI)
    """
    if df.empty:
        st.warning("Không có dữ liệu để vẽ biểu đồ.")
        return

    # 3 Subplots: Price (0.6), Volume (0.2), Indicator (0.2)
    fig = make_subplots(
        rows=3, cols=1, 
        shared_xaxes=True,
        vertical_spacing=0.03, 
        row_heights=[0.60, 0.20, 0.20],
        subplot_titles=(f"{ticker} - OHLCV & Đường Xu Hướng", "Khối Lượng Giao Dịch", subchart_type)
    )

    # 1. Candlestick Price
    fig.add_trace(go.Candlestick(
        x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        increasing_line_color='#00E676', increasing_fillcolor='#00E676',
        decreasing_line_color='#FF1744', decreasing_fillcolor='#FF1744',
        name="Giá"
    ), row=1, col=1)

    # Bollinger Bands
    if 'bb_high' in df.columns and 'bb_low' in df.columns:
        fig.add_trace(go.Scatter(
            x=df['time'], y=df['bb_high'],
            line=dict(color='rgba(148, 163, 184, 0.4)', width=1, dash='dash'),
            name="BB Upper"
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df['time'], y=df['bb_low'],
            line=dict(color='rgba(148, 163, 184, 0.4)', width=1, dash='dash'),
            fill='tonexty', fillcolor='rgba(148, 163, 184, 0.05)',
            name="BB Lower"
        ), row=1, col=1)

    # Moving Averages
    if 'ema20' in df.columns:
        fig.add_trace(go.Scatter(
            x=df['time'], y=df['ema20'], line=dict(color='#38BDF8', width=1.5), name="EMA 20"
        ), row=1, col=1)
    if 'ema50' in df.columns:
        fig.add_trace(go.Scatter(
            x=df['time'], y=df['ema50'], line=dict(color='#F59E0B', width=1.5), name="EMA 50"
        ), row=1, col=1)
    if 'sma200' in df.columns:
        fig.add_trace(go.Scatter(
            x=df['time'], y=df['sma200'], line=dict(color='#A855F7', width=1.5, dash='dot'), name="SMA 200"
        ), row=1, col=1)

    # Overlay Tín hiệu Mua/Bán nếu có trong df
    if 'signal' in df.columns:
        buys = df[df['signal'] == 'Buy']
        sells = df[df['signal'] == 'Sell']
        if not buys.empty:
            fig.add_trace(go.Scatter(
                x=buys['time'], y=buys['low'] * 0.985, mode='markers',
                marker=dict(symbol='triangle-up', size=11, color='#00E676'),
                name="Tín hiệu MUA"
            ), row=1, col=1)
        if not sells.empty:
            fig.add_trace(go.Scatter(
                x=sells['time'], y=sells['high'] * 1.015, mode='markers',
                marker=dict(symbol='triangle-down', size=11, color='#FF1744'),
                name="Tín hiệu BÁN"
            ), row=1, col=1)

    # 2. Volume Bar
    vol_colors = ['#00E676' if c >= o else '#FF1744' for c, o in zip(df['close'], df['open'])]
    fig.add_trace(go.Bar(
        x=df['time'], y=df['volume'], marker_color=vol_colors, opacity=0.8, name="Volume"
    ), row=2, col=1)
    
    if 'vol_sma20' in df.columns:
        fig.add_trace(go.Scatter(
            x=df['time'], y=df['vol_sma20'], line=dict(color='#F59E0B', width=1.2), name="Vol SMA20"
        ), row=2, col=1)

    # 3. Indicator Subplot (MACD hoặc RSI)
    if subchart_type == "MACD" and 'macd' in df.columns:
        fig.add_trace(go.Scatter(
            x=df['time'], y=df['macd'], line=dict(color='#38BDF8', width=1.5), name="MACD"
        ), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=df['time'], y=df['macd_signal'], line=dict(color='#F59E0B', width=1.2), name="Signal"
        ), row=3, col=1)
        hist_colors = ['#00E676' if v >= 0 else '#FF1744' for v in df['macd_hist']]
        fig.add_trace(go.Bar(
            x=df['time'], y=df['macd_hist'], marker_color=hist_colors, opacity=0.7, name="Hist"
        ), row=3, col=1)
    elif subchart_type == "RSI" and 'rsi' in df.columns:
        fig.add_trace(go.Scatter(
            x=df['time'], y=df['rsi'], line=dict(color='#C084FC', width=1.8), name="RSI (14)"
        ), row=3, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="rgba(244, 63, 94, 0.6)", row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="rgba(16, 185, 129, 0.6)", row=3, col=1)

    # Dark Mode Layout
    fig.update_layout(
        template='plotly_dark',
        height=620,
        xaxis_rangeslider_visible=False,
        paper_bgcolor='#121721',
        plot_bgcolor='#121721',
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
            font=dict(size=11, color='#94A3B8')
        ),
        font=dict(family="Inter, sans-serif", color='#94A3B8'),
        hovermode="x unified"
    )
    
    fig.update_xaxes(gridcolor='#1E293B', zeroline=False)
    fig.update_yaxes(gridcolor='#1E293B', zeroline=False)

    st.plotly_chart(fig, use_container_width=True)


def render_kpi_dashboard(bt_results: dict):
    """Hiển thị 6 thẻ KPI Dashboard hiện đại cho kiểm định Quant Backtest."""
    ret = bt_results.get('total_return_pct', 0.0)
    bm_ret = bt_results.get('benchmark_return_pct', 0.0)
    win_rate = bt_results.get('win_rate_pct', 0.0)
    pf = bt_results.get('profit_factor', 0.0)
    mdd = bt_results.get('max_drawdown_pct', 0.0)
    sharpe = bt_results.get('sharpe_ratio', 0.0)
    total_trades = bt_results.get('total_trades', 0)
    wins = bt_results.get('winning_trades', 0)
    
    ret_color = "#10B981" if ret >= 0 else "#F43F5E"
    bm_color = "#10B981" if bm_ret >= 0 else "#F43F5E"
    alpha = ret - bm_ret
    alpha_str = f"+{alpha:.2f}%" if alpha >= 0 else f"{alpha:.2f}%"
    alpha_color = "#10B981" if alpha >= 0 else "#F43F5E"

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    
    with c1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Lợi nhuận Chiến lược</div>
            <div class="kpi-value" style="color: {ret_color};">{ret:+.2f}%</div>
            <div class="kpi-desc">Alpha: <span style="color:{alpha_color};">{alpha_str}</span></div>
        </div>
        """, unsafe_allow_html=True)
        
    with c2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Buy & Hold Benchmark</div>
            <div class="kpi-value" style="color: {bm_color};">{bm_ret:+.2f}%</div>
            <div class="kpi-desc">Khấu trừ phí mua & bán</div>
        </div>
        """, unsafe_allow_html=True)
        
    with c3:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Tỷ lệ thắng (Win Rate)</div>
            <div class="kpi-value" style="color: #38BDF8;">{win_rate:.1f}%</div>
            <div class="kpi-desc">{wins}/{total_trades} lệnh thắng</div>
        </div>
        """, unsafe_allow_html=True)
        
    with c4:
        pf_color = "#10B981" if pf >= 1.5 else ("#F59E0B" if pf >= 1.0 else "#F43F5E")
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Profit Factor</div>
            <div class="kpi-value" style="color: {pf_color};">{pf:.2f}</div>
            <div class="kpi-desc">> 1.5: Chiến lược tốt</div>
        </div>
        """, unsafe_allow_html=True)
        
    with c5:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Max Drawdown</div>
            <div class="kpi-value" style="color: #F43F5E;">-{mdd:.2f}%</div>
            <div class="kpi-desc">Sụt giảm vốn tối đa</div>
        </div>
        """, unsafe_allow_html=True)
        
    with c6:
        sharpe_color = "#10B981" if sharpe >= 1.0 else ("#F59E0B" if sharpe >= 0.5 else "#94A3B8")
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Sharpe Ratio</div>
            <div class="kpi-value" style="color: {sharpe_color};">{sharpe:.2f}</div>
            <div class="kpi-desc">Annualized (Rf=5%)</div>
        </div>
        """, unsafe_allow_html=True)


def render_equity_comparison_chart(eq_df: pd.DataFrame):
    """Vẽ biểu đồ Đối sánh Vốn (Equity Curve) vs Buy & Hold Benchmark + Drawdown."""
    if eq_df.empty:
        return
        
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.75, 0.25],
        subplot_titles=("Tăng Trưởng Vốn: Chiến Lược Quant vs Buy & Hold", "Sụt Giảm Vốn (Drawdown %)")
    )
    
    # Đường Vốn Chiến Lược
    fig.add_trace(go.Scatter(
        x=eq_df['time'], y=eq_df['equity'],
        mode='lines', name="Chiến Lược Quant (VND)",
        line=dict(color='#00E676', width=2.5)
    ), row=1, col=1)
    
    # Đường Benchmark Buy & Hold
    if 'benchmark_equity' in eq_df.columns:
        fig.add_trace(go.Scatter(
            x=eq_df['time'], y=eq_df['benchmark_equity'],
            mode='lines', name="Buy & Hold Benchmark (VND)",
            line=dict(color='#94A3B8', width=1.5, dash='dash')
        ), row=1, col=1)
        
    # Drawdown Area
    if 'drawdown' in eq_df.columns:
        dd_pct = eq_df['drawdown'] * 100.0
        fig.add_trace(go.Scatter(
            x=eq_df['time'], y=dd_pct,
            fill='tozeroy', fillcolor='rgba(244, 63, 94, 0.25)',
            line=dict(color='#F43F5E', width=1),
            name="Drawdown (%)"
        ), row=2, col=1)

    fig.update_layout(
        template='plotly_dark',
        height=450,
        xaxis_rangeslider_visible=False,
        paper_bgcolor='#121721',
        plot_bgcolor='#121721',
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_xaxes(gridcolor='#1E293B')
    fig.update_yaxes(gridcolor='#1E293B')

    st.plotly_chart(fig, use_container_width=True)
