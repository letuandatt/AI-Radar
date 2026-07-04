# 7. Mô hình dữ liệu (Data Model)

---

## 7.1 Tổng quan

Mô hình dữ liệu (Data Model) định nghĩa cách dữ liệu được biểu diễn, chuyển đổi, lưu trữ và sử dụng xuyên suốt vòng đời của hệ thống AI-Radar.

Khác với các hệ thống tổng hợp tin tức truyền thống, AI-Radar không xem bài viết gốc (Raw Article) là tài sản dữ liệu quan trọng nhất. Thay vào đó, toàn bộ dữ liệu sau khi thu thập sẽ được chuyển đổi thành một thực thể tri thức chuẩn hóa gọi là **Knowledge Object** trước khi được lưu vào Knowledge Base.

Đây là một trong những quyết định thiết kế quan trọng nhất của hệ thống.

Việc chuẩn hóa dữ liệu theo hướng Knowledge-Centric mang lại nhiều lợi ích:

- Chuẩn hóa dữ liệu đến từ nhiều nguồn khác nhau.
- Loại bỏ thông tin dư thừa hoặc ít giá trị.
- Cải thiện chất lượng Semantic Retrieval.
- Giảm số lượng token khi xây dựng Prompt cho LLM.
- Cho phép nhiều thành phần trong hệ thống tái sử dụng cùng một nguồn tri thức.

Trong toàn bộ AI-Radar, **Knowledge Object** được xem là nguồn dữ liệu chuẩn (Single Source of Truth).

---

## 7.2 Mô hình miền dữ liệu (Domain Model)

AI-Radar không được thiết kế theo mô hình cơ sở dữ liệu quan hệ (Relational Database).

Thay vào đó, dữ liệu được tổ chức theo các thực thể (Domain Entities), phản ánh đúng vòng đời của tri thức trong hệ thống.

```
                Raw Article
                     │
                     ▼
            Knowledge Object
                     │
         ┌───────────┴────────────┐
         ▼                        ▼
Embedding Record          Daily Digest
         │
         ▼
 Qdrant Knowledge Base
```

Mối quan hệ giữa các thực thể được mô tả như sau:

- Một **Raw Article** sau khi được xử lý sẽ tạo ra một **Knowledge Object**.
- Mỗi **Knowledge Object** sẽ sinh ra một **Embedding Record**.
- Embedding cùng Metadata sẽ được lưu vào **Qdrant**.
- Daily Digest sẽ được tạo từ tập hợp các Knowledge Object thay vì từ bài viết gốc.

Thiết kế này giúp toàn bộ hệ thống luôn làm việc trên dữ liệu đã được chuẩn hóa.

---

# 7.3 Raw Article Model

## Mục đích

Raw Article đại diện cho dữ liệu vừa được thu thập từ Internet.

Đây chỉ là dữ liệu tạm thời trong quá trình xử lý và **không được xem là dữ liệu lâu dài của hệ thống**.

Raw Article chỉ tồn tại trong Knowledge Update Pipeline.

Sau khi hoàn thành việc xây dựng Knowledge Object, dữ liệu này sẽ được loại bỏ.

---

## Thuộc tính

| Thuộc tính | Ý nghĩa |
|------------|----------|
| title | Tiêu đề bài viết |
| content | Nội dung đầy đủ |
| author | Tác giả (nếu có) |
| url | Liên kết bài viết |
| source | Nguồn dữ liệu |
| published_at | Thời gian phát hành |
| language | Ngôn ngữ |
| fetched_at | Thời điểm hệ thống thu thập |

---

## Vòng đời

```
Fetcher

↓

Raw Article

↓

Knowledge Processing

↓

Discard
```

Raw Article không bao giờ được đưa trực tiếp vào Qdrant.

Đây là một quyết định thiết kế nhằm đảm bảo Knowledge Base chỉ chứa tri thức đã được chuẩn hóa.

---

# 7.4 Knowledge Object Model

## Mục đích

Knowledge Object là thực thể quan trọng nhất của AI-Radar.

Đây là kết quả sau khi hệ thống:

- làm sạch dữ liệu,
- loại bỏ thông tin dư thừa,
- tóm tắt nội dung,
- trích xuất từ khóa,
- phân loại chủ đề.

Thay vì lưu toàn bộ bài viết gốc, AI-Radar chỉ lưu Knowledge Object.

Toàn bộ các module phía sau như:

- Daily Digest,
- Semantic Retrieval,
- Question Answering,

đều làm việc trực tiếp với Knowledge Object.

---

## Thuộc tính

| Thuộc tính | Ý nghĩa |
|------------|----------|
| id | Mã định danh duy nhất |
| title | Tiêu đề tri thức |
| summary | Nội dung tóm tắt |
| key_takeaways | Các ý chính quan trọng |
| keywords | Từ khóa kỹ thuật |
| topics | Chủ đề công nghệ |
| source | Nguồn dữ liệu |
| url | Liên kết bài viết |
| published_at | Ngày phát hành |
| created_at | Thời điểm tạo Knowledge Object |
| importance_score | Mức độ quan trọng |
| embedding_id | Mã Embedding tương ứng |

---

## Giải thích một số thuộc tính

### Summary

Đây là phần tóm tắt do LLM sinh ra.

Summary được sử dụng trong:

- Daily Digest
- Semantic Retrieval
- Prompt Context

Thay vì sử dụng toàn bộ bài viết.

---

### Key Takeaways

Đây là tập hợp các ý chính có giá trị nhất của bài viết.

Ví dụ:

- Mô hình OCR mới đạt SOTA.
- Hỗ trợ nhận dạng đa ngôn ngữ.
- Đã mã nguồn mở trên GitHub.

Key Takeaways giúp LLM dễ dàng tổng hợp thông tin khi trả lời câu hỏi.

---

### Topics

Topics là tập hợp các chủ đề được chuẩn hóa.

Ví dụ:

- LLM
- RAG
- OCR
- AI Agent
- MCP
- Computer Vision
- MLOps

Không sử dụng Tag tự do nhằm tránh việc cùng một chủ đề nhưng được đặt nhiều tên khác nhau.

---

### Importance Score

Đây là điểm đánh giá mức độ quan trọng của Knowledge Object.

Thông tin này có thể được sử dụng để:

- ưu tiên bài viết nổi bật,
- xếp hạng Daily Digest,
- lọc các bài viết ít giá trị.

---

## Vòng đời

```
Raw Article

↓

Knowledge Builder

↓

Knowledge Object

↓

Embedding

↓

Qdrant

↓

Retriever

↓

Prompt Context

↓

Generated Answer
```

Knowledge Object là dữ liệu tồn tại lâu dài nhất trong hệ thống.

---

# 7.5 Embedding Record

## Mục đích

Embedding Record biểu diễn Knowledge Object dưới dạng vector số.

Embedding không phục vụ người dùng cuối mà chỉ phục vụ quá trình Semantic Search.

---

## Thuộc tính

| Thuộc tính | Ý nghĩa |
|------------|----------|
| knowledge_id | Knowledge Object liên kết |
| vector | Vector Embedding |
| embedding_model | Tên mô hình Embedding |
| dimension | Kích thước vector |
| created_at | Thời điểm tạo |

---

## Lưu ý

Embedding Record không chứa nghiệp vụ.

Nó chỉ phục vụ việc tính toán độ tương đồng giữa các Knowledge Object.

Việc tách Embedding khỏi dữ liệu nghiệp vụ giúp kiến trúc dễ dàng thay đổi mô hình Embedding trong tương lai.

---

# 7.6 Thiết kế Qdrant Collection

AI-Radar sử dụng **Qdrant** làm Vector Database.

Qdrant chịu trách nhiệm lưu trữ:

- Vector Embedding.
- Metadata của Knowledge Object.

Không lưu:

- Raw Article.
- HTML.
- Nội dung đầy đủ của bài viết.

---

## Collection

```
knowledge_base
```

---

## Payload

Mỗi Vector sẽ đi kèm Metadata.

| Trường | Ý nghĩa |
|---------|----------|
| id | Mã tri thức |
| title | Tiêu đề |
| summary | Nội dung tóm tắt |
| keywords | Từ khóa |
| topics | Chủ đề |
| source | Nguồn dữ liệu |
| url | Liên kết |
| published_at | Ngày phát hành |
| importance_score | Điểm quan trọng |

---

## Vector

Kích thước Vector phụ thuộc vào mô hình Embedding được lựa chọn.

Do đó hệ thống không ràng buộc với một số chiều (Dimension) cố định.

Điều này giúp AI-Radar dễ dàng thay đổi Embedding Provider trong tương lai mà không ảnh hưởng đến kiến trúc tổng thể.

---

# 7.7 Daily Digest Model

## Mục đích

Daily Digest đại diện cho bản tin công nghệ được gửi tới người dùng theo lịch định kỳ.

Thay vì sinh lại từ đầu nhiều lần, Digest có thể được tái tạo từ các Knowledge Object đã tồn tại.

---

## Thuộc tính

| Thuộc tính | Ý nghĩa |
|------------|----------|
| date | Ngày tạo Digest |
| generated_at | Thời điểm sinh |
| knowledge_ids | Danh sách Knowledge Object |
| summary | Nội dung tổng hợp |
| top_topics | Các chủ đề nổi bật |

---

# 7.8 Message Model

## Mục đích

Message Model mô tả cấu trúc logic của tin nhắn gửi tới người dùng.

Model này độc lập với nền tảng triển khai (Zalo, Telegram, Discord,...).

Điều này giúp hệ thống dễ dàng mở rộng thêm các kênh thông báo trong tương lai.

---

## Thuộc tính

| Thuộc tính | Ý nghĩa |
|------------|----------|
| title | Tiêu đề |
| body | Nội dung |
| references | Danh sách liên kết tham khảo |
| timestamp | Thời điểm gửi |

---

# 7.9 Vòng đời dữ liệu (Data Lifecycle)

Dữ liệu trong AI-Radar luôn tuân theo một vòng đời cố định.

```
Raw Article

↓

Knowledge Object

↓

Embedding

↓

Qdrant

↓

Retriever

↓

Prompt Context

↓

Generated Answer
```

Trong toàn bộ quá trình này:

- Raw Article chỉ tồn tại trong Pipeline cập nhật tri thức.
- Prompt Context chỉ tồn tại trong thời gian tạo câu trả lời.
- Knowledge Object và Embedding là hai thực thể được lưu trữ lâu dài.

Việc phân chia rõ vòng đời của từng loại dữ liệu giúp giảm dung lượng lưu trữ và đơn giản hóa quá trình bảo trì hệ thống.

---

# 7.10 Kiểm tra tính hợp lệ của dữ liệu

Để đảm bảo chất lượng của Knowledge Base, mọi Knowledge Object phải vượt qua bước kiểm tra trước khi được lưu vào Qdrant.

Các trường bắt buộc bao gồm:

- Title
- Summary
- Source
- URL
- Topics

Nếu thiếu bất kỳ trường quan trọng nào, Knowledge Object sẽ bị loại bỏ và không thực hiện bước Embedding.

Điều này giúp ngăn chặn các dữ liệu không đầy đủ hoặc có chất lượng thấp làm ảnh hưởng đến quá trình Semantic Retrieval.

---

# 7.11 Tổng kết

Chương này đã mô tả mô hình dữ liệu cốt lõi của AI-Radar theo hướng **Knowledge-Centric**.

Thay vì lưu trữ toàn bộ bài viết gốc, hệ thống chuyển đổi chúng thành các Knowledge Object chuẩn hóa, sau đó tạo Embedding và lưu vào Qdrant để phục vụ Semantic Retrieval.

Thiết kế này giúp:

- Chuẩn hóa dữ liệu từ nhiều nguồn.
- Giảm chi phí xử lý của LLM.
- Tăng khả năng tái sử dụng tri thức.
- Đơn giản hóa việc mở rộng hệ thống trong tương lai.

Mô hình dữ liệu này cũng là nền tảng cho các chương tiếp theo, đặc biệt là **Module Design**, nơi sẽ mô tả cách từng thành phần của hệ thống tạo ra, xử lý và sử dụng các thực thể dữ liệu đã được định nghĩa trong chương này.