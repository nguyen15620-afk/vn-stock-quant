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

@st.cache_data(ttl=3600)  # Cache data for 1 hour to prevent spamming the API
def load_historical_data(symbol: str, months: int = 12) -> pd.DataFrame:
    """
    Loads historical OHLCV data for a given symbol.
    Supports stocks and VNINDEX.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30 * months)
    
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    try:
        symbol_upper = symbol.upper()
        
        if USE_NEW_API:
            # New API as per vnstock 4.0 migration guide
            q = Quote(symbol=symbol_upper, source='VCI')
            df = q.history(start=start_str, end=end_str)
        else:
            # Fallback for old API
            if symbol_upper == 'VNINDEX':
                stock = Vnstock().stock(symbol='VNINDEX', source='VCI')
            else:
                stock = Vnstock().stock(symbol=symbol_upper, source='VCI')
            df = stock.quote.history(start=start_str, end=end_str)
        
        if df is None or df.empty:
            st.error(f"No data returned for {symbol}")
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
