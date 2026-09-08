# VN Stock Recommendation Tool

A Quantitative Trading Dashboard built with Python, Streamlit, and vnstock, designed specifically for the Vietnamese Stock Market (HOSE/HNX and VNINDEX).

## Features
- **Fetch Data**: Retrieves historical OHLCV data using the `vnstock` library.
- **Technical Indicators**: Calculates Bollinger Bands, Ichimoku Cloud, MACD, RSI, StochRSI, and Volume SMA using the `ta` library.
- **Rule Engine**: Generates automated Buy/Sell/Hold signals based on combined technical conditions.
- **Backtesting**: Simple vectorized backtest over customizable historical periods to evaluate Strategy vs Buy & Hold.
- **Interactive UI**: A rich Streamlit dashboard with interactive Plotly charts (Candlesticks + Subplots).

## Trading Rules
Currently, the strategy implements the following strict rules:
- **Buy**: Price > BB middle + RSI > 50 & rising + MACD hist > 0 + StochRSI crosses up below 20 + Volume > SMA9.
- **Sell**: Price < BB middle + RSI < 50 + MACD hist < 0 + StochRSI crosses down above 80.
- **Hold**: All other conditions.

## Installation

Ensure you have Python 3.10+ installed.

```bash
pip install -r requirements.txt
```

*(Note: Requires `vnstock`, `streamlit`, `plotly`, `ta`, `pandas`, `numpy`)*

## Usage

Run the Streamlit application:

```bash
streamlit run app.py
```

1. Open the provided local URL in your browser (usually http://localhost:8501).
2. Enter the Ticker Symbol (e.g., `FPT`, `HPG`, `VNM`, `VNINDEX`) in the left sidebar.
3. Select the historical data range (in months).
4. Click **Phân tích (Analyze)** to view the chart, indicators, and backtest results.
