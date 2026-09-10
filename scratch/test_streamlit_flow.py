import pandas as pd
from data_loader import load_historical_data
from strategy import compute_indicators, generate_signals
from backtester import run_backtest
import sys

months = 24
interval = '1d'

# Force YFinance for MSN
df = load_historical_data("MSN", months=months, interval=interval, use_yfinance_only=True)
# Keep default behavior for VNINDEX (falls back to VNDirect)
df_vnindex = load_historical_data("VNINDEX", months=max(months, 6), interval=interval)

if not df_vnindex.empty:
    df_vnindex['sma50'] = df_vnindex['close'].rolling(50).mean()
    df_vnindex['date_str'] = df_vnindex['time'].dt.strftime('%Y-%m-%d')
    df_vnindex.set_index('date_str', inplace=True)
    market_regime_series = df_vnindex['close'] > df_vnindex['sma50']
else:
    market_regime_series = None

df['date_str'] = df['time'].dt.strftime('%Y-%m-%d')
df.set_index('date_str', inplace=True, drop=False)

df = compute_indicators(df)
df = generate_signals(df, strategy_type='trend', market_regime=market_regime_series)

bt = run_backtest(df)
print(f"Total trades: {bt.get('total_trades', 0)}")
print(f"Buy signals allowed: {(df['signal'] == 'Buy').sum()}")
