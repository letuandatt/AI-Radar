# Decision: Layered Architecture Pattern

## Decision
Hệ thống áp dụng mô hình **Layered Architecture** với 4 tầng chức năng rõ ràng:
1.  **Knowledge Acquisition** (Thu thập)
2.  **Knowledge Processing** (Xử lý)
3.  **Knowledge Storage** (Lưu trữ)
4.  **Knowledge Consumption** (Khai thác)

## Context
Để đảm bảo nguyên tắc "Separation of Responsibility", hệ thống cần được phân chia sao mỗi tầng chỉ làm một việc cụ thể. Điều này giúp code dễ đọc, dễ test và dễ thay thế một tầng mà không ảnh hưởng đến các tầng khác.

## Why This Decision?
1.  **Clarity:** Mỗi developer mới vào dự án đều có thể hiểu ngay luồng dữ liệu đi từ đâu (Acquisition) đến đâu (Consumption).
2.  **Maintainability:** Nếu muốn thay đổi cách lưu trữ (ví dụ: từ Qdrant sang Milvus), chỉ cần sửa ở tầng Storage, các tầng Acquisition và Processing không hề hay biết.
3.  **Testability:** Có thể viết Unit Test cho từng tầng một cách độc lập bằng cách mock các tầng bên dưới.

## Why Not Alternatives?
-   **Not Feature-based Packaging:** Tổ chức code theo tính năng (ví dụ: folder `daily_digest/` chứa cả fetcher, processor, sender) thường dẫn đến sự trùng lặp code và khó tái sử dụng các thành phần chung như `knowledge_processor`.
-   **Not Hexagonal/Clean Architecture (Strict):** Mặc dù AI-Radar có áp dụng một số nguyên tắc của Clean Arch (như Dependency Rule), nhưng việc áp dụng quá nhiều layer trừu tượng (Interface, Adapter, Port) sẽ làm tăng độ phức tạp không cần thiết cho một dự án cá nhân. Layered Architecture truyền thống đủ hiệu quả và dễ hiểu hơn.

## Impact
-   Cấu trúc thư mục `app/` được tổ chức theo các layer này (`fetchers/`, `knowledge/`, `vectorstores/`, `services/`).
-   Dữ liệu chỉ di chuyển một chiều từ tầng dưới lên tầng trên hoặc ngược lại theo quy định, không được phép nhảy cóc (ví dụ: Fetcher không được gọi trực tiếp Services).