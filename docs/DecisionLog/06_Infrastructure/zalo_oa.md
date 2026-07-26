# Decision: Use Zalo Official Account (OA) as Primary Channel

## Decision
Hệ thống sử dụng **Zalo Official Account (OA)** làm kênh giao tiếp duy nhất với người dùng cuối cho cả hai chức năng: gửi Daily Digest và nhận/trả lời câu hỏi RAG.

## Context
AI-Radar cần một kênh phân phối tin nhắn phổ biến, ổn định và hỗ trợ cả hai chiều (broadcast và interactive) tại thị trường mục tiêu (Việt Nam).

## Why This Decision?
1.  **User Convenience:** Zalo là ứng dụng nhắn tin phổ biến nhất tại Việt Nam. Người dùng không cần cài đặt thêm app mới (như Telegram/Discord) để sử dụng AI-Radar.
2.  **Rich Features:** Zalo OA hỗ trợ tốt việc gửi tin nhắn văn bản, hình ảnh và có cơ chế Webhook ổn định để nhận tin nhắn từ người dùng, phù hợp cho cả Digest và QA.
3.  **Local Relevance:** Phù hợp với đối tượng người dùng mục tiêu là các AI Engineer/Researcher tại Việt Nam.
4.  **Official API:** Zalo cung cấp tài liệu API rõ ràng và cơ chế xác thực Webhook an toàn, giúp việc tích hợp trở nên minh bạch và bảo mật.

## Why Not Alternatives?
-   **Not Telegram:** Mặc dù API rất tốt và dễ tích hợp, nhưng độ phổ biến tại Việt Nam thấp hơn Zalo. Việc yêu cầu người dùng chuyển sang Telegram có thể làm giảm tỷ lệ sử dụng.
-   **Not Email:** Email không phù hợp cho tương tác tức thời (QA) và dễ bị rơi vào spam folder. Định dạng email cũng kém linh hoạt hơn so với chat app.
-   **Not SMS:** Chi phí cao, giới hạn ký tự ngắn và không hỗ trợ định dạng văn bản phong phú (Markdown/Bold) cần thiết cho bản tin công nghệ.

## Impact
-   Module `integrations/zalo/` được xây dựng để xử lý Webhook verification, nhận message payload và gửi tin nhắn qua Zalo OA API.
-   Hệ thống cần quản lý `ZALO_ACCESS_TOKEN` và `WEBHOOK_SECRET` an toàn trong Environment Variables.
-   Logic business (Digest content, RAG answer) được tách biệt hoàn toàn khỏi lớp tích hợp Zalo, giúp dễ dàng mở rộng sang các kênh khác (Telegram/Email) trong tương lai nếu cần.