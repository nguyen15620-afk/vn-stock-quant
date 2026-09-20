import pytest
import pandas as pd
from datetime import datetime, timedelta
from data_loader import VN30, load_historical_data

def test_vn30_constituents():
    """Kiểm tra danh sách VN30 đủ 30 mã và không bị trùng lặp"""
    assert len(VN30) == 30
    assert len(set(VN30)) == 30
    assert "FPT" in VN30
    assert "HPG" in VN30
    assert "VCB" in VN30
    assert "VIC" in VN30

def test_historical_data_structure():
    """Kiểm tra cấu trúc và chuẩn hóa dữ liệu OHLCV"""
    df = load_historical_data("FPT", months=1)
    if not df.empty:
        required_cols = ['time', 'open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            assert col in df.columns, f"Cột {col} phải có trong DataFrame"
        assert pd.api.types.is_datetime64_any_dtype(df['time'])
        assert (df['close'] > 0).all()
