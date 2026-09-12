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

def fetch_all_models(api_key: str):
    """Lấy danh sách tất cả các models khả dụng từ Google API"""
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
        # Bỏ qua các model cũ có số phiên bản cụ thể (ví dụ: -001, -002)
        if re.search(r'-\d{3}$', name):
            continue
        # Bỏ qua các model không phải gemini
        if 'gemini' not in name:
            continue
        # Bỏ qua bản -latest nếu đã có bản gốc
        if name.endswith('-latest'):
            base = name.replace('-latest', '')
            if base in raw_models:
                continue
        # Bỏ qua gemini-3.x-pro vì thường bị khóa (limit=0) trên Free Tier
        if 'pro' in name and ('3' in name or '2' in name):
            continue
            
        models.append(name)
        
    _cached_models = models
    return _cached_models

def get_best_available_model(api_key: str, tier: str = "flash") -> str:
    """Trả về tên model tốt nhất dựa trên yêu cầu tier (flash/pro)"""
    models = fetch_all_models(api_key)
    
    if tier == "pro":
        # Tìm model pro mới nhất (ưu tiên gemini-1.5-pro)
        pro_models = [m for m in models if 'pro' in m]
        if pro_models:
            # Sắp xếp để bản mới nhất nằm cuối hoặc tùy logic, ở đây lấy phần tử cuối cùng
            pro_models.sort()
            return pro_models[-1]
            
    # Nếu là flash hoặc không tìm thấy pro, trả về flash
    flash_models = [m for m in models if 'flash' in m]
    if flash_models:
        flash_models.sort()
        # Ưu tiên bản gemini-1.5-flash
        for m in flash_models:
            if '1.5-flash' in m and '8b' not in m:
                return m
        return flash_models[-1]
        
    # Fallback cuối cùng nếu không có gì
    return models[0] if models else "gemini-1.5-flash"
