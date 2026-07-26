# Decision: Dual Pipeline Architecture

## Decision
AI-Radar vận hành dựa trên hai Pipeline độc lập:
1.  **Knowledge Update Pipeline (Scheduled):** Chạy định kỳ để thu thập và xây dựng tri thức.
2.  **Question Answering Pipeline (Interactive):** Chạy ngay lập tức khi người dùng đặt câu hỏi.

Hai Pipeline này **không chia sẻ trạng thái runtime** mà chỉ chia sẻ chung **Knowledge Base (Qdrant)**.

## Context
Nhiều hệ thống RAG truyền thống thường cố gắng làm mọi thứ trong thời gian thực (Real-time): khi người dùng hỏi thì mới đi crawl, summarize và embed. Cách này gây ra độ trễ rất lớn (vài chục giây đến vài phút) và tốn kém tài nguyên nếu nhiều người dùng cùng hỏi về một chủ đề.

## Why This Decision?
1.  **Low Latency for QA:** Vì tri thức đã được chuẩn bị sẵn trong Qdrant, Pipeline QA chỉ cần truy xuất và sinh câu trả lời, giúp thời gian phản hồi nhanh (dưới 5 giây).
2.  **Cost Efficiency:** Việc tóm tắt và embedding chỉ được thực hiện đúng một lần trong Update Pipeline. Nhiều người dùng hỏi cùng một câu hỏi sẽ không kích hoạt lại quá trình xử lý đắt đỏ này.
3.  **Stability:** Update Pipeline chạy nền, không bị ảnh hưởng bởi lưu lượng truy vấn của người dùng. Ngược lại, QA Pipeline không bị nghẽn nếu Update Pipeline đang chạy nặng.
4.  **Daily Intelligence Focus:** Update Pipeline đảm bảo nhiệm vụ cốt lõi là "Radar" – quét và báo cáo tin tức hàng ngày, bất kể có ai hỏi hay không.

## Why Not Alternatives?
-   **Not Real-time RAG:** Crawl và xử lý dữ liệu thô ngay lúc người dùng hỏi là quá chậm và không khả thi cho trải nghiệm chatbot.
-   **Not Single Mixed Pipeline:** Trộn lẫn logic update và query vào một luồng duy nhất sẽ làm code rối rắm, khó kiểm soát lỗi và khó tối ưu hiệu năng cho từng tác vụ riêng biệt.

## Impact
-   Hệ thống cần cơ chế Scheduler (GitHub Actions/Cron) để kích hoạt Update Pipeline.
-   Webhook Handler (Zalo) chỉ kích hoạt QA Pipeline.
-   Qdrant đóng vai trò là điểm hội tụ (Convergence Point) và là nguồn chân lý duy nhất (Single Source of Truth) cho cả hai Pipeline.