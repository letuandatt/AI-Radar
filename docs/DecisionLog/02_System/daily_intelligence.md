# Decision: Daily Intelligence as First-Class Feature

## Decision
Tính năng **Daily AI Intelligence** (gửi bản tin tổng hợp hàng ngày qua Zalo) được xác định là tính năng cốt lõi số 1 (First-Class Feature) của AI-Radar, quan trọng ngang hàng hoặc hơn cả chức năng Question Answering (RAG).

## Context
Tên dự án là "AI-Radar", ám chỉ khả năng liên tục quét và phát hiện tín hiệu mới. Người dùng cần một cách thụ động để nắm bắt tin tức mà không phải chủ động đi tìm kiếm mỗi ngày.

## Why This Decision?
1.  **Đúng với tên gọi Radar:** Radar hoạt động bằng cách quét liên tục và báo cáo kết quả. Daily Digest là hiện thực hóa trực tiếp nhất của khái niệm này.
2.  **Giảm tải nhận thức:** Thay vì phải kiểm tra 10-20 nguồn khác nhau mỗi sáng, người dùng chỉ cần đọc một bản tin đã được AI lọc và sắp xếp.
3.  **Thúc đẩy việc xây dựng Knowledge Base:** Để tạo được bản tin chất lượng, hệ thống bắt buộc phải xử lý và chuẩn hóa dữ liệu rất tốt, từ đó nâng cao chất lượng chung của kho tri thức phục vụ cho RAG sau này.

## Why Not Alternatives?
-   **Not Just Q&A:** Nếu chỉ tập trung vào Q&A, hệ thống sẽ thiếu đi tính chủ động và giá trị "cập nhật xu hướng" mà một Radar cần có.
-   **Not Real-time Notification:** Gửi tin ngay khi có bài mới sẽ gây nhiễu (spam) và không mang tính tổng hợp. Daily Digest chọn lọc những gì quan trọng nhất trong 24h.

## Impact
-   Pipeline xử lý phải đảm bảo chạy đúng lịch (Scheduled) và ổn định.
-   Cần có cơ chế đánh giá độ quan trọng (`importance_score`) của Knowledge Object để chọn lọc nội dung cho bản tin.
-   Tích hợp chặt chẽ với kênh phân phối (Zalo OA) ngay từ giai đoạn đầu.