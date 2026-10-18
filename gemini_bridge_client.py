"""
gemini_bridge_client.py
Module kết nối trực tiếp giữa VN-Stock Quant và Gemini 4 Argon Pro
trên Microsoft Edge thông qua Chrome DevTools Protocol (CDP).
Hỗ trợ cơ chế Dual-Stage Alert lúc 14:25 - 14:30 và chức năng AI Second Opinion trên Dashboard.
"""

import sys
import json
import time
import asyncio
import logging
import requests
import websockets

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("GeminiBridge")

CDP_BASE_URL = "http://127.0.0.1:9222"

def is_edge_cdp_available() -> dict:
    """
    Kiểm tra trạng thái kết nối tới Microsoft Edge Debugging (Port 9222).
    Trả về dict: {"available": bool, "tab_found": bool, "model": str, "error": str}
    """
    try:
        resp = requests.get(f"{CDP_BASE_URL}/json", timeout=2)
        if resp.status_code != 200:
            return {"available": False, "tab_found": False, "model": "", "error": f"HTTP status {resp.status_code}"}
        tabs = resp.json()
        gem_tabs = [t for t in tabs if 'gemini.google.com' in t.get('url', '') and t.get('type') == 'page']
        if not gem_tabs:
            return {"available": True, "tab_found": False, "model": "", "error": "Chưa mở tab gemini.google.com trên Edge"}
        
        return {"available": True, "tab_found": True, "model": "Argon", "ws_url": gem_tabs[0].get('webSocketDebuggerUrl')}
    except Exception as e:
        return {"available": False, "tab_found": False, "model": "", "error": str(e)}

async def _send_to_gemini_async(prompt: str, timeout_sec: int = 65) -> tuple[bool, str]:
    """Hàm bất đồng bộ gửi prompt tới Gemini 4 Argon qua WebSocket CDP."""
    status = is_edge_cdp_available()
    if not status.get("available") or not status.get("tab_found"):
        return False, f"Lỗi kết nối Edge CDP: {status.get('error', 'Edge chưa mở cổng 9222 hoặc thiếu tab Gemini')}"
        
    ws_url = status.get("ws_url")
    if not ws_url:
        return False, "Không tìm thấy webSocketDebuggerUrl của tab Gemini."

    try:
        async with websockets.connect(ws_url, max_size=30*1024*1024) as ws:
            # 1. Kích hoạt Runtime domain
            await ws.send(json.dumps({'id': 1, 'method': 'Runtime.enable'}))
            await ws.recv()
            
            # 2. Đếm số response hiện có
            count_js = "document.querySelectorAll('model-response').length"
            await ws.send(json.dumps({'id': 2, 'method': 'Runtime.evaluate', 'params': {'expression': count_js, 'returnByValue': True}}))
            raw_cnt = json.loads(await ws.recv())
            initial_count = raw_cnt.get('result', {}).get('result', {}).get('value', 0)
            
            # 3. Đưa prompt vào Quill Editor
            set_text_js = f"""
            (() => {{
                const rich = document.querySelector('rich-textarea');
                const q = rich ? rich.__quill : null;
                if (q) {{
                    q.setText({json.dumps(prompt + "\\n")}, "user");
                    q.setSelection(q.getLength(), 0, "user");
                    return true;
                }}
                return false;
            }})()
            """
            await ws.send(json.dumps({'id': 3, 'method': 'Runtime.evaluate', 'params': {'expression': set_text_js, 'returnByValue': True}}))
            raw_set = json.loads(await ws.recv())
            has_set = raw_set.get('result', {}).get('result', {}).get('value', False)
            if not has_set:
                return False, "Không thể tương tác với ô nhập liệu rich-textarea trên giao diện Gemini."
                
            await asyncio.sleep(0.3)
            
            # 4. Kích hoạt gửi bằng bàn phím (KeyDown Enter)
            send_js = """
            (() => {
                const box = document.querySelector('rich-textarea div[role="textbox"]');
                if (box) {
                    box.focus();
                    const ev = new KeyboardEvent('keydown', {
                        key: 'Enter',
                        code: 'Enter',
                        keyCode: 13,
                        which: 13,
                        bubbles: true,
                        cancelable: true
                    });
                    box.dispatchEvent(ev);
                    return true;
                }
                return false;
            })()
            """
            await ws.send(json.dumps({'id': 4, 'method': 'Runtime.evaluate', 'params': {'expression': send_js, 'returnByValue': True}}))
            await ws.recv()
            
            logger.info(f"Đã chuyển dữ liệu sang Gemini 4 Argon. Đang theo dõi phản hồi (timeout={timeout_sec}s)...")
            
            # 5. Vòng lặp chờ phản hồi hoàn tất
            status_js = """
            (() => {
                const resps = document.querySelectorAll('model-response');
                const stopBtn = document.querySelector('button[aria-label*="Stop"], button[aria-label*="Dừng"], button[aria-label*="Cancel"], .stop-generating-button');
                const isGen = !!(stopBtn && stopBtn.offsetParent !== null);
                let text = "";
                if (resps.length > 0) {
                    const last = resps[resps.length - 1];
                    const mc = last.querySelector('message-content') || last;
                    text = (mc.textContent || mc.innerText || "").trim();
                }
                return {
                    count: resps.length,
                    isGen: isGen,
                    len: text.length,
                    text: text
                };
            })()
            """
            
            start_time = time.time()
            last_len = 0
            stable_cycles = 0
            
            # Đợi 2s đầu tiên để Gemini bắt đầu sinh câu trả lời
            await asyncio.sleep(2)
            
            while time.time() - start_time < timeout_sec:
                await asyncio.sleep(2.5)
                msg_id = int(time.time() * 1000) % 1000000
                await ws.send(json.dumps({'id': msg_id, 'method': 'Runtime.evaluate', 'params': {'expression': status_js, 'returnByValue': True}}))
                
                res = None
                while True:
                    raw_msg = await ws.recv()
                    data = json.loads(raw_msg)
                    if data.get('id') == msg_id:
                        res = data.get('result', {}).get('result', {}).get('value', {})
                        break
                        
                cur_count = res.get('count', 0)
                cur_len = res.get('len', 0)
                is_gen = res.get('isGen', False)
                elapsed = int(time.time() - start_time)
                
                # Nếu đã xuất hiện response mới và có văn bản
                if cur_count > initial_count and cur_len > 100:
                    if cur_len == last_len and not is_gen:
                        stable_cycles += 1
                    else:
                        stable_cycles = 0
                    last_len = cur_len
                    
                    # 2 chu kỳ liên tiếp độ dài không đổi và nút Stop biến mất -> Hoàn tất
                    if stable_cycles >= 2:
                        ans = res.get('text', '')
                        if ans.startswith('Gemini said'):
                            ans = ans[len('Gemini said'):].strip()
                        return True, ans

            # Nếu timeout nhưng đã nhận được phần lớn văn bản
            if last_len > 150:
                logger.warning(f"Chạm ngưỡng timeout ({timeout_sec}s), trả về văn bản hiện có ({last_len} ký tự).")
                ans = res.get('text', '')
                if ans.startswith('Gemini said'):
                    ans = ans[len('Gemini said'):].strip()
                return True, ans
                
            return False, f"Timeout ({timeout_sec}s) khi chờ Gemini 4 Argon phản hồi."
    except Exception as e:
        logger.error(f"Lỗi WebSocket giao tiếp với Edge CDP: {e}")
        return False, f"Lỗi WebSocket CDP: {str(e)}"

def ask_gemini_4_argon_sync(prompt: str, timeout_sec: int = 65) -> tuple[bool, str]:
    """Hàm đồng bộ gọi Gemini 4 Argon để tích hợp vào các script thông thường."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    if loop.is_running():
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(_send_to_gemini_async(prompt, timeout_sec))
    else:
        return loop.run_until_complete(_send_to_gemini_async(prompt, timeout_sec))

def format_candidates_payload(candidates: list, vnindex_val: float, vnindex_ma50: float, market_status: str) -> str:
    """Format danh sách các mã tiềm năng thành Payload Markdown chuẩn nén cho Gemini 4 Argon."""
    now_str = time.strftime('%Y-%m-%d %H:%M:%S')
    payload = f"### DỮ LIỆU THỊ TRƯỜNG LÚC 14:25 ({now_str})\n"
    payload += f"- **VN-INDEX**: {vnindex_val:,.1f} | **MA50**: {vnindex_ma50:,.1f} | **Trạng thái**: {market_status}\n\n"
    payload += "### TOP ỨNG VIÊN ĐẠT CHUẨN QUANT (14:25):\n"
    
    for c in candidates:
        payload += f"#### Mã: {c['ticker']} (Ngành: {c.get('sector', 'N/A')})\n"
        payload += f"- Giá hiện tại: {c['price']:,.0f} ₫ (Biên độ nến: High {c.get('high', c['price']):,.0f} - Low {c.get('low', c['price']):,.0f})\n"
        payload += f"- Close Location Value (CLV): {c.get('clv', 0.8):.2f} (Vị trí đóng cửa so với biên độ ngày)\n"
        payload += f"- Tỷ lệ Volume / MA20: {c.get('vol_ratio', 1.5):.1f}x\n"
        payload += f"- RSI(14): {c.get('rsi', 55):.1f} | MACD Hist: {c.get('macd_hist', 0):.2f}\n"
        payload += f"- Khối ngoại mua/bán ròng: {c.get('foreign_net', 'N/A')}\n"
        payload += f"- Cơ bản: P/E={c.get('pe', 'N/A')} | ROE={c.get('roe', 0)*100 if isinstance(c.get('roe'), (int, float)) else 'N/A'}%\n"
        payload += f"- Tín hiệu kích hoạt: {c.get('reason', 'N/A')}\n\n"
        
    return payload
