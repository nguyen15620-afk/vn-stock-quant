import pandas as pd
from data_loader import load_historical_data

df = load_historical_data("MSN", months=1, interval='1d', use_yfinance_only=True)
df['date_str'] = df['time'].dt.strftime('%Y-%m-%d')
df.set_index('date_str', inplace=True, drop=False)

df_vnindex = load_historical_data("VNINDEX", months=1, interval='1d')
df_vnindex['date_str'] = df_vnindex['time'].dt.strftime('%Y-%m-%d')
df_vnindex.set_index('date_str', inplace=True)

print("YF (MSN) index:")
print(df.index.tolist()[-5:])
print("VND (VNINDEX) index:")
print(df_vnindex.index.tolist()[-5:])
