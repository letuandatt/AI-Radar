# Decision: Architecture Before Code Implementation

## Decision
Việc thiết kế kiến trúc chi tiết (Architecture Design) phải hoàn tất và được phê duyệt trước khi bắt đầu giai đoạn Implementation (viết code). Kiến trúc đóng vai trò là bản vẽ kỹ thuật, còn code là quá trình thi công.

## Context
Nhiều developer có xu hướng nhảy thẳng vào viết code khi mới chỉ có ý tưởng sơ bộ hoặc SDD chung chung. Điều này dẫn đến việc cấu trúc thư mục lộn xộn, phụ thuộc chéo (circular dependency) và vi phạm các nguyên tắc thiết kế cốt lõi như Loose Coupling hay Separation of Responsibility.

## Why This Decision?
1.  **Structural Integrity:** Architecture xác định rõ ranh giới giữa các module, quy tắc phụ thuộc (Dependency Rules) và luồng dữ liệu (Data Flow). Nếu không có bản vẽ này, code rất dễ bị vi phạm các nguyên tắc nền tảng.
2.  **Mapping Consistency:** Kiến trúc đảm bảo rằng mỗi thành phần trong thiết kế đều có vị trí tương ứng rõ ràng trong cấu trúc thư mục (`Folder Structure`). Điều này giúp code dễ tìm, dễ hiểu và dễ kiểm thử.
3.  **Risk Mitigation:** Thiết kế kiến trúc giúp phát hiện sớm các rủi ro về hiệu năng, khả năng mở rộng hoặc tích hợp hạ tầng (ví dụ: cách Qdrant giao tiếp với App) trước khi bị khóa cứng bởi implementation.
4.  **Alignment with SDD:** Architecture là cầu nối biến các yêu cầu trừu tượng trong SDD thành các khối chức năng cụ thể. Bỏ qua bước này khiến việc hiện thực hóa SDD trở nên mơ hồ và thiếu chính xác.

## Why Not Alternatives?
-   **Not Evolving Architecture via Code:** Để kiến trúc tự hình thành qua quá trình viết code (Emergent Architecture) chỉ phù hợp với các dự án cực nhỏ hoặc prototype. Với AI-Radar – một hệ thống có cấu trúc Pipeline phức tạp và yêu cầu tái sử dụng tri thức cao – cách làm này sẽ dẫn đến sự hỗn loạn trong quản lý module.
-   **Not Parallel Design & Code:** Vừa viết architecture vừa viết code thường dẫn đến mâu thuẫn, vì tốc độ thay đổi của code nhanh hơn nhiều so với tốc độ cập nhật tài liệu, khiến tài liệu nhanh chóng bị lỗi thời.

## Impact
-   Giai đoạn Implementation chỉ được bắt đầu khi toàn bộ 4 Views của Architecture (Foundation, Structure, Runtime, Operations) đã hoàn thành.
-   Mọi thay đổi trong code liên quan đến cấu trúc module hoặc luồng dữ liệu đều phải được cập nhật ngược lại vào tài liệu Architecture trước.
-   Folder Structure được xem là một phần của Architecture Design, không được tự ý thay đổi tên thư mục hoặc di chuyển file nếu chưa có sự đồng thuận trong tài liệu.