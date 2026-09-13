import google.generativeai as genai
import re
from aiolimiter import AsyncLimiter

import asyncio

_limiters = {}

def get_flash_limiter():
    loop = asyncio.get_running_loop()
    if loop not in _limiters:
        _limiters[loop] = {'flash': AsyncLimiter(15, 60), 'pro': AsyncLimiter(2, 60)}
    return _limiters[loop]['flash']

def get_pro_limiter():
    loop = asyncio.get_running_loop()
    if loop not in _limiters:
        _limiters[loop] = {'flash': AsyncLimiter(15, 60), 'pro': AsyncLimiter(2, 60)}
    return _limiters[loop]['pro']

def extract_version(model_name: str) -> float:
    match = re.search(r'gemini-(\d+(\.\d+)?)-', model_name)
    if match:
        return float(match.group(1))
    return 0.0

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
        return "models/gemini-flash-latest" if tier == "flash" else "models/gemini-pro-latest"
        
    print(f"DEBUG - Models khả dụng: {available_models}")
    
    if not available_models:
        return "models/gemini-flash-latest" if tier == "flash" else "models/gemini-pro-latest"
        
    if tier == "flash":
        flash_models = [m for m in available_models if "flash" in m.lower() and "tts" not in m.lower() and "image" not in m.lower()]
        if flash_models:
            # Ưu tiên version cao nhất (vd: 3.8 > 3.6 > 2.5), sau đó ưu tiên tên ngắn gọn nhất
            flash_models.sort(key=lambda m: (-extract_version(m), len(m)))
            return flash_models[0]
            
    elif tier == "pro":
        pro_models = [m for m in available_models if "pro" in m.lower() and "tts" not in m.lower() and "image" not in m.lower() and "vision" not in m.lower()]
        if pro_models:
            # Ưu tiên version cao nhất (vd: 3.1 > 2.5), sau đó ưu tiên tên ngắn gọn nhất
            pro_models.sort(key=lambda m: (-extract_version(m), len(m)))
            return pro_models[0]
            
    # Fallback cuối cùng nếu không tìm thấy gì khớp
    return available_models[-1]
