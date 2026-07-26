# Decision: Use Cohere Embedding Model

## Decision
Hệ thống sử dụng mô hình Embedding của **Cohere** (ví dụ: `embed-english-v3.0` hoặc `embed-multilingual-v3.0`) để chuyển đổi Knowledge Object thành Vector số.

## Context
Chất lượng của Semantic Search phụ thuộc rất lớn vào khả năng biểu diễn ngữ nghĩa của mô hình Embedding. Chúng ta cần một mô hình không chỉ chính xác mà còn phải dễ tích hợp, có chi phí hợp lý hoặc free tier tốt, và phù hợp với ngôn ngữ tiếng Anh (ngôn ngữ chính của các tài liệu AI).

## Why This Decision?
1.  **High Quality:** Các mô hình của Cohere thường xếp hạng cao trong các bảng đánh giá (MTEB) về khả năng truy xuất thông tin (Retrieval), đặc biệt là với các văn bản kỹ thuật dài.
2.  **API Ease-of-use:** Cohere cung cấp API đơn giản, tốc độ phản hồi nhanh và tài liệu hướng dẫn rõ ràng, dễ dàng tích hợp vào LangChain.
3.  **Cost-Effective:** Cohere có chính sách free tier khá hào phóng cho developer, phù hợp với quy mô xử lý hàng chục đến vài trăm bài báo mỗi ngày của AI-Radar.
4.  **Multilingual Support (Optional):** Nếu trong tương lai cần thu thập nguồn tiếng Việt, mô hình `embed-multilingual` của Cohere là một lựa chọn an toàn mà không cần thay đổi kiến trúc.

## Why Not Alternatives?
-   **Not OpenAI (text-embedding-3-small/large):** Mặc dù chất lượng rất tốt, nhưng việc phụ thuộc thêm vào một API key của OpenAI sẽ tăng sự phụ thuộc nhà cung cấp. Cohere cung cấp giải pháp thay thế cạnh tranh với chi phí/thuật toán riêng biệt.
-   **Not Local Models (e.g., BAAI/bge-m3 via SentenceTransformers):** Chạy local đòi hỏi tài nguyên CPU/RAM đáng kể mỗi khi Pipeline chạy. Với nguyên tắc Asynchronous by Default và chạy trên server nhỏ, việc gọi API external thường ổn định và nhẹ nhàng hơn cho ứng dụng chính.
-   **Not HuggingFace Inference API:** Miễn phí nhưng thường bị giới hạn rate limit và độ trễ không ổn định, không phù hợp cho một hệ thống cần chạy đúng lịch trình hàng ngày.

## Impact
-   Module `integrations/cohere/` hoặc `vectorstores/embedding_service.py` sẽ chịu trách nhiệm gọi API Cohere.
-   Kích thước Vector (Dimension) sẽ phụ thuộc vào model cụ thể được chọn (thường là 1024 hoặc 768 dimensions).
-   Cần đảm bảo API Key của Cohere được quản lý an toàn trong `.env`.