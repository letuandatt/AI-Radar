# Decision: No Chunking Strategy (One Knowledge Object = One Vector)

## Decision
AI-Radar áp dụng chiến lược **"No Chunking"** đối với dữ liệu đã qua xử lý. Mỗi **Knowledge Object** (đã được tóm tắt và trích xuất ý chính) sẽ được embedding thành **một Vector duy nhất**.

## Context
Trong các hệ thống RAG truyền thống, người ta thường chia nhỏ văn bản gốc (Raw Article) thành các chunk nhỏ (ví dụ: 500 tokens) để nhúng vào vector database. Tuy nhiên, AI-Radar có cách tiếp cận khác: chúng ta không lưu bài gốc mà lưu tri thức đã được chuẩn hóa.

## Why This Decision?
1.  **Preserve Semantic Integrity:** Một Knowledge Object đại diện cho một ý tưởng hoặc một mảnh tri thức hoàn chỉnh (gồm Title, Summary, Key Takeaways). Việc chia nhỏ nó ra sẽ phá vỡ sự liên kết ngữ cảnh giữa "Vấn đề" và "Giải pháp" hoặc giữa "Tiêu đề" và "Nội dung".
2.  **Optimized Length:** Vì `summary` và `key_takeaways` đã được LLM rút gọn, độ dài của chúng thường nằm trong khoảng phù hợp cho một lần embedding duy nhất (dưới 1000 tokens). Không cần thiết phải chia nhỏ.
3.  **Simpler Retrieval:** Khi truy vấn, hệ thống sẽ trả về đúng "mảnh tri thức" cần thiết thay vì một đoạn văn bản cụt lủn thiếu đầu đuôi. Người dùng (hoặc LLM) sẽ nhận được bức tranh tổng thể của mảnh tri thức đó ngay lập tức.
4.  **Efficiency:** Giảm số lượng vector cần lưu trữ và quản lý trong Qdrant, giúp quá trình indexing và searching nhanh hơn.

## Why Not Alternatives?
-   **Not Fixed-size Chunking:** Chia cố định theo số ký tự/tokens sẽ cắt ngang câu hoặc ngắt mạch logic của bản tóm tắt, làm giảm chất lượng ngữ nghĩa của vector.
-   **Not Recursive Character Splitting:** Kỹ thuật này phức tạp và không cần thiết khi đầu vào đã là văn bản ngắn gọn, có cấu trúc rõ ràng do AI sinh ra.

## Impact
-   Quy trình Embedding sẽ nhận toàn bộ trường `summary` + `key_takeaways` + `title` của Knowledge Object để tạo ra một vector duy nhất.
-   Khi Retrieval, Top-K sẽ trả về K Knowledge Objects nguyên vẹn.
-   Prompt Engineering sẽ đóng vai trò quan trọng hơn trong việc hướng dẫn LLM cách sử dụng thông tin từ các Knowledge Objects này.