# Appendix

---

# A.1 Mục đích

Appendix cung cấp các thông tin tham khảo bổ sung cho Software Design Document.

Các nội dung trong chương này không đưa ra quyết định thiết kế mới mà có vai trò:

- Tổng hợp các khái niệm quan trọng.
- Chuẩn hóa thuật ngữ.
- Làm rõ các từ viết tắt.
- Liên kết giữa các chương của tài liệu.

Appendix giúp người đọc dễ dàng tra cứu trong quá trình phát triển và bảo trì dự án.

---

# A.2 Glossary

## AI-Radar

Hệ thống Knowledge Intelligence được xây dựng nhằm thu thập, xử lý, lưu trữ và khai thác tri thức trong lĩnh vực Trí tuệ nhân tạo.

---

## Knowledge Object

Đơn vị tri thức chuẩn hóa của hệ thống.

Knowledge Object được tạo ra từ Raw Article sau quá trình Knowledge Processing và là dữ liệu duy nhất được lưu trữ trong Knowledge Base.

---

## Raw Article

Nội dung gốc được thu thập từ các nguồn bên ngoài trước khi trải qua quá trình xử lý.

Raw Article chỉ tồn tại trong Pipeline xử lý và không được sử dụng trực tiếp cho Retrieval.

---

## Knowledge Base

Kho tri thức trung tâm của hệ thống.

Knowledge Base lưu trữ toàn bộ Knowledge Object cùng Embedding tương ứng và là nguồn dữ liệu chung cho mọi chức năng khai thác tri thức.

---

## Daily Digest

Bản tổng hợp các thông tin AI quan trọng trong một khoảng thời gian xác định.

Daily Digest được tạo từ Knowledge Base và gửi tới người dùng thông qua kênh thông báo.

---

## Retrieval

Quá trình tìm kiếm các Knowledge Object phù hợp với câu hỏi của người dùng dựa trên Embedding và Metadata.

---

## Embedding

Biểu diễn dữ liệu dưới dạng vector để phục vụ Semantic Search.

---

## Vector Database

Hệ quản trị cơ sở dữ liệu chuyên lưu trữ Embedding và hỗ trợ tìm kiếm theo độ tương đồng ngữ nghĩa.

Trong AI-Radar, Vector Database được hiện thực bằng Qdrant.

---

## Pipeline

Chuỗi các bước xử lý liên tiếp nhằm hoàn thành một nhiệm vụ cụ thể.

Ví dụ:

- Knowledge Update Pipeline.
- Question Answering Pipeline.

---

## Fetcher

Module chịu trách nhiệm thu thập dữ liệu từ các nguồn bên ngoài.

---

## Knowledge Processing

Quá trình chuyển đổi Raw Article thành Knowledge Object thông qua các bước làm sạch, chuẩn hóa và trích xuất tri thức.

---

## Retrieval-Augmented Generation (RAG)

Kỹ thuật kết hợp giữa Retrieval và Large Language Model nhằm tạo câu trả lời dựa trên Knowledge Base thay vì chỉ dựa trên kiến thức nội tại của mô hình.

---

# A.3 Abbreviations

| Viết tắt | Ý nghĩa |
|----------|----------|
| AI | Artificial Intelligence |
| API | Application Programming Interface |
| RAG | Retrieval-Augmented Generation |
| LLM | Large Language Model |
| RSS | Really Simple Syndication |
| HTTP | Hypertext Transfer Protocol |
| HTTPS | Hypertext Transfer Protocol Secure |
| JSON | JavaScript Object Notation |
| OA | Official Account |
| SRP | Single Responsibility Principle |

---

# A.4 Design Principles Summary

Trong toàn bộ Software Design Document, các nguyên tắc thiết kế sau được xem là nền tảng của AI-Radar:

- Goal First.
- Trade-off Thinking.
- Knowledge-Centric Architecture.
- Simplicity First.
- Separation of Concerns.
- Loose Coupling.
- Single Responsibility Principle.
- Extensibility.
- Documentation First.

Mọi quyết định thiết kế đều cần nhất quán với các nguyên tắc trên.

---

# A.5 Architecture Decisions Summary

Các quyết định kiến trúc đã được thống nhất trong Software Design Document bao gồm:

- AI-Radar là một Knowledge Intelligence System.
- Knowledge Object là Single Source of Truth.
- Daily Digest là chức năng ưu tiên cao nhất.
- Daily Digest và Question Answering sử dụng chung Knowledge Base.
- Áp dụng Knowledge-Centric Architecture.
- Áp dụng Dual Pipeline Architecture.
- Sử dụng Qdrant làm Vector Database.
- Sử dụng Groq làm LLM Provider.
- Áp dụng Dense Retrieval và Metadata Filtering.
- Không sử dụng GraphRAG hoặc Agentic RAG trong phiên bản đầu tiên.

Các quyết định này được xem là nền tảng của kiến trúc hiện tại và không thay đổi nếu không có đánh giá Trade-off phù hợp.

---

# A.6 Document Relationship

Các tài liệu của dự án có mối quan hệ như sau:

| Tài liệu | Vai trò |
|----------|----------|
| PROJECT_INDEX.md | Quản lý cấu trúc và lộ trình tài liệu |
| rules_me_and_AI.md | Quy tắc làm việc trong toàn bộ dự án |
| SDD_ONBOARDING.md | Quy trình onboarding trước khi tham gia dự án |
| Software Design Document | Nguồn thông tin thiết kế chính của hệ thống |
| Architecture.md | Hiện thực hóa kiến trúc dựa trên Software Design Document |
| DecisionLog.md | Ghi lại các quyết định kiến trúc và Trade-off |
| API.md | Mô tả các API của hệ thống |
| README.md | Hướng dẫn sử dụng và triển khai dự án |

Software Design Document là nguồn thông tin thiết kế chính (Source of Truth). Các tài liệu còn lại phải nhất quán với các quyết định được mô tả trong SDD.

---

# A.7 Document Evolution

Software Design Document là tài liệu sống (Living Document).

Khi có thay đổi về:

- Yêu cầu.
- Kiến trúc.
- Thiết kế.
- Module.
- Data Model.

Các nội dung liên quan trong SDD cần được cập nhật trước khi thay đổi mã nguồn.

Quy trình phát triển của AI-Radar luôn tuân theo nguyên tắc:

Requirement

↓

Software Design Document

↓

Architecture

↓

Decision Log

↓

Implementation

Điều này đảm bảo mã nguồn luôn phản ánh đúng thiết kế đã được thống nhất.

---

# A.8 Closing Statement

Software Design Document là nền tảng thiết kế của AI-Radar.

Toàn bộ các quyết định trong tài liệu này được xây dựng dựa trên mục tiêu phát triển một Knowledge Intelligence System đơn giản, dễ bảo trì và có khả năng mở rộng hợp lý.

Các chương trong tài liệu mô tả đầy đủ từ mục tiêu, phạm vi, kiến trúc, dữ liệu, module, yêu cầu phi chức năng cho đến định hướng phát triển trong tương lai.

Mọi thay đổi của dự án cần được đánh giá dựa trên các nguyên tắc thiết kế đã thống nhất và được cập nhật vào Software Design Document trước khi triển khai.

---