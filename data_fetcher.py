import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import traceback

# Cố gắng import vnstock
try:
    from vnstock import financial_ratio, stock_historical_data
    VNSTOCK_AVAILABLE = True
except ImportError:
    VNSTOCK_AVAILABLE = False
    print("Warning: vnstock library not found or failed to import.")

@st.cache_data(ttl=300)
def get_fundamental_data(ticker: str) -> dict:
    """
    Lấy dữ liệu cơ bản (P/E, P/B, ROE, EPS) sử dụng vnstock.
    Cache 5 phút (300s).
    """
    if not VNSTOCK_AVAILABLE:
        return {"error": "Thư viện vnstock chưa được cài đặt hoặc lỗi import."}
        
    try:
        # Lấy dữ liệu tỷ số tài chính (thường trả về dataframe theo năm hoặc quý)
        df_ratio = financial_ratio(ticker, 'yearly', True)
        if df_ratio is not None and not df_ratio.empty:
            latest = df_ratio.iloc[0] # Lấy năm gần nhất
            
            return {
                "P/E": round(latest.get('priceToEarning', 0), 2),
                "P/B": round(latest.get('priceToBook', 0), 2),
                "ROE": f"{round(latest.get('roe', 0) * 100, 2)}%",
                "Biên LN Gộp": f"{round(latest.get('grossProfitMargin', 0) * 100, 2)}%",
                "Note": "Dữ liệu được cập nhật từ vnstock (BCTC gần nhất)"
            }
        else:
            return {"error": f"Không tìm thấy dữ liệu tài chính cho {ticker}"}
            
    except Exception as e:
        # Fallback nếu vnstock lỗi (do API SSI/TCBS thay đổi)
        print(f"Lỗi lấy dữ liệu FA vnstock cho {ticker}: {e}")
        return {"error": f"Lỗi cào dữ liệu FA: {str(e)}"}

@st.cache_data(ttl=300)
def get_macro_flow() -> str:
    """
    Lấy thông tin Vĩ mô và Thị trường chung (Sức mạnh VNINDEX) sử dụng vnstock.
    Cache 5 phút.
    """
    if not VNSTOCK_AVAILABLE:
        return "Lỗi: Không thể lấy dữ liệu Vĩ mô do thiếu vnstock."
        
    try:
        # Lấy diễn biến VNINDEX 5 phiên gần nhất
        end_date = datetime.now()
        start_date = end_date - timedelta(days=10)
        
        df_vnindex = stock_historical_data("VNINDEX", start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), "1D", "index")
        
        if df_vnindex is not None and not df_vnindex.empty:
            recent_data = df_vnindex.tail(5)
            
            # Tính toán xu hướng
            latest_close = recent_data.iloc[-1]['close']
            old_close = recent_data.iloc[0]['close']
            trend = "Tăng" if latest_close > old_close else "Giảm"
            
            summary = f"Chỉ số VNINDEX hiện tại: {latest_close:,.2f}.\n"
            summary += f"Xu hướng 5 phiên gần nhất: {trend}.\n"
            summary += "Dữ liệu giá 5 phiên:\n"
            summary += recent_data[['time', 'close', 'volume']].to_string(index=False)
            
            return summary
        else:
            return "Không lấy được dữ liệu VNINDEX từ vnstock."
            
    except Exception as e:
        print(f"Lỗi lấy dữ liệu Vĩ mô vnstock: {e}")
        return f"Lỗi cào dữ liệu VNINDEX: {str(e)}"
