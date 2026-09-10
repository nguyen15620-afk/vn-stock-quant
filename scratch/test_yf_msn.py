import pandas as pd
from data_loader import load_historical_data
from strategy import compute_indicators
import sys

df = load_historical_data("MSN", months=24, interval='1d', use_yfinance_only=True)
df = compute_indicators(df)
print(df[['close', 'bb_mid', 'macd_hist', 'rsi', 'volume', 'vol_sma20']].tail(10))
print(f"Volume = 0 count: {(df['volume'] == 0).sum()}")
print(f"Volume NaN count: {df['volume'].isna().sum()}")
