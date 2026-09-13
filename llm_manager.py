import google.generativeai as genai
import re
from aiolimiter import AsyncLimiter

# Global rate limiters (Token Bucket)
# Flash models: Free Tier limit is 15 RPM
flash_limiter = AsyncLimiter(15, 60)
# Pro models: Free Tier limit is 2 RPM
pro_limiter = AsyncLimiter(2, 60)

def get_best_available_model(api_key: str, tier: str = "flash") -> str:
    """Trả về tên model cứng để tránh lỗi 404"""
    if api_key:
        genai.configure(api_key=api_key)
        
    if tier == "flash":
        return "gemini-1.5-flash-latest"
    return "gemini-1.5-pro-latest"
