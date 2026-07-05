# 11. Security

---

# 11.1 Mục đích

Chương này mô tả các yêu cầu và nguyên tắc bảo mật của AI-Radar.

Mục tiêu của chương này không phải xây dựng một hệ thống bảo mật phức tạp, mà là xác định các biện pháp cần thiết để bảo vệ:

- Thông tin cấu hình.
- Dữ liệu tri thức.
- Các dịch vụ bên ngoài.
- Quá trình vận hành của hệ thống.

Các yêu cầu bảo mật được thiết kế phù hợp với phạm vi của một Knowledge Intelligence System cá nhân và tuân theo nguyên tắc **Security by Simplicity**.

---

# 11.2 Triết lý bảo mật

AI-Radar áp dụng triết lý:

- Chỉ bảo vệ những tài sản thực sự cần bảo vệ.
- Không bổ sung cơ chế bảo mật vượt quá nhu cầu hiện tại.
- Mỗi lớp bảo mật phải giải quyết một rủi ro cụ thể.
- Ưu tiên cấu hình đúng hơn là triển khai nhiều cơ chế phức tạp.

Phiên bản đầu tiên không hướng đến việc đáp ứng các tiêu chuẩn bảo mật dành cho hệ thống doanh nghiệp hoặc môi trường đa người dùng.

---

# 11.3 Security Scope

Các thành phần cần được bảo vệ bao gồm:

- API Key.
- Access Token.
- Environment Configuration.
- Knowledge Base.
- Prompt Configuration.
- Webhook Endpoint.
- Log dữ liệu.

Các thành phần này được xem là tài sản quan trọng của hệ thống.

---

# 11.4 Secrets Management

Toàn bộ thông tin bí mật phải được quản lý tách khỏi mã nguồn.

Bao gồm:

- Groq API Key.
- Qdrant API Key (nếu có).
- Zalo Access Token.
- Webhook Secret.
- Các thông tin xác thực khác.

Các thông tin này được lưu thông qua Environment Variables hoặc cơ chế quản lý cấu hình của môi trường triển khai.

Không được:

- Hard-code Secret.
- Commit Secret lên Git.
- Ghi Secret trong tài liệu.

---

# 11.5 Configuration Security

Các tệp cấu hình chỉ chứa:

- Giá trị mặc định.
- Tham số hệ thống.
- Thiết lập triển khai.

Các thông tin nhạy cảm luôn được nạp từ Environment Variables trong quá trình khởi động ứng dụng.

Việc tách biệt này giúp giảm nguy cơ rò rỉ thông tin khi chia sẻ mã nguồn hoặc triển khai trên nhiều môi trường.

---

# 11.6 External Communication Security

Toàn bộ kết nối tới các dịch vụ bên ngoài cần sử dụng giao thức bảo mật.

Bao gồm:

- Groq API.
- Qdrant.
- RSS Feed (khi nguồn hỗ trợ HTTPS).
- Zalo Official Account API.

Hệ thống không truyền tải thông tin xác thực thông qua kết nối không an toàn.

Trong trường hợp nguồn dữ liệu chỉ hỗ trợ HTTP, dữ liệu chỉ được sử dụng nếu được đánh giá là không chứa thông tin nhạy cảm.

---

# 11.7 Webhook Security

Webhook là điểm tiếp nhận yêu cầu từ bên ngoài.

Do đó cần đảm bảo:

- Chỉ xử lý các HTTP Method được hỗ trợ.
- Kiểm tra định dạng dữ liệu đầu vào.
- Xác thực yêu cầu nếu nền tảng tích hợp hỗ trợ.
- Từ chối các yêu cầu không hợp lệ.

Webhook không được giả định rằng mọi Request đều đáng tin cậy.

---

# 11.8 Input Validation

Toàn bộ dữ liệu đầu vào đều cần được kiểm tra trước khi xử lý.

Bao gồm:

- RSS Feed.
- Website Content.
- Webhook Payload.
- User Question.
- Configuration.

Việc kiểm tra bao gồm:

- Định dạng.
- Kiểu dữ liệu.
- Giá trị bắt buộc.
- Giới hạn kích thước nếu cần.

Input Validation giúp giảm nguy cơ lỗi và tăng tính ổn định của Pipeline.

---

# 11.9 Output Validation

Dữ liệu trước khi chuyển sang Module tiếp theo cũng cần được kiểm tra.

Ví dụ:

Knowledge Object cần:

- Có Title.
- Có Summary.
- Có Source.
- Có Main Content.

Embedding cần:

- Sinh thành công.
- Đúng Dimension.
- Không rỗng.

Prompt Context cần:

- Có Retrieval Result.
- Không vượt quá giới hạn Context của LLM.

Nếu dữ liệu không đạt yêu cầu, Pipeline sẽ dừng tại bước hiện tại hoặc xử lý theo chiến lược lỗi đã thiết kế.

---

# 11.10 Logging Security

Log phục vụ việc theo dõi và phân tích lỗi.

Tuy nhiên, Log không được chứa:

- API Key.
- Access Token.
- Secret.
- Thông tin xác thực.
- Nội dung nhạy cảm của cấu hình.

Trong trường hợp cần ghi nhận lỗi liên quan đến xác thực, chỉ ghi loại lỗi và ngữ cảnh cần thiết cho việc Debug.

---

# 11.11 Dependency Security

AI-Radar sử dụng các thư viện mã nguồn mở.

Các nguyên tắc bao gồm:

- Chỉ sử dụng thư viện có mục đích rõ ràng.
- Hạn chế phụ thuộc không cần thiết.
- Cập nhật phiên bản khi cần thiết để khắc phục lỗi bảo mật.
- Không thêm thư viện chỉ vì tiện lợi nếu có thể tự triển khai đơn giản.

Điều này giúp giảm bề mặt tấn công và tăng khả năng bảo trì lâu dài.

---

# 11.12 Data Protection

Knowledge Base của AI-Radar chủ yếu lưu trữ tri thức công khai được thu thập từ Internet.

Do đó:

- Không lưu thông tin cá nhân của người dùng.
- Không lưu dữ liệu bí mật của tổ chức.
- Không lưu thông tin xác thực.

Trong tương lai nếu bổ sung dữ liệu riêng tư, cần bổ sung cơ chế bảo vệ tương ứng.

---

# 11.13 Denial of Service Considerations

Phiên bản đầu tiên không triển khai các cơ chế chống tấn công chuyên biệt như:

- Rate Limiting phân tán.
- WAF.
- DDoS Protection.

Tuy nhiên, hệ thống vẫn cần:

- Giới hạn dữ liệu đầu vào hợp lý.
- Xử lý ngoại lệ đầy đủ.
- Không để một yêu cầu lỗi làm dừng toàn bộ tiến trình.

Điều này đủ đáp ứng phạm vi triển khai hiện tại.

---

# 11.14 Security Boundaries

Business Logic không được trực tiếp quản lý:

- Secret.
- Access Token.
- HTTP Client Configuration.

Các thành phần này thuộc tầng Infrastructure hoặc Integration.

Việc phân tách trách nhiệm giúp:

- giảm Coupling,
- dễ kiểm thử,
- dễ thay đổi cơ chế xác thực khi cần.

---

# 11.15 Future Security Enhancements

Thiết kế hiện tại cho phép bổ sung các cơ chế bảo mật trong tương lai mà không làm thay đổi kiến trúc cốt lõi.

Ví dụ:

- Token Rotation.
- Secret Manager.
- Request Signature Verification.
- Rate Limiting.
- Audit Log.
- Encryption at Rest.
- Role-based Access Control.

Các tính năng này chưa được triển khai trong phiên bản đầu tiên vì chưa xuất hiện nhu cầu thực tế.

---

# 11.16 Tổng kết

Chương này đã mô tả các yêu cầu bảo mật của AI-Radar theo định hướng đơn giản, thực dụng và phù hợp với mục tiêu của dự án.

Thay vì triển khai nhiều cơ chế bảo mật phức tạp ngay từ đầu, hệ thống tập trung vào việc bảo vệ các tài sản quan trọng như Secret, Configuration, Webhook và Knowledge Base thông qua các nguyên tắc thiết kế rõ ràng và phân tách trách nhiệm hợp lý.

Cách tiếp cận này vừa đảm bảo mức độ an toàn cần thiết cho phiên bản hiện tại, vừa tạo nền tảng để mở rộng các cơ chế bảo mật khi quy mô hệ thống phát triển trong tương lai.
