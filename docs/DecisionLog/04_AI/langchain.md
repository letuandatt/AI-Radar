# Decision: Use LangChain as AI Framework

## Decision
Hệ thống sử dụng **LangChain** làm framework chính để trừu tượng hóa việc tương tác với LLM và xây dựng các chuỗi xử lý (Chains).

## Context
Việc gọi trực tiếp API của các LLM Provider (như Groq) thường đòi hỏi phải tự quản lý nhiều chi tiết kỹ thuật như: xử lý prompt template, parsing response, retry logic, và tích hợp với các công cụ khác (như Vector Stores). Viết code thuần (raw code) cho từng tác vụ nhỏ sẽ dẫn đến sự trùng lặp và khó bảo trì khi cần thay đổi provider hoặc nâng cấp logic.

## Why This Decision?
1.  **Standardization:** LangChain cung cấp một interface chuẩn hóa (`BaseChatModel`, `BaseRetriever`) giúp code business logic không bị phụ thuộc chặt chẽ vào implementation cụ thể của Groq hay Qdrant.
2.  **Prompt Management:** Hỗ trợ mạnh mẽ trong việc quản lý và lắp ráp Prompt Templates, giúp tách biệt rõ ràng giữa logic code và nội dung prompt.
3.  **Ecosystem & Integrations:** Dễ dàng tích hợp với Qdrant, Embedding Models và các công cụ khác thông qua các module có sẵn, giảm thời gian phát triển.
4.  **Future-Proofing:** Nếu cần chuyển sang một LLM Provider khác (ví dụ: OpenRouter), chỉ cần thay đổi phần khởi tạo model trong LangChain mà không cần sửa đổi toàn bộ luồng xử lý.

## Why Not Alternatives?
-   **Not Raw HTTP Requests:** Mặc dù nhẹ hơn, nhưng việc tự viết wrapper cho mọi thao tác AI sẽ tốn nhiều công sức bảo trì và dễ phát sinh lỗi khi API thay đổi.
-   **Not LlamaIndex:** LlamaIndex tối ưu cho việc xây dựng Index từ dữ liệu thô. Tuy nhiên, AI-Radar đã có quy trình xử lý tri thức riêng (`knowledge/` module) và chỉ cần LangChain cho việc gọi LLM và kết nối với Vector Store đã có sẵn. LangChain linh hoạt hơn cho các tác vụ điều phối pipeline đa dạng.

## Impact
-   Dependency `langchain` và `langchain-groq` được thêm vào dự án.
-   Các module trong `integrations/groq/` và `services/` sẽ sử dụng các class của LangChain để thực hiện gọi API.
-   Cần đảm bảo phiên bản LangChain ổn định để tránh các breaking changes thường gặp ở framework này.