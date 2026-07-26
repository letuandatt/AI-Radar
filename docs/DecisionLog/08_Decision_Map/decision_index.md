# Decision Index

## Mục đích
Tài liệu này đóng vai trò là mục lục tra cứu nhanh (Quick Reference) cho toàn bộ bộ Decision Log. Nó giúp Developer hoặc Architect dễ dàng tìm thấy lý do đằng sau một quyết định cụ thể mà không cần đọc lại toàn bộ tài liệu.

## Danh sách quyết định theo nhóm

### 01_Introduction
| File | Quyết định chính |
| --- | --- |
| `purpose.md` | Decision Log ghi lại "Why" và "Why not" cho các lựa chọn thiết kế. |
| `how_to_read.md` | Đọc theo thứ tự nhóm để hiểu ngữ cảnh kế thừa. |

### 02_System
| File | Quyết định chính |
| --- | --- |
| `knowledge_intelligence.md` | AI-Radar là hệ thống thu thập tri thức chủ động, không phải Chatbot thụ động. |
| `daily_intelligence.md` | Daily Digest là tính năng cốt lõi số 1, hiện thực hóa khái niệm "Radar". |
| `knowledge_object.md` | Knowledge Object là đơn vị dữ liệu trung tâm, thay thế Raw Article. |
| `single_source_of_truth.md` | Qdrant chứa Knowledge Object là nguồn chân lý duy nhất cho cả Digest và RAG. |

### 03_Architecture
| File | Quyết định chính |
| --- | --- |
| `modular_monolith.md` | Chọn Monolith để đơn giản hóa deploy và debug cho quy mô cá nhân. |
| `layered_architecture.md` | Phân tầng rõ ràng: Acquisition $\rightarrow$ Processing $\rightarrow$ Storage $\rightarrow$ Consumption. |
| `loose_coupling.md` | Sử dụng Interface/Adapter để dễ dàng thay đổi hạ tầng (LLM, DB). |
| `dual_pipeline.md` | Tách biệt Pipeline Update (Scheduled) và Pipeline QA (Interactive). |

### 04_AI
| File | Quyết định chính |
| --- | --- |
| `langchain.md` | Dùng LangChain để chuẩn hóa việc gọi LLM và tích hợp Vector Store. |
| `groq.md` | Chọn Groq vì tốc độ inference cực nhanh và chi phí hợp lý. |
| `naive_rag.md` | Ưu tiên Naive RAG (Dense Retrieval + Metadata Filter) để giữ sự đơn giản. |
| `prompt_engineering.md` | Quản lý Prompt tập trung trong `config/prompts.py` để dễ tinh chỉnh. |

### 05_Knowledge
| File | Quyết định chính |
| --- | --- |
| `qdrant.md` | Chọn Qdrant vì hỗ trợ Metadata Filtering mạnh mẽ và dễ self-host. |
| `embedding_model.md` | Sử dụng Cohere Embedding Model cho chất lượng ngữ nghĩa cao. |
| `chunking.md` | Áp dụng chiến lược "No Chunking" (One Knowledge Object = One Vector). |
| `metadata.md` | Sử dụng Metadata Filtering (Topics, Date) để tăng độ chính xác Retrieval. |

### 06_Infrastructure
| File | Quyết định chính |
| --- | --- |
| `docker.md` | Đóng gói toàn bộ App và Qdrant trong Docker Compose để nhất quán môi trường. |
| `scheduler.md` | Dùng GitHub Actions Cron để kích hoạt Pipeline Update, giữ App Stateless. |
| `configuration.md` | Quản lý Secret và Config qua Environment Variables (`.env`). |
| `zalo_oa.md` | Chọn Zalo OA làm kênh giao tiếp chính do độ phổ biến tại Việt Nam. |

### 07_Development
| File | Quyết định chính |
| --- | --- |
| `documentation_first.md` | Tài liệu phải hoàn thiện trước khi viết code (Documentation-First). |
| `architecture_before_code.md` | Kiến trúc phải được phê duyệt trước khi bắt đầu Implementation. |

## Cách sử dụng Decision Index
1.  **Khi gặp lỗi thiết kế:** Tra cứu nhóm liên quan (ví dụ: lỗi Retrieval kém $\rightarrow$ xem nhóm `05_Knowledge`).
2.  **Khi muốn thay đổi công nghệ:** Kiểm tra `dependency_graph.md` để xem ảnh hưởng lan tỏa.
3.  **Khi onboarding thành viên mới:** Cung cấp file này để họ có cái nhìn tổng quan về các lựa chọn kỹ thuật của dự án.

## Kết luận
Decision Index là điểm bắt đầu cho mọi hoạt động bảo trì và mở rộng hệ thống. Nó đảm bảo rằng mọi thay đổi trong tương lai đều tôn trọng lịch sử thiết kế và các trade-off đã được cân nhắc kỹ lưỡng.