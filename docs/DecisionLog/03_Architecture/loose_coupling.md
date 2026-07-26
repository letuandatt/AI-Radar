# Decision: Loose Coupling via Interface & Abstraction

## Decision
Các module trong AI-Radar được thiết kế với độ **Loose Coupling** (liên kết lỏng lẻo) cao nhất có thể. Các thành phần hạ tầng (LLM, Vector DB, Notification) được trừu tượng hóa thông qua các lớp adapter hoặc interface.

## Context
Công nghệ AI và hạ tầng cloud thay đổi rất nhanh. Hôm nay chúng ta dùng Groq, ngày mai có thể OpenRouter rẻ hơn. Hôm nay dùng Qdrant, ngày mai có thể cần chuyển sang Pinecone. Nếu code business logic phụ thuộc chặt chẽ vào thư viện cụ thể của các provider này, việc thay đổi sẽ cực kỳ đau đớn.

## Why This Decision?
1.  **Replaceable Infrastructure:** Cho phép thay đổi LLM Provider hoặc Vector Database chỉ bằng cách thay đổi cấu hình và một vài file adapter, không cần sửa đổi core logic.
2.  **Ease of Testing:** Dễ dàng mock các dịch vụ bên ngoài (Groq, Qdrant) khi viết Unit Test cho business logic.
3.  **Focus on Business Value:** Developer tập trung vào logic xử lý tri thức (Knowledge Processing) thay vì lo lắng về chi tiết kỹ thuật của API bên thứ ba.

## Why Not Alternatives?
-   **Not Tight Coupling:** Việc gọi trực tiếp `groq.Client()` hoặc `qdrant.QdrantClient()` rải rác khắp nơi trong code sẽ khiến hệ thống bị "khóa cứng" vào các công nghệ này, vi phạm nguyên tắc Extensibility.

## Impact
-   Sử dụng các module như `integrations/groq/` và `vectorstores/qdrant.py` làm lớp đệm.
-   Business Logic (`services/`) chỉ giao tiếp với các interface hoặc wrapper này, không bao giờ import trực tiếp thư viện gốc của provider nếu không cần thiết.
-   Cấu hình (API Key, Endpoint) được tập trung hóa trong `config/`.