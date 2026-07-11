# Source Mapping

## Mục đích

Tài liệu này xác định ánh xạ (Mapping) giữa các thành phần kiến trúc (Architectural Components) của AI-Radar và cấu trúc mã nguồn (Source Code Structure) tương ứng. 

Khác với Module Responsibilities tập trung vào vai trò nghiệp vụ, Source Mapping trả lời câu hỏi: "Thành phần kiến trúc X nằm ở đâu trong thư mục `app/`?". Đây là cầu nối quan trọng giúp Developer dễ dàng định vị code khi làm việc với hệ thống.

Mọi ánh xạ trong tài liệu này đều tuân thủ tuyệt đối thiết kế trong `FolderStructure.md`.

## Nguyên tắc ánh xạ

1. **One-to-One hoặc One-to-Many:** Một thành phần kiến trúc có thể ánh xạ sang một hoặc nhiều file/thư mục trong source code.
2. **Không ánh xạ chéo:** Mỗi file trong `app/` chỉ thuộc về duy nhất một thành phần kiến trúc chính để tránh nhầm lẫn trách nhiệm.
3. **Phản ánh Layered Architecture:** Cấu trúc thư mục `app/` phản ánh đúng 4 tầng kiến trúc đã mô tả trong High-Level Architecture.

## Bảng ánh xạ chi tiết

Bảng dưới đây liệt kê toàn bộ các thành phần kiến trúc cốt lõi và vị trí tương ứng của chúng trong mã nguồn.

| Thành phần Kiến trúc (Architecture Component) | Vị trí Source Code (Source Location) | Trách nhiệm chính trong Code |
|---|---|---|
| **Configuration Manager** | `app/config/settings.py` | Load biến môi trường, quản lý API Keys, Scheduler config. |
| **Prompt Templates** | `app/config/prompts.py` | Lưu trữ các template string dùng cho LLM (Summary, RAG, Digest). |
| **Core Infrastructure** | `app/core/` | Logger, Exception Handler, Utils chung. |
| **Scheduler Interface** | `app/core/scheduler.py` | Định nghĩa interface và logic kích hoạt Pipeline định kỳ. |
| **Data Models** | `app/models/` | Định nghĩa Pydantic/Dataclass cho `RawArticle`, `KnowledgeObject`, v.v. |
| **RSS Fetcher** | `app/fetchers/rss.py` | Logic crawl và parse dữ liệu từ RSS Feeds. |
| **GitHub Fetcher** | `app/fetchers/github.py` | Logic gọi GitHub API để lấy trending repos. |
| **HuggingFace Fetcher** | `app/fetchers/huggingface.py` | Logic gọi HuggingFace API để lấy model/dataset mới. |
| **Knowledge Cleaner** | `app/knowledge/cleaner.py` | Loại bỏ HTML tags, ký tự đặc biệt, chuẩn hóa văn bản. |
| **Knowledge Summarizer** | `app/knowledge/summarize.py` | Gọi Groq API để tóm tắt nội dung bài viết. |
| **Topic Classifier** | `app/knowledge/topic_classifier.py` | Phân loại bài viết vào các chủ đề AI cố định. |
| **Keyword Extractor** | `app/knowledge/keyword_extractor.py` | Trích xuất các từ khóa kỹ thuật quan trọng. |
| **Qdrant Client** | `app/vectorstores/qdrant.py` | Wrapper cho Qdrant Client, xử lý kết nối và upsert. |
| **Semantic Retriever** | `app/vectorstores/retriever.py` | Thực hiện vector search và lọc metadata. |
| **Groq Integration** | `app/integrations/groq/client.py` | Gửi request đến Groq API và xử lý response. |
| **Zalo Integration** | `app/integrations/zalo/` | Xử lý Webhook, format tin nhắn và gửi qua Zalo OA API. |
| **Digest Service** | `app/services/digest_service.py` | Logic tổng hợp Daily Digest từ danh sách Knowledge Objects. |
| **RAG Service** | `app/services/rag_service.py` | Logic xây dựng context và sinh câu trả lời cho user question. |
| **Update Pipeline** | `app/pipelines/knowledge_update.py` | Điều phối luồng: Fetch $\rightarrow$ Process $\rightarrow$ Store. |
| **QA Pipeline** | `app/pipelines/question_answering.py` | Điều phối luồng: Receive Question $\rightarrow$ Retrieve $\rightarrow$ Answer. |
| **Entry Point** | `app/main.py` | Điểm khởi động ứng dụng, đăng ký scheduler và routes. |

## Ánh xạ theo tầng kiến trúc (Layer Mapping)

Để dễ hình dung hơn, dưới đây là cách các thư mục trong `app/` ánh xạ sang 4 tầng kiến trúc đã định nghĩa.

### Layer 1: Knowledge Acquisition
*   **Kiến trúc:** Tầng thu thập dữ liệu.
*   **Source Code:** `app/fetchers/`
*   **Chi tiết:** Chứa các class kế thừa từ `BaseFetcher`, mỗi file đại diện cho một nguồn dữ liệu cụ thể.

### Layer 2: Knowledge Processing
*   **Kiến trúc:** Tầng xử lý và chuẩn hóa tri thức.
*   **Source Code:** `app/knowledge/`
*   **Chi tiết:** Chứa các hàm/module độc lập thực hiện cleaning, summarizing, classification. Các module này nhận `RawArticle` và trả về `KnowledgeObject`.

### Layer 3: Knowledge Storage
*   **Kiến trúc:** Tầng lưu trữ ngữ nghĩa.
*   **Source Code:** `app/vectorstores/`, `app/storage/`
*   **Chi tiết:** 
    *   `vectorstores/`: Giao tiếp với Qdrant.
    *   `storage/`: Quản lý file JSON/SQLite cục bộ cho history/cache.

### Layer 4: Knowledge Consumption & Orchestration
*   **Kiến trúc:** Tầng điều phối và khai thác tri thức.
*   **Source Code:** `app/services/`, `app/pipelines/`, `app/integrations/`
*   **Chi tiết:**
    *   `services/`: Chứa business logic phức tạp (Digest, RAG).
    *   `pipelines/`: Kết nối các service và module lại thành một luồng hoàn chỉnh.
    *   `integrations/`: Cầu nối với Groq và Zalo.

## Ánh xạ Data Flow sang Code Execution

Khi một luồng dữ liệu chạy trong hệ thống, nó sẽ đi qua các file code theo trình tự sau:

**Luồng cập nhật tri thức (Update Flow):**
1.  `core/scheduler.py` kích hoạt job.
2.  `pipelines/knowledge_update.py` bắt đầu thực thi.
3.  Gọi `fetchers/rss.py` (và các fetcher khác) $\rightarrow$ Trả về `models/article.py`.
4.  Gọi `knowledge/cleaner.py` $\rightarrow$ `knowledge/summarize.py` $\rightarrow$ `knowledge/topic_classifier.py`.
5.  Tạo đối tượng `models/knowledge.py`.
6.  Gọi `vectorstores/qdrant.py` để upsert.
7.  Gọi `services/digest_service.py` nếu đến giờ gửi bản tin.
8.  Gọi `integrations/zalo/client.py` để gửi tin.

**Luồng truy vấn tri thức (Query Flow):**
1.  `integrations/zalo/webhook.py` nhận request từ Zalo.
2.  Chuyển payload sang `pipelines/question_answering.py`.
3.  Gọi `services/rag_service.py`.
4.  `rag_service` gọi `vectorstores/retriever.py` để lấy context.
5.  `rag_service` gọi `integrations/groq/client.py` để sinh answer.
6.  Trả kết quả về `integrations/zalo/client.py` để gửi lại user.

## Kết luận

Source Mapping đảm bảo rằng mọi khái niệm kiến trúc trừu tượng đều có một vị trí cụ thể, rõ ràng trong mã nguồn. Việc tuân thủ bảng ánh xạ này giúp đội ngũ phát triển dễ dàng trace code, debug lỗi và mở rộng hệ thống mà không bị lạc hướng trong cấu trúc dự án.