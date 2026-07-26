# Decision: Knowledge Intelligence System

## Decision
AI-Radar được định nghĩa là một **Knowledge Intelligence System** thay vì một Chatbot hay một công cụ tổng hợp tin tức (RSS Aggregator) thông thường.

## Context
Trong lĩnh vực AI, lượng thông tin mới xuất hiện mỗi ngày là khổng lồ và đa dạng (bài báo, paper, repo GitHub, blog kỹ thuật). Việc tiếp cận thủ công tốn nhiều thời gian lọc nhiễu và khó nắm bắt bức tranh tổng thể. Các chatbot truyền thống chỉ phản hồi khi có câu hỏi và không có khả năng chủ động cập nhật tri thức mới nhất nếu không được cung cấp ngữ cảnh.

## Why This Decision?
1.  **Chủ động thu thập:** Hệ thống cần tự động "quét" và học hỏi từ các nguồn dữ liệu theo lịch trình, biến dữ liệu thô thành tri thức có cấu trúc trước khi người dùng cần đến.
2.  **Tập trung vào giá trị tri thức:** Mục tiêu không phải là lưu trữ càng nhiều bài viết càng tốt, mà là trích xuất được những ý chính, xu hướng và công nghệ đáng chú ý nhất.
3.  **Hỗ trợ ra quyết định:** Cung cấp cho AI Engineer/Researcher một "bộ nhớ thứ hai" luôn cập nhật, giúp họ trả lời nhanh các câu hỏi về trạng thái hiện tại của công nghệ.

## Why Not Alternatives?
-   **Not a Chatbot:** Chatbot thụ động, phụ thuộc hoàn toàn vào kiến thức nền của mô hình (thường bị lỗi thời) hoặc ngữ cảnh do người dùng cung cấp. AI-Radar xây dựng kho tri thức riêng biệt và luôn mới.
-   **Not an RSS Reader:** RSS Reader chỉ hiển thị tiêu đề và link, người dùng vẫn phải tự đọc và tóm tắt. AI-Radar tự động hóa quá trình đọc hiểu và tóm tắt này.

## Impact
-   Kiến trúc hệ thống phải bao gồm **Knowledge Update Pipeline** chạy nền độc lập với tương tác người dùng.
-   Trọng tâm thiết kế chuyển sang việc chuẩn hóa dữ liệu đầu vào thành **Knowledge Object**.