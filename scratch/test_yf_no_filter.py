import pandas as pd
from data_loader import load_historical_data
from strategy import compute_indicators, generate_signals

df = load_historical_data("MSN", months=24, interval='1d', use_yfinance_only=True)
df['date_str'] = df['time'].dt.strftime('%Y-%m-%d')
df.set_index('date_str', inplace=True, drop=False)
df = compute_indicators(df)
df = generate_signals(df, strategy_type='trend')

print(f"Buy signals without filter: {(df['signal'] == 'Buy').sum()}")
