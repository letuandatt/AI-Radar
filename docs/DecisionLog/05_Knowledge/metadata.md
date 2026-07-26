# Decision: Rich Metadata Filtering for Retrieval

## Decision
Hệ thống sử dụng **Metadata Filtering** kết hợp với Semantic Search để nâng cao độ chính xác của quá trình Retrieval. Các trường metadata quan trọng bao gồm: `topics`, `published_at`, `source`, và `importance_score`.

## Context
Chỉ dựa vào độ tương đồng ngữ nghĩa (Cosine Similarity) đôi khi chưa đủ để lọc ra những tri thức phù hợp nhất. Ví dụ, người dùng có thể muốn hỏi về "xu hướng OCR mới nhất", lúc này yếu tố thời gian (`published_at`) và chủ đề (`topics`) quan trọng không kém nội dung ngữ nghĩa.

## Why This Decision?
1.  **Precision Boost:** Metadata filtering giúp loại bỏ các kết quả "nhiễu" dù có độ tương đồng ngữ nghĩa cao nhưng sai chủ đề hoặc quá cũ.
2.  **Support for Daily Digest:** Việc lọc theo `published_at` (trong ngày) và `importance_score` là bắt buộc để tạo ra bản tin hàng ngày chất lượng.
3.  **User Intent Handling:** Khi người dùng hỏi cụ thể về một framework hoặc một lĩnh vực, hệ thống có thể ngầm định filter theo `topics` tương ứng để thu hẹp phạm vi tìm kiếm.
4.  **Qdrant Capability:** Tận dụng khả năng lọc payload mạnh mẽ của Qdrant mà không cần phải xây dựng thêm index phức tạp.

## Why Not Alternatives?
-   **Not Pure Semantic Search:** Tìm kiếm thuần túy dễ bị lệch bởi các từ khóa chung chung hoặc các bài viết có nội dung tương tự nhưng không liên quan đến bối cảnh hiện tại.
-   **Not Keyword Search Only:** Vì chúng ta không lưu bài gốc nên keyword search trên nội dung đầy đủ là không khả thi. Metadata là cách thay thế hiệu quả nhất.

## Impact
-   Cấu trúc Payload trong Qdrant phải đảm bảo lưu trữ đầy đủ và chuẩn hóa các trường:
    -   `topics`: List[string] (ví dụ: ["LLM", "RAG"])
    -   `published_at`: Timestamp
    -   `importance_score`: Float
    -   `source`: String
-   Module `vectorstores/retriever.py` sẽ xây dựng logic filter động dựa trên câu hỏi hoặc yêu cầu của Pipeline.
-   Topic Classifier trong Knowledge Processing phải hoạt động chính xác để đảm bảo metadata `topics` đáng tin cậy.