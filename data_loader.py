import os
import sys
import logging
import pandas as pd
import requests
from datetime import datetime, timedelta

# Ensure UTF-8 output safely (avoid errors on non-Windows/Linux container streams)
try:
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

logger = logging.getLogger(__name__)

# List of VN30 components (standard current constituent list)
VN30 = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "PNJ", "POW", "SAB", "SHB", "SSB", "SSI",
    "STB", "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB"
]

# Import vnstock safely
try:
    from vnstock import Quote
    HAS_VNSTOCK = True
except ImportError:
    try:
        from vnstock.api.quote import Quote
        HAS_VNSTOCK = True
    except ImportError:
        HAS_VNSTOCK = False

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

# Safe streamlit caching wrapper that doesn't break or warn in CLI scripts
def cache_decorator(*dargs, **dkwargs):
    def decorator(fn):
        cached_fn = None
        def wrapped(*args, **kwargs):
            nonlocal cached_fn
            try:
                if HAS_STREAMLIT:
                    import streamlit as st
                    if hasattr(st, "runtime") and st.runtime.exists():
                        if cached_fn is None:
                            cached_fn = st.cache_data(*dargs, **dkwargs)(fn)
                        return cached_fn(*args, **kwargs)
            except Exception:
                pass
            return fn(*args, **kwargs)
        return wrapped
    return decorator

def _safe_st_error(msg: str):
    """Safely log error and display to Streamlit UI if running within an active Streamlit app."""
    logger.error(msg)
    if HAS_STREAMLIT:
        try:
            import streamlit as st
            # Only call st.error if Streamlit script context is active
            if hasattr(st, "runtime") and st.runtime.exists():
                st.error(msg)
        except Exception:
            pass


@cache_decorator(ttl=3600)
def load_fundamentals(symbol: str) -> dict:
    """
    Loads fundamental data (P/E, P/B, EPS, ROE, Margins) for a given symbol using yfinance.
    """
    try:
        if not HAS_YF or symbol.upper() in ['VNINDEX', 'E1VFVN30']:
            return {}
        yf_symbol = f"{symbol.upper()}.VN"
        info = yf.Ticker(yf_symbol).info
        if not info or not isinstance(info, dict):
            return {}
        return {
            "PE": info.get("trailingPE") or info.get("forwardPE"),
            "PB": info.get("priceToBook"),
            "EPS": info.get("trailingEps"),
            "ROE": info.get("returnOnEquity"),
            "RevenueGrowth": info.get("revenueGrowth"),
            "GrossMargins": info.get("grossMargins"),
            "ProfitMargins": info.get("profitMargins"),
            "MarketCap": info.get("marketCap")
        }
    except Exception as e:
        logger.warning(f"Error loading fundamentals for {symbol}: {e}")
        return {}

@cache_decorator(ttl=3600)  # Cache data for 1 hour to prevent spamming the API
def load_historical_data(symbol: str, months: int = 36, use_yfinance_only: bool = False, interval: str = "1d") -> pd.DataFrame:
    """
    Loads historical OHLCV data for a given symbol.
    months: default 36 (3 years for robust market cycle analysis and backtesting)
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
        
        if not use_yfinance_only and HAS_VNSTOCK:
            for source in sources:
                try:
                    q = Quote(symbol=symbol_upper, source=source)
                    temp_df = q.history(start=start_str, end=end_str, resolution=vns_resolution)
                    if temp_df is not None and not temp_df.empty:
                        df = temp_df
                        break  # Success!
                except Exception as e:
                    last_error = str(e)
                    continue  # Try next source
                    
        # Reliable fallback for VNINDEX using VNDirect API
        if (df is None or df.empty) and symbol_upper == 'VNINDEX':
            vnd_res = 'D'
            if interval == '1wk': vnd_res = 'W'
            elif interval == '1h': vnd_res = '60'
            
            start_ts = int(start_date.timestamp())
            end_ts = int(end_date_api.timestamp())
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                url = f"https://dchart-api.vndirect.com.vn/dchart/history?resolution={vnd_res}&symbol=VNINDEX&from={start_ts}&to={end_ts}"
                res = requests.get(url, headers=headers, timeout=5)
                if res.status_code == 200:
                    res_json = res.json()
                    if res_json.get('s') == 'ok':
                        df = pd.DataFrame({
                            'time': pd.to_datetime(res_json['t'], unit='s'),
                            'open': res_json['o'],
                            'high': res_json['h'],
                            'low': res_json['l'],
                            'close': res_json['c'],
                            'volume': res_json['v']
                        })
            except Exception as e:
                last_error = f"{last_error} | VNDirect API error: {str(e)}"
                
        # Check if local data is insufficient for long periods (> 24 months) or empty
        min_expected_bars = int(months * 14) if months > 24 else 15
        needs_yfinance_fill = (df is None or df.empty or (months > 24 and len(df) < min_expected_bars))

        # Fallback to yfinance if empty or insufficient bars for long timeframe
        if needs_yfinance_fill and HAS_YF:
            try:
                # E1VFVN30 ETF is our VNINDEX proxy on yfinance
                if symbol_upper == "E1VFVN30":
                    yf_symbol = "E1VFVN30.VN"
                else:
                    yf_symbol = "^VNINDEX" if symbol_upper == "VNINDEX" else f"{symbol_upper}.VN"
                ticker = yf.Ticker(yf_symbol)
                
                # Fetch history with explicit interval
                temp_df = ticker.history(start=start_str, end=end_str, interval=interval)
                if temp_df is not None and not temp_df.empty:
                    temp_df = temp_df.reset_index()
                    # Normalize Date column from yfinance
                    date_col = 'Date' if 'Date' in temp_df.columns else ('Datetime' if 'Datetime' in temp_df.columns else None)
                    if date_col:
                        temp_df.rename(columns={date_col: 'time'}, inplace=True)
                    # Convert to datetime and strip timezone
                    temp_df['time'] = pd.to_datetime(temp_df['time'])
                    if temp_df['time'].dt.tz is not None:
                        temp_df['time'] = temp_df['time'].dt.tz_localize(None)
                    df = temp_df
            except Exception as e:
                last_error = f"{last_error} | yfinance error: {str(e)}"
                
        if df is None or df.empty:
            _safe_st_error(f"Không thể lấy dữ liệu cho {symbol} từ tất cả các nguồn. Lỗi: {last_error}")
            return pd.DataFrame()
            
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
                _safe_st_error(f"Missing required column '{col}' in data.")
                return pd.DataFrame()
                
        # Ensure sorting by time ascending
        df = df.sort_values('time').reset_index(drop=True)
        
        # Ensure numeric types
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        return df
    except Exception as e:
        _safe_st_error(f"Error loading data for {symbol}: {str(e)}")
        return pd.DataFrame()
