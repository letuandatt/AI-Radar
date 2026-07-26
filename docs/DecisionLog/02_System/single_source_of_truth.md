# Decision: Single Source of Truth for Knowledge

## Decision
**Knowledge Base (Qdrant)** chứa các **Knowledge Objects** được xác định là Nguồn chân lý duy nhất (Single Source of Truth) cho mọi hoạt động khai thác tri thức của hệ thống.

## Context
Hệ thống có hai nhu cầu khai thác tri thức khác nhau: gửi bản tin hàng ngày (Daily Digest) và trả lời câu hỏi người dùng (RAG). Việc duy trì hai nguồn dữ liệu riêng biệt hoặc xử lý lại dữ liệu thô cho từng mục đích sẽ dẫn đến mâu thuẫn thông tin và lãng phí tài nguyên.

## Why This Decision?
1.  **Nhất quán thông tin:** Bản tin hàng ngày và câu trả lời RAG đều dựa trên cùng một tập hợp tri thức đã được chuẩn hóa. Người dùng sẽ không thấy sự khác biệt giữa "tin tức hôm nay" và "kiến thức trong kho".
2.  **Tái sử dụng tối đa (Knowledge Reuse):** Một Knowledge Object chỉ được sinh ra đúng một lần (trong Update Pipeline) nhưng được sử dụng cho cả Digest và RAG. Điều này giảm thiểu số lần gọi LLM để tóm tắt lại cùng một nội dung.
3.  **Đơn giản hóa kiến trúc:** Không cần đồng bộ dữ liệu giữa các database khác nhau. Chỉ cần duy trì một Qdrant Collection chất lượng.

## Why Not Alternatives?
-   **Not Separate Stores for Digest and RAG:** Sẽ dẫn đến tình trạng "data silo", nơi bản tin có thể nói về một xu hướng nhưng RAG lại không tìm thấy thông tin đó do khác nguồn hoặc khác cách xử lý.
-   **Not Real-time Processing for Both:** Xử lý lại bài báo gốc mỗi khi gửi tin hoặc trả lời câu hỏi là cực kỳ chậm và tốn kém.

## Impact
-   Kiến trúc Dual Pipeline (Update & Query) phải chia sẻ chung tầng Storage (Qdrant).
-   Chất lượng của Knowledge Object trong Qdrant quyết định trực tiếp đến chất lượng của cả hai tính năng cốt lõi.
-   Không có module nào được phép bỏ qua bước tạo Knowledge Object để làm việc trực tiếp với Raw Article.