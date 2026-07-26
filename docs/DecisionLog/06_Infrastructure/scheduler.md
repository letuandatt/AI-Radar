# Decision: Use GitHub Actions Cron for Scheduling

## Decision
Hệ thống sử dụng **GitHub Actions** với tính năng `cron` để kích hoạt **Knowledge Update Pipeline** theo lịch định kỳ (ví dụ: 06:00 sáng hàng ngày) thay vì tích hợp sẵn một scheduler daemon (như Celery Beat hoặc APScheduler) vào trong ứng dụng.

## Context
AI-Radar cần một cơ chế để tự động chạy pipeline cập nhật tri thức mà không cần sự can thiệp thủ công. Việc lựa chọn công cụ scheduler cần cân nhắc giữa độ tin cậy, chi phí vận hành và độ phức tích hợp.

## Why This Decision?
1.  **Zero Maintenance:** GitHub Actions là dịch vụ managed, không cần lo lắng về việc server bị treo, cron job bị chết hay cần monitor process. Nó luôn sẵn sàng khi đến giờ chạy.
2.  **Cost-Effective:** Free tier của GitHub Actions đủ rộng rãi cho tần suất chạy 1 lần/ngày của một dự án cá nhân.
3.  **Separation of Concerns:** Ứng dụng AI-Radar chỉ tập trung vào logic xử lý tri thức. Việc "khi nào chạy" được giao phó hoàn toàn cho hạ tầng bên ngoài. Điều này giúp ứng dụng trở nên Stateless hơn.
4.  **CI/CD Integration:** Cùng một workflow có thể vừa dùng để chạy test khi có code mới, vừa dùng để chạy scheduler, giúp tận dụng tối đa hạ tầng CI/CD hiện có.

## Why Not Alternatives?
-   **Not Celery Beat / APScheduler:** Tích hợp scheduler vào trong app đòi hỏi app phải chạy liên tục (daemon mode), tốn RAM và cần cơ chế giám sát (monitoring) để đảm bảo nó không bị crash. Với tác vụ chạy 1 lần/ngày, việc giữ app chạy 24/7 là lãng phí tài nguyên.
-   **Not Linux Crontab:** Phụ thuộc vào môi trường server cụ thể, khó quản lý version control và khó debug nếu script bị lỗi quyền truy cập hoặc môi trường biến.

## Impact
-   Repository chứa file `.github/workflows/update_knowledge.yml` định nghĩa lịch trình cron.
-   Workflow sẽ SSH vào host hoặc gọi API endpoint của ứng dụng để kích hoạt pipeline.
-   Ứng dụng AI-Radar cần expose một endpoint hoặc CLI command an toàn để nhận tín hiệu trigger từ GitHub Actions.