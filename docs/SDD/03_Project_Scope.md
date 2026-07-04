# 3. Project Scope

## 3.1 In Scope

Phiên bản đầu tiên của AI-Radar sẽ bao gồm các chức năng sau.

### Knowledge Collection

Thu thập dữ liệu định kỳ từ nhiều nguồn.

Ví dụ:

* Hugging Face
* Hacker News
* GitHub Trending
* RSS AI Blogs
* Papers With Code

---

### Knowledge Processing

Mỗi bài viết sẽ được:

* chuẩn hóa,
* loại bỏ dữ liệu dư thừa,
* tóm tắt,
* phân loại chủ đề,
* trích xuất từ khóa,
* đánh giá mức độ quan trọng.

Kết quả cuối cùng là một Knowledge Object.

---

### Knowledge Storage

Knowledge Object sẽ được embedding và lưu trong Qdrant.

Hệ thống không lưu vector của bài báo gốc.

Thay vào đó lưu vector của Knowledge Object đã được AI chuẩn hóa.

Điều này giúp:

* giảm kích thước dữ liệu,
* tăng chất lượng retrieval,
* giảm token khi RAG.

---

### Daily Intelligence

Mỗi ngày lúc 06:00 sáng, hệ thống tự động:

* cập nhật dữ liệu mới,
* xây dựng Daily Digest,
* gửi bản tin tới Zalo.

---

### Semantic Question Answering

Người dùng có thể đặt câu hỏi.

Ví dụ:

* OCR framework mới nhất?
* LangGraph Memory là gì?
* Có gì mới về MCP?

Hệ thống sẽ sử dụng RAG để trả lời.

---
