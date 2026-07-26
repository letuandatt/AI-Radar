# Decision: Use Qdrant as Vector Database

## Decision
Hệ thống sử dụng **Qdrant** làm Vector Database chính để lưu trữ Knowledge Base thay vì các giải pháp khác như Pinecone, Milvus hay Chroma.

## Context
Vector Database là thành phần cốt lõi của kiến trúc RAG, chịu trách nhiệm lưu trữ Embedding Vector và Metadata của Knowledge Object. Việc lựa chọn công cụ này cần cân bằng giữa hiệu năng tìm kiếm ngữ nghĩa (Semantic Search), khả năng lọc metadata, chi phí vận hành và độ phức tạp khi triển khai.

## Why This Decision?
1.  **Metadata Filtering:** Qdrant hỗ trợ mạnh mẽ việc lọc kết quả tìm kiếm dựa trên Payload (Metadata). Điều này cực kỳ quan trọng với AI-Radar vì chúng ta cần lọc theo `topics`, `published_at` hoặc `importance_score` trước khi trả về context cho LLM.
2.  **Performance & Efficiency:** Qdrant được viết bằng Rust, mang lại hiệu năng cao và tiêu thụ tài nguyên thấp hơn so với các giải pháp Java-based (như Milvus) hoặc Python-based (như Chroma ở quy mô lớn).
3.  **Ease of Deployment:** Qdrant có Docker Image chính chủ rất nhẹ và dễ dàng tích hợp vào `docker-compose.yml` của dự án cá nhân. Không yêu cầu cấu hình cluster phức tạp ngay từ đầu.
4.  **LangChain Integration:** Hỗ trợ tích hợp sẵn với LangChain, giúp việc trừu tượng hóa tầng lưu trữ trở nên đơn giản và tuân thủ nguyên tắc Replaceable Infrastructure.
5.  **Open Source & Self-Hosted:** Cho phép kiểm soát hoàn toàn dữ liệu tri thức mà không phụ thuộc vào dịch vụ Cloud trả phí ngay từ đầu.

## Why Not Alternatives?
-   **Not Pinecone:** Mặc dù dễ sử dụng và managed service tốt, nhưng Pinecone là dịch vụ trả phí và khó tự host. Với mục tiêu cá nhân và nguyên tắc Simplicity, việc tự quản lý một container Qdrant là đủ và tiết kiệm hơn.
-   **Not Chroma:** Chroma phù hợp cho prototyping nhanh nhưng thường gặp vấn đề về hiệu năng và ổn định khi dữ liệu tăng lên hoặc khi cần lọc metadata phức tạp. Qdrant chuyên nghiệp hơn cho production-ready dù vẫn đơn giản.
-   **Not Milvus:** Milvus quá nặng nề và phức tạp cho một dự án cá nhân. Nó yêu cầu nhiều thành phần phụ trợ (Etcd, MinIO...) khiến việc deploy trở nên cồng kềnh.

## Impact
-   Module `vectorstores/qdrant.py` được xây dựng để đóng gói mọi tương tác với Qdrant Client.
-   Collection `knowledge_base` trong Qdrant sẽ lưu trữ Vector cùng với Payload chứa đầy đủ thông tin của Knowledge Object (title, summary, topics, url...).
-   Chiến lược Retrieval sẽ kết hợp Dense Retrieval (Vector Search) và Metadata Filtering (Payload Filter) để tối ưu độ chính xác.