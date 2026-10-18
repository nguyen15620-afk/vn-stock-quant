# BỐI CẢNH DỰ ÁN VN-STOCK QUANT & TÍCH HỢP GEMINI 4 ARGON PRO

### 1. Hiện trạng hệ thống (VN-Stock Recommendation):
- **Cơ chế phân tích định lượng (Quantitative Rules)**:
  - Lọc Market Regime: Chỉ mở vị thế mua khi VN-INDEX nằm trên đường MA50 (thị trường Uptrend / Bull market).
  - Đa khung thời gian (Multi-Timeframe): Khung Tuần xác nhận xu hướng tăng trung hạn (MACD > 0, EMA20 > EMA50, Supertrend xanh), Khung Ngày tìm điểm vào tối ưu.
  - Các chiến lược kích hoạt: Breakout đỉnh 20 phiên (Turtle Trading), Breakout mây Ichimoku Kumo, Nến phá vỡ kháng cự kèm Volume bùng nổ (> 1.5x MA20 Volume).
  - Lọc cơ bản: P/E hợp lý, ROE > 12-15%, EPS tăng trưởng.
- **Vận hành & Thực thi**:
  - Giao diện Dashboard phân tích trực quan viết bằng Streamlit (`app.py`).
  - Bot Telegram quét tự động (`alert_bot.py`), đặc biệt có nhịp quét chốt trước phiên ATC vào lúc **14:30** mỗi ngày giao dịch để báo tín hiệu kịp thời cho nhà đầu tư vào lệnh ATC.

### 2. Vấn đề đặt ra & Giải pháp kiến trúc Hybrid:
- **Vấn đề**: API Key chính thức của Gemini 4 Pro / Advanced rất đắt đỏ, không có gói Free Tier phù hợp để cá nhân gọi API liên tục mỗi ngày. Trong khi đó, người dùng đã đăng ký tài khoản trả phí Gemini Pro/Advanced trên Web Chat (`gemini.google.com`) với model **Gemini 4 Argon**.
- **Giải pháp**: Xây dựng cầu nối **CDP Bridge** (Chrome DevTools Protocol) tự động:
  - Hệ thống Quant Python chạy nền.
  - Khi đến khung giờ quét (đặc biệt 14:25 - 14:30), Quant Engine lọc ra Top 3 - 5 mã cổ phiếu đạt chuẩn kỹ thuật tốt nhất.
  - Gom dữ liệu dạng nén (JSON/Markdown) và gửi tự động sang tab Gemini 4 Argon đang mở trên Microsoft Edge (port 9222).
  - Gemini 4 Argon suy luận chuyên sâu, trả lời lại trong ~15-30 giây.
  - Bot nhận kết quả phân tích AI và bắn thẳng qua Telegram lúc 14:32 - 14:35, giúp nhà đầu tư có đầy đủ góc nhìn AI trước khi chốt lệnh ATC (14:30 - 14:45).

### 3. Yêu cầu dành cho Chief Architect (Gemini 4 Argon):
1. **Đánh giá kiến trúc Hybrid (Quant Engine + Web CDP Bridge)**:
   - Ưu điểm và những rủi ro kỹ thuật / rủi ro thực thi (độ trễ, timeout, session web, re-authentication).
   - Biện pháp khắc phục để hệ thống vận hành bền bỉ 24/7 không bị đứt gãy.
2. **Các điểm chạm AI (AI Touchpoints) trước giờ ATC (14:30)**:
   - Ngoài việc xác nhận lại tín hiệu kỹ thuật thô, Gemini 4 Argon có thể đóng góp những góc nhìn "thông minh" nào mà thuật toán code thuần không làm được? (Ví dụ: Phát hiện bẫy bull-trap / nến rút chân giả lúc cận ATC, tương quan dòng tiền khối ngoại / tự doanh, phân bổ tỷ trọng danh mục theo khẩu vị rủi ro, dự đoán cung cầu ATC, kịch bản chốt lời/cắt lỗ thích ứng).
3. **Thiết kế Data Pipeline & Định dạng Prompt chuẩn**:
   - Thiết kế cấu trúc JSON/Markdown nén gọn nhất để nạp dữ liệu (Nến 5 ngày gần nhất, RSI, MACD, Volume đột biến, Market Regime, Khối ngoại mua/bán ròng) mà không làm tràn context hoặc làm chậm tốc độ suy luận của Gemini.
   - Bản mẫu Prompt Template tối ưu để nhận về phản hồi có cấu trúc (Bullet points sắc bén, Tỷ lệ Action: MUA / THEO DÕI / BỎ QUA, Kế hoạch giá và Tỷ trọng danh mục).
