# 5. Design Philosophy

Toàn bộ hệ thống được xây dựng dựa trên năm nguyên tắc cốt lõi.

## 5.1 Simplicity First

Hệ thống chỉ sử dụng những thành phần thực sự cần thiết.

Mỗi công nghệ được đưa vào đều phải giải thích được lý do tồn tại.

Không bổ sung thành phần chỉ vì xu hướng hoặc để tăng số lượng công nghệ trong dự án.

---

## 5.2 AI Only Where AI Adds Value

LLM là thành phần có chi phí cao nhất.

Do đó AI chỉ được sử dụng ở các bước mà thuật toán truyền thống khó thực hiện.

Ví dụ:

* tóm tắt,
* phân loại,
* trích xuất keyword,
* trả lời câu hỏi.

Các công việc như:

* crawl,
* parse,
* retry,
* deduplicate,
* scheduling

được thực hiện bằng các thuật toán thông thường.

Điều này giúp giảm đáng kể chi phí vận hành.

---

## 5.3 Knowledge-centric Architecture

Thay vì coi bài báo là đơn vị lưu trữ, AI-Radar coi tri thức đã được xử lý là đơn vị trung tâm.

Mỗi Knowledge Object đại diện cho một mảnh tri thức độc lập.

Toàn bộ hệ thống, từ Daily Digest đến RAG, đều làm việc trên Knowledge Object thay vì dữ liệu thô.

Đây là quyết định kiến trúc quan trọng nhất của dự án.

---

## 5.4 Loose Coupling

Mỗi module chỉ chịu trách nhiệm cho một chức năng.

Fetcher không biết Vector Database hoạt động như thế nào.

Vector Database không biết Notification Service.

Notification Service không biết Retriever.

Việc tách biệt trách nhiệm giúp hệ thống dễ kiểm thử, dễ mở rộng và dễ bảo trì.

---

## 5.5 Extensibility

Ngay từ đầu, hệ thống được thiết kế để có thể mở rộng mà không phải thay đổi kiến trúc cốt lõi.

Ví dụ:

* thay Groq bằng OpenRouter,
* thay Chroma bằng Qdrant,
* thay Zalo bằng Telegram,
* thêm nguồn RSS mới,
* thêm Dashboard,

đều chỉ ảnh hưởng đến một số module cụ thể thay vì toàn bộ hệ thống.

---