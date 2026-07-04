# 10. Non-Functional Requirements

---

# 10.1 Mục đích

Chương này mô tả các yêu cầu phi chức năng (Non-Functional Requirements) của AI-Radar.

Nếu các chương trước tập trung vào việc hệ thống **làm gì**, thì chương này tập trung vào việc hệ thống **phải hoạt động như thế nào**.

Các yêu cầu phi chức năng đóng vai trò là tiêu chí đánh giá chất lượng của hệ thống trong quá trình triển khai và vận hành.

Chúng không bổ sung chức năng mới mà định nghĩa các đặc tính mà toàn bộ hệ thống phải đáp ứng.

---

# 10.2 Triết lý thiết kế

Các yêu cầu phi chức năng của AI-Radar được xây dựng dựa trên triết lý:

- Đơn giản trước, tối ưu sau.
- Ưu tiên khả năng bảo trì hơn tối ưu cực hạn.
- Chỉ tối ưu khi xuất hiện Pain Point thực tế.
- Thiết kế phù hợp với quy mô của một Knowledge Intelligence System cá nhân.

Do đó, các mục tiêu như Horizontal Scaling, High Availability hoặc Distributed Deployment không phải là ưu tiên của phiên bản đầu tiên.

---

# 10.3 Performance

Hiệu năng của AI-Radar được đánh giá theo từng Pipeline thay vì toàn bộ hệ thống.

## Knowledge Update Pipeline

Pipeline cập nhật tri thức là tác vụ chạy theo lịch.

Do đó, hệ thống ưu tiên:

- Hoàn thành đầy đủ.
- Ổn định.
- Có khả năng phục hồi.

Thay vì tối ưu thời gian xử lý xuống mức thấp nhất.

Pipeline có thể mất vài phút để hoàn thành mà không ảnh hưởng đến trải nghiệm người dùng.

---

## Question Answering Pipeline

Đối với truy vấn của người dùng, thời gian phản hồi cần đủ nhanh để đảm bảo trải nghiệm sử dụng.

Thời gian xử lý chủ yếu bao gồm:

- Retrieval.
- Xây dựng Prompt.
- Gọi Groq API.
- Định dạng câu trả lời.

Do toàn bộ Knowledge Base đã được chuẩn bị trước, Pipeline này không cần thực hiện:

- Crawl.
- Cleaning.
- Knowledge Extraction.
- Embedding.

Điều này giúp giảm đáng kể độ trễ khi trả lời.

---

## Daily Digest

Daily Digest được sinh theo Batch.

Không yêu cầu thời gian phản hồi tức thời.

Điều quan trọng nhất là:

- tổng hợp đúng,
- dữ liệu đầy đủ,
- nội dung nhất quán.

---

# 10.4 Reliability

AI-Radar ưu tiên khả năng hoạt động ổn định hơn hiệu năng cực đại.

Một số nguyên tắc bao gồm:

- Một nguồn dữ liệu lỗi không làm dừng toàn bộ Pipeline.
- Một bài viết lỗi không ảnh hưởng các bài viết khác.
- Một Knowledge Object lỗi không làm hủy toàn bộ quá trình Embedding.
- Một lần gửi Zalo thất bại không làm mất dữ liệu đã xử lý.

Hệ thống luôn cố gắng hoàn thành tối đa công việc có thể thay vì dừng toàn bộ khi gặp lỗi cục bộ.

---

# 10.5 Availability

AI-Radar không phải hệ thống phục vụ thời gian thực 24/7.

Do đó:

- Không yêu cầu High Availability.
- Không yêu cầu Cluster Deployment.
- Không yêu cầu Multi-region.

Tuy nhiên, các thành phần cốt lõi như:

- Scheduler,
- Qdrant,
- Groq API,
- Zalo Webhook,

cần hoạt động ổn định trong phạm vi triển khai của dự án.

Nếu một thành phần tạm thời không khả dụng, hệ thống sẽ ghi nhận lỗi và xử lý theo chiến lược Retry hoặc Abort đã được thiết kế.

---

# 10.6 Scalability

Khả năng mở rộng của AI-Radar được thiết kế theo hướng Functional Scalability thay vì Infrastructure Scalability.

Hệ thống ưu tiên khả năng:

- bổ sung nguồn dữ liệu mới,
- bổ sung Prompt,
- thay đổi LLM Provider,
- thay đổi Embedding Model,
- thay đổi Notification Channel,

mà không phải thay đổi kiến trúc cốt lõi.

Phiên bản đầu tiên không hướng tới:

- Distributed Processing.
- Horizontal Scaling.
- Microservices.
- Event Streaming.

Đây là quyết định phù hợp với mục tiêu và quy mô hiện tại của dự án.

---

# 10.7 Maintainability

Khả năng bảo trì là một trong những mục tiêu quan trọng nhất của AI-Radar.

Toàn bộ hệ thống được thiết kế theo các nguyên tắc:

- Single Responsibility Principle.
- Separation of Concerns.
- Loose Coupling.
- Knowledge-Centric Design.

Mỗi Module chỉ đảm nhiệm một trách nhiệm duy nhất.

Các Module giao tiếp thông qua tầng Service hoặc Interface thay vì phụ thuộc trực tiếp vào nhau.

Điều này giúp:

- dễ sửa lỗi,
- dễ mở rộng,
- dễ kiểm thử,
- giảm ảnh hưởng dây chuyền khi thay đổi.

---

# 10.8 Extensibility

Ngay từ đầu, AI-Radar được thiết kế để hỗ trợ mở rộng.

Ví dụ:

Có thể bổ sung:

- RSS Source mới.
- GitHub Repository mới.
- Embedding Provider mới.
- LLM Provider mới.
- Notification Adapter mới.

Mà không làm thay đổi Business Logic.

Khả năng mở rộng đạt được thông qua việc phân tách rõ:

- Business Logic.
- Infrastructure.
- External Integration.

---

# 10.9 Security

Phiên bản đầu tiên chỉ triển khai các yêu cầu bảo mật cần thiết.

Bao gồm:

- API Key không lưu trong Source Code.
- Thông tin cấu hình được quản lý thông qua Environment Variables.
- Không ghi Log các thông tin nhạy cảm.
- Chỉ kết nối tới các API thông qua HTTPS.

Các yêu cầu bảo mật chi tiết sẽ được trình bày trong Chương 11.

---

# 10.10 Observability

Để hỗ trợ quá trình vận hành và bảo trì, hệ thống cần ghi nhận đầy đủ thông tin thực thi.

Các sự kiện quan trọng cần được Log bao gồm:

- Bắt đầu Pipeline.
- Kết thúc Pipeline.
- Số lượng bài viết đã thu thập.
- Số lượng Knowledge Object được tạo.
- Lỗi khi gọi API.
- Lỗi khi Embedding.
- Lỗi khi Retrieval.
- Lỗi khi gửi Zalo.

Log phục vụ việc theo dõi và phân tích sự cố.

Không được sử dụng Log để thay thế xử lý lỗi.

---

# 10.11 Configuration

Toàn bộ thông số có khả năng thay đổi cần được cấu hình bên ngoài mã nguồn.

Ví dụ:

- API Key.
- Scheduler Time.
- Groq Model.
- Embedding Model.
- Retrieval Top-K.
- RSS Sources.
- Qdrant Connection.

Điều này giúp hệ thống dễ triển khai trên nhiều môi trường mà không cần chỉnh sửa mã nguồn.

---

# 10.12 Portability

AI-Radar được thiết kế để có thể triển khai trên nhiều môi trường khác nhau.

Ví dụ:

- Máy cá nhân.
- Máy chủ Linux.
- Docker Container.

Việc triển khai không phụ thuộc vào hệ điều hành cụ thể.

Các thành phần hạ tầng được cấu hình độc lập với Business Logic nhằm giảm chi phí di chuyển giữa các môi trường.

---

# 10.13 Testability

Kiến trúc Module của AI-Radar hỗ trợ việc kiểm thử từng thành phần một cách độc lập.

Các Module có thể được kiểm thử riêng biệt thông qua Interface hoặc Mock.

Ví dụ:

- Fetcher có thể kiểm thử mà không cần Qdrant.
- Retrieval có thể kiểm thử với dữ liệu giả lập.
- Knowledge Processing có thể kiểm thử mà không cần Zalo.
- LLM Module có thể được Mock để giảm chi phí và tăng tính ổn định của quá trình kiểm thử.

Thiết kế này giúp việc xây dựng Unit Test và Integration Test trở nên đơn giản hơn.

---

# 10.14 Compatibility

Các thành phần bên ngoài được sử dụng thông qua API chuẩn hoặc Interface trừu tượng.

Điều này giúp hệ thống dễ dàng thay thế:

- Groq bằng LLM Provider khác.
- Qdrant bằng Vector Database khác.
- Zalo bằng nền tảng nhắn tin khác.

Việc thay đổi hạ tầng không làm ảnh hưởng đến Business Logic của hệ thống.

---

# 10.15 Tổng kết

Chương này đã mô tả các yêu cầu phi chức năng của AI-Radar nhằm đảm bảo hệ thống không chỉ đáp ứng đúng chức năng mà còn duy trì được chất lượng trong quá trình vận hành.

Thay vì theo đuổi các mục tiêu như khả năng mở rộng vô hạn hoặc kiến trúc phân tán phức tạp, AI-Radar ưu tiên tính đơn giản, ổn định, dễ bảo trì và khả năng mở rộng hợp lý với quy mô của một Knowledge Intelligence System cá nhân.

Các yêu cầu này là cơ sở cho các chương tiếp theo về Security, Testing Strategy và Deployment, đồng thời đóng vai trò là tiêu chí đánh giá chất lượng của toàn bộ hệ thống trong quá trình triển khai.

> Nhớ điều chỉnh cây thư mục.