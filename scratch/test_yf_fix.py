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

mr_aligned = market_regime.reindex(df.index).fillna(False).astype(bool)

df_trend = generate_signals(df, strategy_type='trend')
buy_mask = df_trend['signal'] == 'Buy'
buy_dates = buy_mask[buy_mask].index

for d in buy_dates[:6]:
    print(f"Date: {d}")
    print(f"  mr_aligned[d]: {mr_aligned[d]}")
    print(f"  ~mr_aligned[d]: {(~mr_aligned)[d]}")
    print(f"  buy_mask[d]: {buy_mask[d]}")
    print(f"  combined: {(buy_mask & (~mr_aligned))[d]}")
