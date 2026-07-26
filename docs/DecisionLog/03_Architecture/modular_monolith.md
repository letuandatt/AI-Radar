# Decision: Modular Monolith Architecture

## Decision
AI-Radar được thiết kế dưới dạng **Modular Monolith** thay vì Microservices hoặc Distributed System. Toàn bộ hệ thống chạy trong một process duy nhất (hoặc một Docker container) nhưng được tổ chức thành các module độc lập về mặt logic.

## Context
Dự án là một Knowledge Intelligence System cá nhân với quy mô vừa phải, không yêu cầu khả năng chịu tải đồng thời cực cao (high concurrency) hay tính sẵn sàng 99.99% (High Availability). Việc triển khai nhiều service riêng biệt sẽ làm tăng đáng kể độ phức tạp trong vận hành (DevOps), chi phí hạ tầng và khó khăn trong việc debug.

## Why This Decision?
1.  **Simplicity Wins:** Một monolith dễ dàng deploy, monitor và debug hơn rất nhiều so với một cụm microservices. Chỉ cần quản lý một Docker container và một vài biến môi trường.
2.  **Performance:** Giao tiếp giữa các module thông qua function calls trong cùng một process nhanh hơn và ổn định hơn so với giao tiếp qua network (gRPC/HTTP) giữa các service.
3.  **Atomic Transactions:** Dễ dàng đảm bảo tính nhất quán dữ liệu khi cập nhật Knowledge Base vì mọi thao tác đều nằm trong cùng một ngữ cảnh thực thi.
4.  **Phù hợp với quy mô:** Với lượng dữ liệu thu thập hàng ngày ở mức cá nhân/nhóm nhỏ, một máy chủ đơn lẻ hoàn toàn đủ sức xử lý cả hai Pipeline (Update và QA).

## Why Not Alternatives?
-   **Not Microservices:** Microservices phù hợp khi có nhiều đội ngũ phát triển lớn, cần deploy độc từng phần và chịu tải cực lớn. Với AI-Radar, nó sẽ dẫn đến "Over-engineering" và lãng phí tài nguyên.
-   **Not Serverless Functions:** Mặc dù serverless giúp giảm chi phí vận hành, nhưng việc quản lý state (trạng thái) của Pipeline dài (như crawling nhiều nguồn) và kết nối persistent tới Qdrant sẽ phức tạp hơn trên nền tảng serverless thuần túy.

## Impact
-   Toàn bộ code (`fetchers`, `knowledge`, `services`, v.v.) nằm chung trong một repository và một ứng dụng Python.
-   Cần tuân thủ nghiêm ngặt quy tắc phụ thuộc (Dependency Rules) giữa các module để tránh tạo ra "Big Ball of Mud".
-   Việc mở rộng sau này vẫn có thể tách một module nặng (ví dụ: Embedding) ra thành service riêng nếu cần, nhờ kiến trúc Modular.