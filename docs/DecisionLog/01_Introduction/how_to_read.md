# How to Read This Document

## Cấu trúc
Decision Log được tổ chức theo các nhóm chủ đề (Knowledge Domains) để dễ dàng tra cứu:
- **02_System:** Các quyết định nền tảng về mục tiêu và phạm vi.
- **03_Architecture:** Các quyết định về cấu trúc hệ thống và luồng dữ liệu.
- **04_AI:** Các quyết định về LLM, Framework và chiến lược RAG.
- **05_Knowledge:** Các quyết định về Vector Database, Embedding và mô hình tri thức.
- **06_Infrastructure:** Các quyết định về triển khai, cấu hình và tích hợp.
- **07_Development:** Các quy tắc phát triển phần mềm.

## Cách đọc hiệu quả
1. **Đọc theo thứ tự nếu mới bắt đầu:** Bắt đầu từ `02_System` để nắm vững tư tưởng cốt lõi trước khi đi vào chi tiết kỹ thuật.
2. **Tra cứu theo chủ đề nếu cần:** Nếu đang làm việc với module AI, hãy đọc nhóm `04_AI`.
3. **Tập trung vào "Why" và "Why Not":** Đừng chỉ đọc kết quả cuối cùng, hãy chú ý đến phần phân tích trade-off để hiểu sâu hơn về quyết định.

## Mối quan hệ với các tài liệu khác
- **SDD:** Là nguồn gốc của yêu cầu. Decision Log giải thích tại sao SDD lại được thiết kế như vậy.
- **Architecture:** Mô tả cách hệ thống hoạt động. Decision Log giải thích tại sao kiến trúc lại được tổ chức theo hướng đó.
- **Code:** Hiện thực hóa các quyết định. Decision Log giúp developer hiểu ý đồ đằng sau đoạn code họ đang đọc.