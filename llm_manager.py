import google.generativeai as genai
from aiolimiter import AsyncLimiter

import asyncio

_limiters = {}

def get_flash_limiter():
    loop = asyncio.get_running_loop()
    if loop not in _limiters:
        _limiters[loop] = {'flash': AsyncLimiter(15, 60), 'master': AsyncLimiter(5, 60)}
    return _limiters[loop]['flash']

def get_master_limiter():
    loop = asyncio.get_running_loop()
    if loop not in _limiters:
        _limiters[loop] = {'flash': AsyncLimiter(15, 60), 'master': AsyncLimiter(5, 60)}
    return _limiters[loop]['master']

def get_best_available_model(api_key: str, tier: str = "flash") -> str:
    """Trả về cứng định danh model để tránh lỗi Quota và tận dụng Lite"""
    if api_key:
        genai.configure(api_key=api_key)
        
    if tier == "flash":
        return "gemini-3.5-flash-lite"
    elif tier == "master":
        return "gemini-3.8-flash"
        
    return "gemini-3.5-flash-lite"

