# Decision: Knowledge Object as Core Data Entity

## Decision
Hệ thống sử dụng **Knowledge Object** làm đơn vị dữ liệu trung tâm thay vì lưu trữ nguyên văn bài báo gốc (Raw Article).

## Context
Bài báo gốc thường chứa nhiều nhiễu (quảng cáo, điều hướng, mã nguồn dài dòng, văn phong phức tạp). Việc lưu trữ và truy xuất trực tiếp bài gốc làm giảm hiệu quả của Semantic Search và tăng chi phí token khi gọi LLM.

## Why This Decision?
1.  **Chuẩn hóa tri thức:** Mọi nguồn dữ liệu (RSS, GitHub, HF) đều được quy về một cấu trúc chung: `title`, `summary`, `key_takeaways`, `topics`, `keywords`.
2.  **Tối ưu Retrieval:** Vector Embedding được tạo từ `summary` và `key_takeaways` sẽ tập trung vào ý nghĩa cốt lõi, giúp tìm kiếm chính xác hơn so với embedding cả bài văn dài.
3.  **Tiết kiệm chi phí:** Khi xây dựng Prompt Context cho RAG hoặc Digest, hệ thống chỉ cần ghép các đoạn tóm tắt ngắn gọn thay vì toàn bộ nội dung bài báo.
4.  **Single Source of Truth:** Mọi module phía sau (Digest, RAG) đều làm việc trên cùng một phiên bản tri thức đã được chuẩn hóa.

## Why Not Alternatives?
-   **Not Raw Article Storage:** Lưu bài gốc tốn dung lượng, khó quản lý sự nhất quán về định dạng và khiến việc trích xuất thông tin cụ thể trở nên khó khăn hơn do nhiễu.
-   **Not Chunked Documents:** Thay vì chia nhỏ bài gốc thành các chunk rời rạc, chúng ta coi mỗi bài báo sau khi xử lý là một "mảnh tri thức" hoàn chỉnh (One Article = One Knowledge Object).

## Impact
-   Module `knowledge/` phải đảm nhiệm vai trò chuyển đổi mạnh mẽ từ Raw Article sang Knowledge Object.
-   Qdrant chỉ lưu trữ metadata và vector của Knowledge Object, không lưu content đầy đủ.
-   Vòng đời dữ liệu: Raw Article chỉ tồn tại tạm thời trong RAM, Knowledge Object tồn tại lâu dài trong Vector DB.