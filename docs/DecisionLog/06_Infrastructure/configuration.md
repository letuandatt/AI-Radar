# Decision: Environment Variables for Configuration Management

## Decision
Mọi thông tin cấu hình nhạy cảm (Secrets) và đặc thù môi trường (Endpoints, Models) đều được quản lý thông qua **Environment Variables** (file `.env`) và được nạp vào ứng dụng thông qua module `config/settings.py`.

## Context
Một hệ thống tích hợp nhiều dịch vụ bên ngoài (Groq, Qdrant, Zalo) cần quản lý nhiều API Keys và URL. Hard-code các thông tin này vào source code là rủi ro bảo mật nghiêm trọng và gây khó khăn khi chuyển đổi giữa các môi trường (Dev/Prod).

## Why This Decision?
1.  **Security:** API Keys không bao giờ xuất hiện trong mã nguồn hoặc được commit lên Git. File `.env` được thêm vào `.gitignore`.
2.  **Flexibility:** Dễ dàng thay đổi model LLM, top-k retrieval, hoặc cron schedule mà không cần sửa code và deploy lại. Chỉ cần thay đổi biến môi trường và restart container.
3.  **Standard Practice:** Đây là chuẩn công nghiệp cho việc quản lý cấu hình trong các ứng dụng 12-factor app, đảm bảo tính portability cao.
4.  **Fail-Fast:** Module `settings.py` sẽ validate sự tồn tại của các biến bắt buộc ngay khi khởi động. Nếu thiếu `GROQ_API_KEY`, ứng dụng sẽ từ chối chạy, tránh các lỗi runtime khó hiểu sau này.

## Why Not Alternatives?
-   **Not Hard-coded Constants:** Vi phạm nguyên tắc bảo mật, khiến việc chia sẻ code hoặc cộng tác trở nên nguy hiểm.
-   **Not Config Files (JSON/YAML) in Repo:** Vẫn có nguy cơ bị commit nhầm thông tin nhạy cảm. Environment variables tách biệt rõ ràng giữa code và config.
-   **Not Cloud Secret Managers (AWS Secrets Manager, etc.):** Quá phức tạp và tốn kém cho một dự án cá nhân chạy trên Docker/VPS đơn giản.

## Impact
-   Dự án cung cấp file `.env.example` làm template cho người dùng điền thông tin.
-   Module `app/config/settings.py` chịu trách nhiệm đọc `os.getenv()` và đóng gói thành một object cấu hình duy nhất để các module khác sử dụng.
-   Các giá trị mặc định (default values) cho các tham số không nhạy cảm (như `TOP_K=5`) có thể được đặt trong code để tiện cho việc phát triển local.