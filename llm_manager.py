import google.generativeai as genai
import re
from aiolimiter import AsyncLimiter

# Global rate limiters (Token Bucket)
# Flash models: Free Tier limit is 15 RPM
flash_limiter = AsyncLimiter(15, 60)
# Pro models: Free Tier limit is 2 RPM
pro_limiter = AsyncLimiter(2, 60)

def get_best_available_model(api_key: str, tier: str = "flash") -> str:
    """Trả về tên model tốt nhất dựa trên yêu cầu tier (flash/pro)"""
    genai.configure(api_key=api_key)
    valid_models = []
    
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if tier == "flash" and "flash" in m.name.lower():
                    valid_models.append(m.name)
                elif tier == "pro" and "pro" in m.name.lower():
                    valid_models.append(m.name)
    except Exception as e:
        print(f"Lỗi khi lấy danh sách model: {e}")
        
    if valid_models:
        # Ưu tiên các model cơ bản ngắn gọn
        valid_models.sort(key=len)
        return valid_models[0]
        
    # Safety Fallback
    if tier == "flash":
        return "gemini-1.5-flash-latest"
    return "gemini-1.5-pro-latest"
