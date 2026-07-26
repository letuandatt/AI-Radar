# Decision: Adopt Naive RAG Strategy

## Decision
AI-Radar áp dụng chiến lược **Naive RAG** (Dense Retrieval + Top-K Search + Metadata Filtering) thay vì các biến thể RAG phức tạp như GraphRAG, Agentic RAG hay Hybrid Search.

## Context
Nhiều hệ thống RAG hiện đại thường cố gắng tích hợp thêm các bước như Query Rewriting, Multi-hop Retrieval, hoặc xây dựng Knowledge Graph để tăng độ chính xác. Tuy nhiên, những kỹ thuật này làm tăng đáng kể độ phức tạp, chi phí token và độ trễ hệ thống.

## Why This Decision?
1.  **Knowledge-Centric Design:** Vì AI-Radar đã chuẩn hóa dữ liệu thành **Knowledge Object** (tóm tắt, ý chính, metadata rõ ràng) trước khi lưu vào Vector DB, nên chất lượng ngữ nghĩa của mỗi vector đã rất cao. Naive RAG đủ sức tìm ra đúng mảnh tri thức cần thiết mà không cần các bước trung gian phức tạp.
2.  **Simplicity Wins:** Naive RAG dễ hiểu, dễ debug và dễ bảo trì. Nó tuân thủ tuyệt đối nguyên tắc "Simplicity First" của dự án.
3.  **Performance:** Chỉ cần một lần Embedding Query và một lần Vector Search, hệ thống có thể trả về kết quả trong vài trăm mili giây, đảm bảo trải nghiệm chatbot mượt mà.
4.  **Metadata Filtering:** Kết hợp với Metadata Filtering (lọc theo Topic, Date, Importance Score), Naive RAG đạt độ chính xác rất cao mà không cần đến Keyword Search (Hybrid) hay Graph traversal.

## Why Not Alternatives?
-   **Not GraphRAG:** Xây dựng và duy trì Knowledge Graph tốn kém tài nguyên và phức tạp. Với phạm vi cá nhân, lợi ích mang lại chưa xứng đáng với chi phí đầu tư.
-   **Not Agentic RAG:** Việc để Agent tự quyết định công cụ nào cần dùng sẽ gây ra độ trễ không đoán trước được và khó kiểm soát lỗi. AI-Radar ưu tiên luồng xử lý tuyến tính, ổn định.
-   **Not Hybrid Search:** Vì chúng ta không lưu bài gốc (Raw Article) nên Keyword Search trên nội dung đầy đủ là không khả thi. Metadata Filtering đã đóng vai trò bổ sung ngữ cảnh hiệu quả hơn.

## Impact
-   Module `vectorstores/retriever.py` chỉ thực hiện Semantic Search và lọc Metadata.
-   Không cần triển khai các module phức tạp như Query Decomposer hay Graph Builder.
-   Chất lượng câu trả lời phụ thuộc chủ yếu vào chất lượng của **Knowledge Object** và **Prompt Engineering**.