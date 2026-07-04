# 9. Data Design

## 9.1 Mục đích

Chương này mô tả thiết kế dữ liệu của hệ thống AI-Radar.

Nếu Chương 8 tập trung vào việc **Module nào chịu trách nhiệm xử lý**, thì Chương 9 tập trung vào **Module đó xử lý loại dữ liệu gì**.

Mục tiêu của chương này là chuẩn hóa toàn bộ các đối tượng dữ liệu (Data Object) được sử dụng trong hệ thống nhằm đảm bảo:

- Dữ liệu nhất quán.
- Giảm sự phụ thuộc giữa các Module.
- Dễ mở rộng trong tương lai.
- Dễ bảo trì.
- Thuận tiện khi triển khai mã nguồn.

Toàn bộ Pipeline của AI-Radar đều xoay quanh việc chuyển đổi dữ liệu từ dạng thô thành tri thức có cấu trúc.

---

## 9.2 Triết lý thiết kế dữ liệu

AI-Radar áp dụng mô hình:

```
Raw Data

↓

Processed Data

↓

Knowledge Object

↓

Vector Representation

↓

Knowledge Retrieval
```

Điều này có nghĩa là mỗi giai đoạn của Pipeline sẽ tạo ra một phiên bản dữ liệu mới thay vì chỉnh sửa trực tiếp dữ liệu cũ.

Thiết kế này mang lại các lợi ích:

- Dễ Debug.
- Dễ Trace Pipeline.
- Giảm Coupling.
- Dễ mở rộng.

Mỗi Object chỉ đại diện cho một trạng thái dữ liệu duy nhất.

---

## 9.3 Data Flow

Luồng dữ liệu tổng thể của hệ thống:

```
RSS / Website

↓

Raw Article

↓

Cleaned Article

↓

Knowledge Object

↓

Embedding Vector

↓

Qdrant

↓

Retriever

↓

Prompt Context

↓

LLM

↓

Daily Digest / Answer
```

Đây là luồng dữ liệu xuyên suốt toàn bộ AI-Radar.

---

## 9.4 Data Classification

AI-Radar chia dữ liệu thành bốn nhóm chính.

### Raw Data

Dữ liệu thu thập trực tiếp từ Internet.

Ví dụ:

- RSS Feed
- HTML
- Markdown
- Blog Article

Đây là dữ liệu chưa qua xử lý.

---

### Processed Data

Dữ liệu sau khi:

- Parse
- Clean
- Normalize
- Remove Noise

Nhưng vẫn chưa trở thành Knowledge.

---

### Knowledge Data

Đây là dữ liệu quan trọng nhất của hệ thống.

Knowledge Object là kết quả sau khi LLM và Knowledge Processing hoàn thành.

Knowledge Data sẽ được lưu trữ trong Qdrant.

---

### Generated Data

Bao gồm:

- Daily Digest
- Question Answer
- Summary
- Topic Classification

Đây là dữ liệu được sinh ra bởi LLM.

---

## 9.5 Data Lifecycle

Mỗi dữ liệu trong AI-Radar đều trải qua vòng đời sau.

```
Collected

↓

Processed

↓

Embedded

↓

Stored

↓

Retrieved

↓

Consumed
```

Một Knowledge Object chỉ được coi là hoàn chỉnh khi đã hoàn thành toàn bộ Pipeline.

---

## 9.6 Raw Article

Raw Article là dữ liệu đầu tiên được Fetcher thu thập.

Raw Article chỉ phản ánh nội dung từ nguồn gốc.

Không chứa:

- Summary
- Topic
- Embedding
- Knowledge Metadata

---

### Thuộc tính

Một Raw Article bao gồm:

- Title
- URL
- Source
- Published Date
- Author (nếu có)
- Raw Content
- Retrieved Time

---

### Mục đích

Raw Article chỉ tồn tại trong quá trình xử lý.

Sau khi Knowledge Object được tạo thành, Raw Article có thể được giải phóng khỏi bộ nhớ.

Hệ thống không lưu trữ lâu dài Raw Article.

Điều này phù hợp với mục tiêu của AI-Radar là xây dựng Knowledge Base thay vì Archive Website.

---

## 9.7 Knowledge Object

Knowledge Object là thực thể quan trọng nhất của AI-Radar.

Toàn bộ hệ thống đều xoay quanh Knowledge Object.

Knowledge Object đại diện cho một đơn vị tri thức đã được chuẩn hóa.

---

### Thành phần

Một Knowledge Object bao gồm:

- Knowledge ID
- Title
- Summary
- Main Content
- Key Takeaways
- Topics
- Tags
- Source Name
- Source URL
- Published Date
- Retrieved Date
- Language
- Embedding ID
- Metadata

---

### Đặc điểm

Knowledge Object:

- Không chứa HTML.
- Không chứa Script.
- Không chứa quảng cáo.
- Không chứa dữ liệu trình bày.

Knowledge Object chỉ chứa tri thức.

---

## 9.8 Metadata Design

Metadata giúp tăng khả năng Retrieval.

Một Metadata có thể bao gồm:

- Source
- Category
- Framework
- AI Domain
- Published Date
- Retrieved Date
- Language

Ví dụ:

```
Source

↓

OpenAI Blog

Category

↓

LLM

Framework

↓

GPT

Published

↓

2026-01-15
```

Metadata không tham gia Embedding nhưng hỗ trợ Filtering.

---

## 9.9 Embedding Data

Embedding đại diện cho biểu diễn Vector của Knowledge Object.

Embedding không được xem là dữ liệu nghiệp vụ.

Nó chỉ phục vụ Semantic Search.

---

### Quan hệ

```
Knowledge Object

1

↓

1

Embedding
```

Mỗi Knowledge Object chỉ có một Embedding trong phiên bản hiện tại.

---

### Nguyên tắc

Embedding được tạo sau khi Knowledge Object hoàn tất.

Nếu Knowledge thay đổi đáng kể, Embedding phải được sinh lại để đảm bảo tính nhất quán.

---

## 9.10 Qdrant Collection Design

AI-Radar sử dụng một Collection chính để lưu trữ tri thức.

Mỗi Point trong Qdrant bao gồm:

- Point ID
- Embedding Vector
- Payload

Payload lưu Metadata và các thông tin cần thiết phục vụ Retrieval.

Thiết kế này giúp:

- Semantic Search.
- Metadata Filtering.
- Top-K Retrieval.

không cần truy cập thêm Database khác.

---

## 9.11 Prompt Data

Prompt được xem là dữ liệu cấu hình.

Prompt không nằm trong Source Code.

Prompt được quản lý riêng nhằm:

- Dễ thay đổi.
- Dễ thử nghiệm.
- Không ảnh hưởng Business Logic.

Các Prompt bao gồm:

- Summary Prompt
- Classification Prompt
- Daily Digest Prompt
- Question Answer Prompt

---

## 9.12 Configuration Data

Các thông tin cấu hình bao gồm:

- RSS Sources
- Scheduler Time
- Groq API Configuration
- Embedding Model
- Retrieval Top-K
- Chunk Size
- Chunk Overlap
- Qdrant Configuration

Configuration được tách khỏi mã nguồn để thuận tiện triển khai ở nhiều môi trường khác nhau.

---

## 9.13 Data Validation

Mỗi Object trước khi chuyển sang Module tiếp theo đều cần được kiểm tra.

Ví dụ:

Raw Article cần:

- Có Title.
- Có URL.
- Có Content.

Knowledge Object cần:

- Có Summary.
- Có Metadata.
- Có Source.

Embedding cần:

- Sinh thành công.
- Đúng Dimension.
- Không rỗng.

Nếu không đạt yêu cầu, Object sẽ không tiếp tục Pipeline.

---

## 9.14 Data Relationship

Quan hệ giữa các Object:

```
Raw Article

↓

Processed Article

↓

Knowledge Object

↓

Embedding

↓

Qdrant Point

↓

Retrieved Context

↓

LLM Response
```

Mỗi Object chỉ phụ thuộc vào Object ngay trước nó.

Điều này giúp giảm Coupling giữa các Module.

---

## 9.15 Thiết kế mở rộng

Thiết kế dữ liệu hiện tại cho phép mở rộng trong tương lai mà không làm thay đổi cấu trúc hiện có.

Ví dụ:

Có thể bổ sung:

- Image Metadata
- Video Metadata
- PDF Knowledge
- Research Paper
- GitHub Repository
- YouTube Transcript

Tất cả đều có thể chuyển đổi thành cùng một Knowledge Object.

Nhờ đó, Retrieval Pipeline không cần thay đổi.

Đây là một quyết định thiết kế nhằm đảm bảo khả năng mở rộng của AI-Radar trong dài hạn.

---

## 9.16 Tổng kết

Chương này đã định nghĩa toàn bộ các đối tượng dữ liệu và vòng đời dữ liệu trong AI-Radar.

Thay vì xử lý trực tiếp dữ liệu từ Internet, hệ thống chuyển đổi dữ liệu qua nhiều giai đoạn để tạo ra một Knowledge Object chuẩn hóa. Đây là trung tâm của toàn bộ kiến trúc AI-Radar và là nền tảng cho cả hai chức năng chính: Daily AI Intelligence và Semantic Question Answering.

Việc chuẩn hóa dữ liệu giúp giảm sự phụ thuộc giữa các Module, tăng khả năng bảo trì và tạo điều kiện mở rộng hệ thống trong tương lai mà không cần thay đổi các Pipeline cốt lõi.

---
