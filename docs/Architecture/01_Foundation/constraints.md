# Constraints

## Mục đích

Tài liệu này xác định các ràng buộc (Constraints) và giới hạn của kiến trúc AI-Radar. Khác với Design Philosophy (tư duy thiết kế) hay Architectural Principles (nguyên tắc chi phối cấu trúc), Constraints là những yếu tố bắt buộc hoặc giới hạn cứng mà hệ thống không được vi phạm trong quá trình hiện thực hóa.

Việc xác định rõ các ràng buộc giúp đảm bảo tính nhất quán giữa Architecture, Folder Structure và Implementation, đồng thời tránh việc mở rộng hệ thống vượt quá phạm vi đã thống nhất.

## Ràng buộc về Công nghệ (Technology Constraints)

Kiến trúc AI-Radar bị ràng buộc bởi các lựa chọn công nghệ đã được xác định trong Software Design Document (SDD). Mọi thành phần kiến trúc phải tương thích với stack này.

| Thành phần | Công nghệ bắt buộc | Ghi chú kiến trúc |
|---|---|---|
| **Ngôn ngữ** | Python 3.10+ | Toàn bộ Business Logic và Integration phải viết bằng Python. |
| **LLM Provider** | Groq API | Kiến trúc phải hỗ trợ gọi API qua HTTP/HTTPS. Không sử dụng Local LLM trong phiên bản đầu tiên. |
| **Vector Database** | Qdrant | Kiến trúc lưu trữ vector phải tuân thủ giao thức của Qdrant. Không sử dụng Pinecone hay Milvus. |
| **Notification Channel** | Zalo Official Account | Kiến trúc tích hợp phải hỗ trợ Webhook và REST API của Zalo. |
| **Containerization** | Docker | Hệ thống phải được đóng gói và triển khai dưới dạng Docker Container. |
| **Scheduler** | GitHub Actions / Cron | Pipeline Update không chạy liên tục mà chỉ kích hoạt theo lịch. |

## Ràng buộc về Kiến trúc (Architectural Constraints)

### 1. Monolithic Architecture
AI-Radar được thiết kế dưới dạng một ứng dụng đơn thể (Monolith) chạy trong một container duy nhất.
- **Ràng buộc:** Không phân tách thành Microservices.
- **Tác động:** Các module (`fetchers`, `knowledge`, `services`) giao tiếp trực tiếp thông qua function calls trong cùng một process, không sử dụng Message Queue (như Kafka/RabbitMQ) hay gRPC giữa các service.

### 2. Dual Pipeline Separation
Hệ thống bắt buộc phải duy trì sự tách biệt hoàn toàn giữa hai pipeline:
- **Knowledge Update Pipeline:** Chạy batch theo lịch.
- **Question Answering Pipeline:** Chạy interactive theo request.
- **Ràng buộc:** Hai pipeline không được chia sẻ trạng thái runtime (runtime state). Chúng chỉ chia sẻ chung Knowledge Base (Qdrant). Pipeline QA tuyệt đối không thực hiện crawl hay embedding.

### 3. Knowledge-Centric Storage
- **Ràng buộc:** Qdrant chỉ lưu trữ **Knowledge Object** (đã được chuẩn hóa, tóm tắt, trích xuất metadata).
- **Giới hạn:** Không lưu Raw Article (HTML/Markdown gốc) vào Vector Database.
- **Tác động:** Kiến trúc phải đảm bảo quy trình `Raw Article -> Knowledge Object` hoàn tất trước khi dữ liệu chạm đến tầng Storage.

### 4. Layered Dependency
Kiến trúc phải tuân thủ nghiêm ngặt quy tắc phụ thuộc một chiều đã định nghĩa trong Folder Structure:
`Pipelines` $\rightarrow$ `Services` $\rightarrow$ `Core Modules` (`Knowledge`, `Fetchers`, `Integrations`).
- **Ràng buộc:** Cấm phụ thuộc ngược (ví dụ: `Fetchers` không được gọi `Services`).

## Ràng buộc về Vận hành (Operational Constraints)

### 1. Stateless Application
Ứng dụng AI-Radar phải được thiết kế ở dạng không trạng thái (Stateless) đối với logic nghiệp vụ.
- **Ràng buộc:** Mọi trạng thái cần lưu trữ lâu dài (History, Cache) phải được đẩy ra ngoài vào `storage/` hoặc Qdrant.
- **Tác động:** Cho phép restart application mà không làm mất dữ liệu tri thức.

### 2. Scheduled Execution
- **Ràng buộc:** Hệ thống không chạy daemon liên tục để chờ dữ liệu mới.
- **Tác động:** Kiến trúc phải hỗ trợ khởi động nhanh (Fast Startup) vì mỗi lần Scheduler kích hoạt, container sẽ start, chạy pipeline và sau đó có thể stop.

### 3. No User Management
- **Ràng buộc:** Hệ thống không có database người dùng, không có authentication/authorization phức tạp.
- **Tác động:** Kiến trúc bảo mật chỉ tập trung vào bảo vệ API Keys và Webhook Secret, không cần xây dựng module quản lý session hay role-based access control (RBAC).

## Ràng buộc về Phạm vi (Scope Constraints)

Các chức năng sau bị loại trừ khỏi kiến trúc hiện tại và không được phép thiết kế chỗ trống (placeholder) cho chúng nếu chưa có yêu cầu thay đổi chính thức:
- **GraphRAG:** Không xây dựng Knowledge Graph.
- **Multi-Agent:** Không sử dụng mô hình Agent tự chủ.
- **Web Dashboard:** Không có giao diện người dùng web.
- **Real-time Streaming:** Không xử lý dữ liệu stream (chỉ batch processing).

## Kết luận

Các ràng buộc trên tạo nên "khung xương" cứng cho kiến trúc AI-Radar. Mọi quyết định thiết kế chi tiết trong các View tiếp theo (Structure, Runtime, Operations) đều phải nằm gọn trong các giới hạn này. Việc tuân thủ các constraints giúp hệ thống giữ được sự đơn giản, dễ bảo trì và tập trung vào giá trị cốt lõi là Knowledge Intelligence.