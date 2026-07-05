# 13. Deployment

---

# 13.1 Mục đích

Chương này mô tả chiến lược triển khai (Deployment Strategy) của AI-Radar.

Mục tiêu của chương này là xác định cách hệ thống được triển khai và vận hành trong các môi trường khác nhau, đồng thời đảm bảo:

- Dễ triển khai.
- Dễ bảo trì.
- Dễ nâng cấp.
- Dễ di chuyển giữa các môi trường.

Các nội dung trong chương này chỉ tập trung vào yêu cầu và nguyên tắc triển khai. Thiết kế hạ tầng chi tiết sẽ được trình bày trong tài liệu Architecture.

---

# 13.2 Triết lý triển khai

AI-Radar áp dụng triết lý:

- Đơn giản trước.
- Tự động khi hợp lý.
- Giảm tối đa thao tác thủ công.
- Không triển khai hạ tầng vượt quá nhu cầu hiện tại.

Phiên bản đầu tiên hướng tới việc triển khai ổn định trên một môi trường chạy duy nhất thay vì nhiều cụm máy chủ phân tán.

---

# 13.3 Deployment Goals

Việc triển khai cần đáp ứng các mục tiêu sau:

- Dễ cài đặt.
- Dễ cấu hình.
- Dễ nâng cấp phiên bản.
- Dễ khôi phục khi xảy ra sự cố.
- Không phụ thuộc vào môi trường phát triển.

Toàn bộ quá trình triển khai cần có khả năng lặp lại với kết quả nhất quán.

---

# 13.4 Deployment Environment

AI-Radar được thiết kế để có thể triển khai trên nhiều môi trường khác nhau.

Ví dụ:

- Máy phát triển cá nhân.
- Máy chủ Linux.
- Docker Container.

Kiến trúc của hệ thống không phụ thuộc vào một nền tảng triển khai cụ thể.

---

# 13.5 Runtime Components

Một phiên bản AI-Radar bao gồm các thành phần chính:

- Backend Application.
- Qdrant.
- Groq API.
- Zalo Official Account.
- Scheduler.

Các thành phần này phối hợp tạo thành một hệ thống hoàn chỉnh phục vụ hai Pipeline chính của AI-Radar.

---

# 13.6 Configuration Management

Toàn bộ thông tin cấu hình được quản lý tách khỏi mã nguồn.

Bao gồm:

- API Key.
- Access Token.
- URL dịch vụ.
- Scheduler Configuration.
- Embedding Model.
- LLM Model.
- Retrieval Configuration.

Việc thay đổi cấu hình không yêu cầu chỉnh sửa Business Logic.

---

# 13.7 Environment Separation

Các môi trường triển khai cần được tách biệt về cấu hình.

Ví dụ:

- Development.
- Testing.
- Production.

Mỗi môi trường có thể sử dụng:

- API Key riêng.
- Qdrant riêng.
- Scheduler riêng.
- Log Level riêng.

Việc tách biệt này giúp giảm rủi ro trong quá trình phát triển và vận hành.

---

# 13.8 Deployment Automation

Quá trình triển khai nên được tự động hóa khi phù hợp.

Ví dụ:

- Build Application.
- Chạy Test.
- Đóng gói Docker Image.
- Khởi động dịch vụ.

Việc tự động hóa giúp giảm sai sót do thao tác thủ công và đảm bảo quá trình triển khai nhất quán.

---

# 13.9 Scheduler Deployment

Knowledge Update và Daily Digest đều là các tác vụ chạy theo lịch.

Do đó, Scheduler cần được triển khai cùng hệ thống.

Scheduler chịu trách nhiệm:

- Khởi động Pipeline đúng thời điểm.
- Không phụ thuộc vào thao tác của người dùng.
- Có khả năng chạy lặp lại theo cấu hình.

Thời gian thực thi được quản lý thông qua cấu hình thay vì mã nguồn.

---

# 13.10 Dependency Management

Toàn bộ thư viện và thành phần phụ thuộc cần được quản lý tập trung.

Nguyên tắc bao gồm:

- Phiên bản được xác định rõ ràng.
- Hạn chế thay đổi ngoài kế hoạch.
- Đảm bảo khả năng tái tạo môi trường triển khai.

Việc quản lý Dependency nhất quán giúp giảm các lỗi phát sinh do khác biệt giữa các môi trường.

---

# 13.11 Deployment Validation

Sau mỗi lần triển khai, hệ thống cần được xác minh ở mức cơ bản.

Bao gồm:

- Ứng dụng khởi động thành công.
- Scheduler hoạt động.
- Kết nối Qdrant thành công.
- Kết nối Groq thành công.
- Webhook hoạt động.
- Pipeline có thể thực thi.

Việc xác minh giúp phát hiện sớm các lỗi cấu hình hoặc triển khai.

---

# 13.12 Upgrade Strategy

Hệ thống cần hỗ trợ nâng cấp mà không làm thay đổi kiến trúc tổng thể.

Quá trình nâng cấp có thể bao gồm:

- Cập nhật Application.
- Cập nhật Prompt.
- Thay đổi Embedding Model.
- Thay đổi LLM Model.
- Bổ sung RSS Source.

Các thay đổi này cần được thực hiện độc lập với dữ liệu tri thức đã lưu trữ khi có thể.

---

# 13.13 Backup and Recovery

Knowledge Base là tài sản quan trọng nhất của AI-Radar.

Do đó cần có khả năng:

- Sao lưu dữ liệu.
- Khôi phục khi xảy ra sự cố.
- Triển khai lại hệ thống mà không làm mất Knowledge đã thu thập.

Chiến lược sao lưu cụ thể phụ thuộc vào môi trường triển khai và sẽ được xác định trong giai đoạn triển khai thực tế.

---

# 13.14 Operational Considerations

Trong quá trình vận hành, hệ thống cần đảm bảo:

- Theo dõi Log.
- Theo dõi Scheduler.
- Theo dõi Pipeline.
- Theo dõi trạng thái các dịch vụ tích hợp.

Mục tiêu là nhanh chóng phát hiện và xử lý các sự cố có thể ảnh hưởng đến quá trình cập nhật tri thức hoặc trả lời người dùng.

---

# 13.15 Tổng kết

Chương này đã mô tả các yêu cầu và nguyên tắc triển khai của AI-Radar.

Thay vì tập trung vào các kiến trúc triển khai phức tạp như Distributed Deployment hoặc Kubernetes, AI-Radar ưu tiên một quy trình triển khai đơn giản, ổn định và dễ bảo trì, phù hợp với mục tiêu của một Knowledge Intelligence System cá nhân.

Các yêu cầu này tạo nền tảng cho việc hiện thực hóa hệ thống trong nhiều môi trường khác nhau mà vẫn giữ nguyên các quyết định thiết kế đã được thống nhất.

---