# Architectural Principles

Các nguyên tắc kiến trúc (Architectural Principles) của AI-Radar được rút ra trực tiếp từ Software Design Document (SDD), Chương 6.2. Khác với Design Philosophy (tập trung vào tư duy thiết kế), các nguyên tắc kiến trúc này chi phối trực tiếp cách tổ chức package, luồng dữ liệu runtime và quan hệ phụ thuộc giữa các thành phần trong hệ thống.

Mọi quyết định về cấu trúc module, data flow và integration trong tài liệu Architecture đều phải tuân thủ tuyệt đối 6 nguyên tắc sau.

## Principle 1 — Knowledge First

Tri thức (Knowledge Object) là tài sản trung tâm và là "Single Source of Truth" của toàn bộ hệ thống.

**Ý nghĩa kiến trúc:**
- Mọi module trong hệ thống đều xoay quanh việc xây dựng, lưu trữ hoặc khai thác Knowledge Object.
- Không có module nào được phép thao tác trực tiếp với Raw Article sau khi Knowledge Object đã được tạo thành công.
- Kiến trúc được chia thành hai pipeline độc lập (Update và Query) nhưng cùng chia sẻ một Knowledge Base duy nhất trên Qdrant.

**Tác động đến cấu trúc:**
- Module `knowledge/` chịu trách nhiệm duy nhất trong việc chuyển đổi Raw Article sang Knowledge Object.
- Module `vectorstores/` chỉ lưu trữ embedding và metadata của Knowledge Object, không lưu nội dung bài báo gốc.

## Principle 2 — Separation of Responsibility

Mỗi module chỉ đảm nhận một trách nhiệm duy nhất và rõ ràng. Không tồn tại "God Service" hay module đa năng.

**Ý nghĩa kiến trúc:**
- Hệ thống được phân rã thành các layer chuyên biệt: Acquisition, Processing, Storage, Consumption.
- Việc tách biệt trách nhiệm giúp giảm coupling, dễ dàng kiểm thử unit test cho từng thành phần và dễ dàng thay thế một module mà không ảnh hưởng đến toàn bộ hệ thống.

**Tác động đến cấu trúc:**
- `fetchers/` chỉ lấy dữ liệu, không xử lý logic.
- `knowledge/` chỉ xử lý tri thức, không lưu trữ.
- `integrations/` chỉ giao tiếp với bên ngoài, không chứa business logic.
- `services/` đóng vai trò orchestration, điều phối các module khác.

## Principle 3 — Pipeline-based Processing

Toàn bộ hệ thống hoạt động dựa trên các pipeline độc lập thay vì một luồng xử lý tuần tự duy nhất.

**Ý nghĩa kiến trúc:**
- AI-Radar sử dụng Dual Pipeline Architecture:
  - **Knowledge Update Pipeline:** Chạy theo lịch (Scheduler), chịu trách nhiệm thu thập và chuẩn hóa tri thức.
  - **Question Answering Pipeline:** Chạy interactive khi có user request, chịu trách nhiệm truy xuất và trả lời.
- Hai pipeline này hoàn toàn tách biệt về vòng đời xử lý nhưng dùng chung Knowledge Base.

**Tác động đến runtime:**
- Pipeline Update không bị chặn bởi các truy vấn của người dùng.
- Pipeline Query có độ trễ thấp vì không phải thực hiện crawl hay embedding trong thời gian thực.

## Principle 4 — Asynchronous by Default

Các tác vụ I/O và network-bound được thực hiện bất đồng bộ để tối ưu hiệu năng.

**Ý nghĩa kiến trúc:**
- Các thao tác như HTTP Request, RSS Fetching, API Calls (GitHub, HuggingFace) đều được xử lý async.
- Giúp giảm tổng thời gian hoàn thành của Knowledge Update Pipeline khi thu thập từ nhiều nguồn cùng lúc.

**Tác động đến implementation:**
- Sử dụng `asyncio` và `aiohttp` trong các fetcher và integrations.
- Scheduler được thiết kế để kích hoạt các coroutine thay vì blocking threads.

## Principle 5 — Replaceable Infrastructure

Các thành phần hạ tầng (Infrastructure) được trừu tượng hóa thông qua interface hoặc adapter pattern.

**Ý nghĩa kiến trúc:**
- Business Logic không phụ thuộc trực tiếp vào một nhà cung cấp cụ thể.
- Cho phép thay đổi Vector Database, LLM Provider hoặc Notification Channel mà không cần sửa đổi core logic.

**Tác động đến cấu trúc:**
- `vectorstores/` đóng vai trò là abstraction layer cho Qdrant.
- `integrations/groq/` và `integrations/zalo/` được tách riêng khỏi `services/`.
- Prompt templates được quản lý tập trung trong `config/prompts.py` để dễ dàng tinh chỉnh mà không cần deploy lại code logic.

## Principle 6 — Knowledge Reuse

Một Knowledge Object chỉ được sinh ra đúng một lần và được tái sử dụng cho nhiều mục đích khác nhau.

**Ý nghĩa kiến trúc:**
- Tránh việc gọi LLM nhiều lần cho cùng một nội dung.
- Tối ưu chi phí vận hành và giảm độ trễ hệ thống.

**Tác động đến data flow:**
- Knowledge Object sau khi được tạo sẽ phục vụ đồng thời cho:
  - Daily Digest Generation.
  - Semantic Retrieval (RAG).
  - Future Analytics (nếu mở rộng).
- Không có quy trình riêng biệt để tạo summary cho Digest và summary cho RAG; cả hai đều dùng chung `summary` field trong Knowledge Object.