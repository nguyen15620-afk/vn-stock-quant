import google.generativeai as genai
import re
from aiolimiter import AsyncLimiter

# Global rate limiters (Token Bucket)
# Flash models: Free Tier limit is 15 RPM
flash_limiter = AsyncLimiter(15, 60)
# Pro models: Free Tier limit is 2 RPM
pro_limiter = AsyncLimiter(2, 60)

def get_best_available_model(api_key: str, tier: str = "flash") -> str:
    """Bulletproof Model Scanner: Hỏi trực tiếp máy chủ Google để lấy model hợp lệ nhất"""
    if api_key:
        genai.configure(api_key=api_key)
        
    available_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
    except Exception as e:
        print(f"Lỗi khi quét list_models: {e}")
        if tier == "flash":
            return "models/gemini-1.5-flash"
        return "models/gemini-1.5-pro"
        
    print(f"DEBUG - Models khả dụng: {available_models}")
    
    if not available_models:
        if tier == "flash":
            return "models/gemini-1.5-flash"
        return "models/gemini-1.5-pro"
        
    if tier == "flash":
        flash_models = [m for m in available_models if "1.5-flash" in m.lower()]
        if flash_models:
            flash_models.sort(key=len)
            return flash_models[0]
            
        any_flash = [m for m in available_models if "flash" in m.lower()]
        if any_flash:
            any_flash.sort(key=len)
            return any_flash[0]
            
    elif tier == "pro":
        pro_models = [m for m in available_models if "1.5-pro" in m.lower()]
        if pro_models:
            pro_models.sort(key=len)
            return pro_models[0]
            
        any_pro = [m for m in available_models if "pro" in m.lower() and "vision" not in m.lower()]
        if any_pro:
            any_pro.sort(key=len)
            return any_pro[0]
            
    return available_models[0]
