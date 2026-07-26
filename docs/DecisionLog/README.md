# AI-Radar Decision Log

## Tổng quan
Decision Log là bộ tài liệu ghi lại các quyết định thiết kế, kiến trúc và công nghệ quan trọng của hệ thống AI-Radar. 

Khác với **Software Design Document (SDD)** mô tả "cái gì cần xây dựng" (What) hay **Architecture** mô tả "hệ thống được tổ chức như thế nào" (How), Decision Log tập trung giải thích **"Tại sao"** (Why) đằng sau mỗi lựa chọn.

Mục tiêu của Decision Log là cung cấp ngữ cảnh đầy đủ về các Trade-off đã được cân nhắc, giúp đội ngũ phát triển hiểu rõ tư duy thiết kế ban đầu và tránh việc phải đánh giá lại các phương án đã bị loại bỏ một cách không cần thiết.

## Mối quan hệ với các tài liệu khác
- **SDD (Source of Truth):** Chứa các yêu cầu và thiết kế hệ thống. Decision Log giải thích lý do chọn các thiết kế đó.
- **Architecture:** Mô tả cấu trúc runtime và dependency. Decision Log giải thích tại sao kiến trúc lại được chia thành các View và Module như hiện tại.
- **Code:** Hiện thực hóa các quyết định. Decision Log giúp developer hiểu ý đồ đằng sau đoạn code họ đang đọc hoặc sửa đổi.

> **Lưu ý:** Decision Log không thay thế SDD hay Architecture. Nó bổ sung góc nhìn về quá trình ra quyết định (Decision Making Process).

## Cấu trúc tài liệu
Decision Log được tổ chức theo các nhóm chủ đề (Knowledge Domains) để dễ dàng tra cứu:

| Nhóm | Nội dung chính |
|------|----------------|
| **01_Introduction** | Mục đích của Decision Log và hướng dẫn cách đọc. |
| **02_System** | Các quyết định nền tảng về mục tiêu, phạm vi và mô hình dữ liệu cốt lõi (Knowledge Object). |
| **03_Architecture** | Các quyết định về kiến trúc phần mềm (Monolith, Layered, Dual Pipeline). |
| **04_AI** | Các quyết định về AI Framework, LLM Provider và chiến lược RAG. |
| **05_Knowledge** | Các quyết định về Vector Database, Embedding Model và chiến lược xử lý dữ liệu tri thức. |
| **06_Infrastructure** | Các quyết định về hạ tầng, triển khai (Docker, Scheduler) và tích hợp kênh phân phối (Zalo). |
| **07_Development** | Các quy tắc và nguyên tắc phát triển phần mềm (Documentation First, Architecture Before Code). |
| **08_Decision_Map** | Sơ đồ phụ thuộc giữa các quyết định và chỉ mục tra cứu nhanh. |

## Cách sử dụng
1. **Đọc từ đầu nếu mới bắt đầu:** Bắt đầu từ `01_Introduction` và `02_System` để nắm vững tư tưởng cốt lõi trước khi đi vào chi tiết kỹ thuật.
2. **Tra cứu theo chủ đề:** Nếu đang làm việc với một module cụ thể (ví dụ: `vectorstores/`), hãy đọc nhóm `05_Knowledge` để hiểu lý do chọn Qdrant và chiến lược Embedding.
3. **Đánh giá thay đổi:** Khi muốn thay đổi một công nghệ hoặc kiến trúc, hãy đọc phần "Why Not Alternatives" trong Decision Log tương ứng để xem xét lại các Trade-off đã được phân tích trước đó.

## Nguyên tắc cập nhật
- Mọi quyết định thiết kế mới hoặc thay đổi công nghệ đều phải được ghi nhận vào Decision Log trước khi triển khai code.
- Decision Log phải luôn nhất quán với SDD và Architecture.
- Tập trung vào việc giải thích "Why" và "Why not", không mô tả chi tiết implementation.
