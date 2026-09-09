import os
import sys
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

# Ensure UTF-8 output to avoid charmap errors on Windows when vnstock prints
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Import vnstock safely
try:
    from vnstock.api.quote import Quote
    USE_NEW_API = True
except ImportError:
    USE_NEW_API = False
    try:
        from vnstock import Vnstock
    except ImportError:
        pass

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False

@st.cache_data(ttl=3600)
def load_fundamentals(symbol: str) -> dict:
    """
    Loads fundamental data (P/E, EPS, ROE) for a given symbol using yfinance.
    """
    try:
        if not HAS_YF or symbol.upper() in ['VNINDEX', 'E1VFVN30']:
            return {}
        yf_symbol = f"{symbol.upper()}.VN"
        info = yf.Ticker(yf_symbol).info
        return {
            "PE": info.get("trailingPE"),
            "EPS": info.get("trailingEps"),
            "ROE": info.get("returnOnEquity"),
            "RevenueGrowth": info.get("revenueGrowth")
        }
    except Exception:
        return {}

@st.cache_data(ttl=3600)  # Cache data for 1 hour to prevent spamming the API
def load_historical_data(symbol: str, months: int = 12, use_yfinance_only: bool = False, interval: str = "1d") -> pd.DataFrame:
    """
    Loads historical OHLCV data for a given symbol.
    interval: "1d" (daily), "1wk" (weekly), "1h" (hourly)
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30 * months)
    
    start_str = start_date.strftime('%Y-%m-%d')
    # API endpoints (like yfinance) often use exclusive end dates. Add 1 day to include today.
    end_date_api = end_date + timedelta(days=1)
    end_str = end_date_api.strftime('%Y-%m-%d')
    
    try:
        symbol_upper = symbol.upper()
        df = None
        last_error = ""
        
        # Streamlit Cloud runs on foreign IPs, which often get blocked by Vietnamese brokers (like VCI).
        # We will try multiple sources until one succeeds.
        sources = ['TCBS', 'SSI', 'VND', 'VCI']
        
        # vnstock resolution mapping
        vns_resolution = '1D'
        if interval == '1wk':
            vns_resolution = '1W'
        elif interval == '1h':
            vns_resolution = '1H'
        
        if not use_yfinance_only:
            for source in sources:
                try:
                    if USE_NEW_API:
                        # New API as per vnstock 4.0 migration guide
                        q = Quote(symbol=symbol_upper, source=source)
                        # vnstock 4.0 may not support resolution for all sources
                        temp_df = q.history(start=start_str, end=end_str, resolution=vns_resolution)
                    else:
                        # Fallback for old API
                        if symbol_upper == 'VNINDEX':
                            stock = Vnstock().stock(symbol='VNINDEX', source=source)
                        else:
                            stock = Vnstock().stock(symbol=symbol_upper, source=source)
                        temp_df = stock.quote.history(start=start_str, end=end_str)
                    
                    if temp_df is not None and not temp_df.empty:
                        df = temp_df
                        break  # Success!
                except Exception as e:
                    last_error = str(e)
                    continue # Try next source
                    
        # Reliable fallback for VNINDEX using VNDirect API
        if (df is None or df.empty) and symbol_upper == 'VNINDEX':
            import requests
            import time
            vnd_res = 'D'
            if interval == '1wk': vnd_res = 'W'
            elif interval == '1h': vnd_res = '60'
            
            start_ts = int(start_date.timestamp())
            end_ts = int(end_date_api.timestamp())
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                url = f"https://dchart-api.vndirect.com.vn/dchart/history?resolution={vnd_res}&symbol=VNINDEX&from={start_ts}&to={end_ts}"
                res = requests.get(url, headers=headers).json()
                if res.get('s') == 'ok':
                    df = pd.DataFrame({
                        'time': pd.to_datetime(res['t'], unit='s'),
                        'open': res['o'],
                        'high': res['h'],
                        'low': res['l'],
                        'close': res['c'],
                        'volume': res['v']
                    })
            except Exception as e:
                last_error = f"{last_error} | VNDirect API error: {str(e)}"
                
        # If vnstock completely fails, fallback to yfinance
        if (df is None or df.empty) and HAS_YF:
            try:
                # E1VFVN30 ETF is our VNINDEX proxy on yfinance
                if symbol_upper == "E1VFVN30":
                    yf_symbol = "E1VFVN30.VN"
                else:
                    yf_symbol = "^VNINDEX" if symbol_upper == "VNINDEX" else f"{symbol_upper}.VN"
                ticker = yf.Ticker(yf_symbol)
                
                # yfinance interval uses the exact same format: 1d, 1wk, 1h
                temp_df = ticker.history(start=start_str, end=end_str, interval=interval)
                
                if temp_df is not None and not temp_df.empty:
                    # yfinance returns index as Date/Datetime, we need to reset it
                    temp_df = temp_df.reset_index()
                    # Rename columns to match what vnstock provides
                    temp_df.rename(columns={
                        'Date': 'time', 'Datetime': 'time',
                        'Open': 'open', 'High': 'high', 'Low': 'low', 
                        'Close': 'close', 'Volume': 'volume'
                    }, inplace=True)
                    # Convert timezone aware to timezone naive for Streamlit compatibility if needed
                    if temp_df['time'].dt.tz is not None:
                        temp_df['time'] = temp_df['time'].dt.tz_localize(None)
                    df = temp_df
            except Exception as e:
                last_error = f"{last_error} | yfinance error: {str(e)}"
                
        if df is None or df.empty:
            st.error(f"Không thể lấy dữ liệu cho {symbol} từ tất cả các nguồn. Lỗi cuối cùng: {last_error}")
            return pd.DataFrame()
            
        # Depending on the vnstock version and source, columns might vary.
        # Standardize column names to lowercase.
        df.columns = [c.lower() for c in df.columns]
        
        # Ensure 'time' column exists and is datetime
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
        elif 'date' in df.columns:
            df.rename(columns={'date': 'time'}, inplace=True)
            df['time'] = pd.to_datetime(df['time'])
            
        # Make sure essential columns exist
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col not in df.columns:
                st.error(f"Missing required column '{col}' in data.")
                return pd.DataFrame()
                
        # Ensure sorting by time ascending
        df = df.sort_values('time').reset_index(drop=True)
        
        # Ensure numeric types
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        return df
    except Exception as e:
        st.error(f"Error loading data for {symbol}: {str(e)}")
        return pd.DataFrame()
