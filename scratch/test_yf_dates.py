import pandas as pd
from data_loader import load_historical_data
from strategy import compute_indicators, generate_signals

df = load_historical_data("MSN", months=24, interval='1d', use_yfinance_only=True)
df['date_str'] = df['time'].dt.strftime('%Y-%m-%d')
df.set_index('date_str', inplace=True, drop=False)
df = compute_indicators(df)

df_vnindex = load_historical_data("VNINDEX", months=24, interval='1d')
df_vnindex['sma50'] = df_vnindex['close'].rolling(50).mean()
df_vnindex['date_str'] = df_vnindex['time'].dt.strftime('%Y-%m-%d')
df_vnindex.set_index('date_str', inplace=True)
market_regime = df_vnindex['close'] > df_vnindex['sma50']

df_filtered = generate_signals(df, strategy_type='trend', market_regime=market_regime)
print("Buy signals before filter:", (generate_signals(df, strategy_type='trend')['signal'] == 'Buy').sum())
print("Buy signals after filter:", (df_filtered['signal'] == 'Buy').sum())
