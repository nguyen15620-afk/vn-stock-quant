"""
styles.py - Design System & Custom CSS for VN Stock Quant & Multi-Agent AI Assistant
Professional Dark-Mode Fintech Aesthetic (Bloomberg / TradingView inspired)
"""

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

/* --- Root Design Tokens (Dark Mode Only) --- */
:root {
    --bg-main: #0B0E14;
    --bg-surface: #121721;
    --bg-card: #18202F;
    --bg-card-hover: #1E283B;
    --border-subtle: #242F42;
    --border-strong: #334155;
    
    --text-primary: #F1F5F9;
    --text-secondary: #94A3B8;
    --text-muted: #64748B;
    
    --accent-cyan: #38BDF8;
    --accent-blue: #2563EB;
    --accent-green: #10B981;
    --accent-green-bg: rgba(16, 185, 129, 0.15);
    --accent-red: #F43F5E;
    --accent-red-bg: rgba(244, 63, 94, 0.15);
    --accent-yellow: #F59E0B;
    --accent-yellow-bg: rgba(245, 158, 11, 0.15);
    --accent-purple: #A855F7;
    --accent-purple-bg: rgba(168, 85, 247, 0.15);
}

/* Base App Overrides */
html, body, [class*="css"], .stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background-color: var(--bg-main) !important;
    color: var(--text-primary) !important;
}

/* Sidebar styling */
[data-testid="stSidebar"] {
    background-color: var(--bg-surface) !important;
    border-right: 1px solid var(--border-subtle) !important;
}

[data-testid="stSidebar"] hr {
    border-color: var(--border-subtle) !important;
}

/* Header bar container */
.app-header {
    background: linear-gradient(135deg, #131A29 0%, #1A2337 100%);
    border: 1px solid var(--border-subtle);
    border-radius: 12px;
    padding: 18px 24px;
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.4);
}

.app-title-group h1 {
    font-size: 24px !important;
    font-weight: 800 !important;
    margin: 0 !important;
    letter-spacing: -0.5px;
    background: linear-gradient(90deg, #38BDF8, #818CF8, #C084FC);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.app-subtitle {
    font-size: 13px;
    color: var(--text-secondary);
    margin-top: 4px;
    font-weight: 400;
}

.header-badges {
    display: flex;
    gap: 10px;
    align-items: center;
}

.badge-model {
    background: rgba(56, 189, 248, 0.12);
    border: 1px solid rgba(56, 189, 248, 0.3);
    color: #7DD3FC;
    padding: 5px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}

.badge-live {
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.3);
    color: #6EE7B7;
    padding: 5px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}

.pulse-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: #10B981;
    box-shadow: 0 0 8px #10B981;
    display: inline-block;
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
    70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}

/* Custom Tabs styling */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background-color: var(--bg-surface);
    padding: 6px;
    border-radius: 10px;
    border: 1px solid var(--border-subtle);
}

.stTabs [data-baseweb="tab"] {
    border-radius: 8px !important;
    color: var(--text-secondary) !important;
    font-weight: 600 !important;
    padding: 10px 18px !important;
    background-color: transparent !important;
    border: none !important;
    transition: all 0.2s ease;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(56, 189, 248, 0.15), rgba(99, 102, 241, 0.2)) !important;
    color: #38BDF8 !important;
    border: 1px solid rgba(56, 189, 248, 0.4) !important;
    box-shadow: 0 2px 10px rgba(56, 189, 248, 0.15) !important;
}

/* Cards & Containers */
.fintech-card {
    background-color: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 16px;
    transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.fintech-card:hover {
    border-color: var(--border-strong);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
}

/* Recommendation Badge styling */
.rec-badge-buy {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.25), rgba(5, 150, 105, 0.3));
    border: 1px solid #10B981;
    color: #34D399;
    font-weight: 800;
    font-size: 18px;
    padding: 8px 16px;
    border-radius: 8px;
    text-align: center;
    letter-spacing: 1px;
    text-shadow: 0 0 10px rgba(16, 185, 129, 0.3);
}

.rec-badge-sell {
    background: linear-gradient(135deg, rgba(244, 63, 94, 0.25), rgba(225, 29, 72, 0.3));
    border: 1px solid #F43F5E;
    color: #FB7185;
    font-weight: 800;
    font-size: 18px;
    padding: 8px 16px;
    border-radius: 8px;
    text-align: center;
    letter-spacing: 1px;
    text-shadow: 0 0 10px rgba(244, 63, 94, 0.3);
}

.rec-badge-hold {
    background: linear-gradient(135deg, rgba(245, 158, 11, 0.25), rgba(217, 119, 6, 0.3));
    border: 1px solid #F59E0B;
    color: #FBBF24;
    font-weight: 800;
    font-size: 18px;
    padding: 8px 16px;
    border-radius: 8px;
    text-align: center;
    letter-spacing: 1px;
}

/* Mini KPI Card */
.kpi-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 14px 16px;
    position: relative;
    overflow: hidden;
}

.kpi-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, #38BDF8, #818CF8);
}

.kpi-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: var(--text-muted);
    margin-bottom: 4px;
}

.kpi-value {
    font-size: 22px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-primary);
}

.kpi-desc {
    font-size: 11px;
    color: var(--text-secondary);
    margin-top: 4px;
}

/* Agent Accordion / Speech Bubble */
.agent-box {
    background: #141B29;
    border-left: 3px solid;
    border-radius: 0 10px 10px 0;
    padding: 12px 16px;
    margin-bottom: 12px;
}

.agent-tech { border-color: #38BDF8; }
.agent-fa { border-color: #10B981; }
.agent-macro { border-color: #A855F7; }

.agent-header {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    font-weight: 700;
    color: var(--text-secondary);
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.agent-body {
    font-size: 13px;
    line-height: 1.6;
    color: #CBD5E1;
}

/* Watchlist Mini Card */
.watchlist-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 10px;
    transition: all 0.2s ease;
}

.watchlist-card:hover {
    border-color: #38BDF8;
    background: var(--bg-card-hover);
}

/* Action Code Box */
.action-box {
    background: #090D14;
    border: 1px dashed var(--border-strong);
    border-radius: 6px;
    padding: 8px 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: #38BDF8;
    margin-top: 8px;
    word-break: break-all;
}

/* Progress Bar for Allocation */
.alloc-bar-bg {
    background-color: #1E293B;
    border-radius: 6px;
    height: 8px;
    width: 100%;
    overflow: hidden;
    margin-top: 6px;
}

.alloc-bar-fill {
    height: 100%;
    border-radius: 6px;
    background: linear-gradient(90deg, #10B981, #38BDF8);
    transition: width 0.4s ease;
}

/* Streamlit button override */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}

.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #2563EB, #1D4ED8) !important;
    border: 1px solid #3B82F6 !important;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35) !important;
}

.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #1D4ED8, #1E40AF) !important;
    box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5) !important;
    transform: translateY(-1px);
}

/* Scrollbar aesthetic */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: var(--bg-main);
}
::-webkit-scrollbar-thumb {
    background: var(--border-strong);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: var(--text-muted);
}
</style>
"""
