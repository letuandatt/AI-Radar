# Decision: Use Docker for Containerization

## Decision
Toàn bộ ứng dụng AI-Radar và cơ sở dữ liệu Qdrant được đóng gói và triển khai dưới dạng **Docker Containers** sử dụng `Dockerfile` và `docker-compose.yml`.

## Context
Việc triển khai một ứng dụng Python với nhiều dependency (LangChain, Groq, Qdrant client...) thường gặp vấn đề "It works on my machine" do khác biệt về môi trường (OS, Python version, library conflicts). Hơn nữa, Qdrant là một dịch vụ riêng biệt cần chạy song song với ứng dụng chính.

## Why This Decision?
1.  **Consistency:** Đảm bảo môi trường chạy ở Local, Testing và Production là giống hệt nhau. Loại bỏ hoàn toàn các lỗi do xung đột thư viện hoặc thiếu dependency hệ thống.
2.  **Simplicity in Deployment:** Chỉ cần một lệnh `docker-compose up -d` để khởi động toàn bộ hệ thống (App + Qdrant + Network). Không cần cài đặt Python hay Qdrant thủ công trên server.
3.  **Isolation:** Ứng dụng AI-Radar và Qdrant chạy trong các container riêng biệt, giao tiếp qua Docker Network nội bộ. Điều này tăng cường bảo mật vì Qdrant không cần expose port ra internet public.
4.  **Portability:** Dễ dàng di chuyển hệ thống sang bất kỳ máy chủ Linux nào hoặc VPS mà không cần cấu hình lại từ đầu.

## Why Not Alternatives?
-   **Not Virtual Machines (VMs):** VMs nặng nề, tốn tài nguyên và thời gian khởi động lâu hơn so với containers. Với quy mô cá nhân, Docker đủ để cách ly môi trường.
-   **Not Kubernetes (K8s):** K8s quá phức tạp và cồng kềnh cho một ứng dụng monolithic chạy trên một node duy nhất. Nó vi phạm nguyên tắc Simplicity Wins.
-   **Not Manual Installation:** Cài đặt thủ công dễ dẫn đến sai sót, khó sao lưu và khó tái tạo môi trường khi có sự cố.

## Impact
-   Dự án bao gồm `Dockerfile` cho ứng dụng Python và `docker-compose.yml` để định nghĩa services (`app`, `qdrant`).
-   Dữ liệu của Qdrant được lưu trữ bền vững thông qua Docker Volume (`qdrant_storage`), đảm bảo không mất tri thức khi restart container.
-   Biến môi trường được inject vào container thông qua file `.env`.