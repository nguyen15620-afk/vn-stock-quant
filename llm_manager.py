import google.generativeai as genai
import re
from aiolimiter import AsyncLimiter

# Global rate limiters (Token Bucket)
# Flash models: Free Tier limit is 15 RPM
flash_limiter = AsyncLimiter(15, 60)
# Pro models: Free Tier limit is 2 RPM
pro_limiter = AsyncLimiter(2, 60)

# Cache for the model list to avoid redundant API calls
_cached_models = []

SAFE_WHITELIST = ["gemini-1.5-flash", "gemini-1.5-pro"]

def fetch_all_models(api_key: str):
    """Lấy danh sách tất cả các models khả dụng từ Google API và lọc theo SAFE_WHITELIST"""
    global _cached_models
    if _cached_models:
        return _cached_models
        
    genai.configure(api_key=api_key)
    raw_models = []
    
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            raw_models.append(m.name.replace('models/', ''))
            
    models = []
    for name in raw_models:
        # Bỏ qua tuyệt đối các dòng thử nghiệm, omni, preview...
        if 'omni' in name or 'exp' in name or 'preview' in name:
            continue
            
        # Chỉ giữ lại nếu nó nằm hoàn toàn trong SAFE_WHITELIST
        # Chúng ta kiểm tra nếu name == "gemini-1.5-flash" hoặc "gemini-1.5-pro"
        # Hoặc ít nhất nó bắt đầu bằng các string trong SAFE_WHITELIST và không có đuôi số
        if name in SAFE_WHITELIST:
            models.append(name)
        
    _cached_models = models
    return _cached_models

def get_best_available_model(api_key: str, tier: str = "flash") -> str:
    """Trả về tên model tốt nhất dựa trên yêu cầu tier (flash/pro)"""
    models = fetch_all_models(api_key)
    
    if not models:
        return "gemini-1.5-flash" # Fallback cứng nếu whitelist không match cái nào
    
    if tier == "pro":
        if "gemini-1.5-pro" in models:
            return "gemini-1.5-pro"
            
    if "gemini-1.5-flash" in models:
        return "gemini-1.5-flash"
        
    # Fallback cuối cùng
    return models[0]
