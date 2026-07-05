# 12. Testing Strategy

---

# 12.1 Mục đích

Chương này mô tả chiến lược kiểm thử của AI-Radar.

Mục tiêu của việc kiểm thử không chỉ là phát hiện lỗi, mà còn đảm bảo:

- Hệ thống hoạt động đúng theo Software Design Document.
- Các Module có thể được thay đổi mà không gây ảnh hưởng ngoài mong muốn.
- Quá trình mở rộng hệ thống trong tương lai vẫn duy trì được tính ổn định.

Chiến lược kiểm thử được xây dựng dựa trên kiến trúc Module và nguyên tắc Loose Coupling đã được trình bày trong các chương trước.

---

# 12.2 Triết lý kiểm thử

AI-Radar áp dụng các nguyên tắc sau:

- Kiểm thử theo Module.
- Kiểm thử theo trách nhiệm.
- Ưu tiên Unit Test trước Integration Test.
- Không phụ thuộc vào dịch vụ bên ngoài trong quá trình Unit Test.
- Chỉ kiểm thử những hành vi thuộc trách nhiệm của Module.

Mỗi Module chỉ chịu trách nhiệm kiểm thử phần logic của chính nó.

---

# 12.3 Testing Scope

Việc kiểm thử bao gồm các thành phần chính của hệ thống:

- Core Utilities.
- Fetchers.
- Knowledge Processing.
- Embedding.
- Retrieval.
- Services.
- Pipelines.
- Integration Layer.

Các thành phần bên ngoài như Groq API hoặc Zalo Official Account không thuộc phạm vi kiểm thử trực tiếp mà sẽ được giả lập khi cần thiết.

---

# 12.4 Unit Testing

Unit Test là lớp kiểm thử quan trọng nhất của AI-Radar.

Mục tiêu là xác minh từng Module hoạt động đúng khi được cung cấp đầu vào hợp lệ và không hợp lệ.

Ví dụ:

- Cleaner xử lý đúng dữ liệu đầu vào.
- Keyword Extractor tạo đúng danh sách từ khóa.
- Topic Classifier phân loại đúng chủ đề.
- Retriever trả về đúng tập Knowledge Object.
- Formatter tạo đúng nội dung gửi Zalo.

Mỗi Unit Test chỉ kiểm thử một hành vi cụ thể.

---

# 12.5 Integration Testing

Integration Test xác minh khả năng phối hợp giữa nhiều Module.

Ví dụ:

Knowledge Processing

↓

Embedding

↓

Qdrant

hoặc

Retriever

↓

Prompt Builder

↓

Answer Generator

Các bài kiểm thử này tập trung vào luồng dữ liệu giữa các Module thay vì logic chi tiết của từng Module.

---

# 12.6 Pipeline Testing

Hai Pipeline chính của AI-Radar cần được kiểm thử độc lập.

## Knowledge Update Pipeline

Kiểm tra toàn bộ quá trình:

- Thu thập dữ liệu.
- Chuẩn hóa.
- Xây dựng Knowledge Object.
- Sinh Embedding.
- Lưu vào Qdrant.

Mục tiêu là đảm bảo Pipeline hoàn thành đầy đủ và dữ liệu cuối cùng nhất quán.

---

## Daily Digest Pipeline

Kiểm tra quá trình:

- Truy xuất Knowledge mới.
- Tổng hợp nội dung.
- Sinh Daily Digest.
- Gửi tới Zalo.

Pipeline cần đảm bảo không bỏ sót dữ liệu hợp lệ.

---

## Question Answering Pipeline

Kiểm tra quá trình:

- Nhận câu hỏi.
- Retrieval.
- Prompt Building.
- Gọi LLM.
- Trả lời người dùng.

Mục tiêu là đảm bảo luồng xử lý hoàn chỉnh hoạt động đúng.

---

# 12.7 Mocking Strategy

Các dịch vụ bên ngoài cần được Mock trong quá trình kiểm thử.

Bao gồm:

- Groq API.
- Qdrant (khi không cần kiểm thử Integration).
- RSS Feed.
- GitHub API.
- Hugging Face API.
- Zalo API.

Việc Mock giúp:

- giảm chi phí,
- tăng tốc độ kiểm thử,
- tránh phụ thuộc Internet,
- tạo kết quả ổn định.

---

# 12.8 Test Data

Dữ liệu kiểm thử cần đại diện cho các tình huống thực tế.

Ví dụ:

- Article hợp lệ.
- Article thiếu Title.
- RSS Feed rỗng.
- Nội dung quá dài.
- URL không hợp lệ.
- Knowledge Object thiếu Metadata.
- Retrieval không trả về kết quả.

Các bộ dữ liệu này giúp đánh giá khả năng xử lý của hệ thống trong cả trường hợp bình thường và ngoại lệ.

---

# 12.9 Error Scenario Testing

Ngoài các trường hợp thành công, hệ thống cần được kiểm thử với các tình huống lỗi.

Ví dụ:

- RSS Source không phản hồi.
- Groq API Timeout.
- Embedding thất bại.
- Không thể kết nối Qdrant.
- Zalo API trả về lỗi.
- Prompt vượt quá giới hạn Context.

Mục tiêu là đảm bảo hệ thống xử lý lỗi theo đúng chiến lược đã thiết kế mà không làm dừng toàn bộ Pipeline nếu không cần thiết.

---

# 12.10 Regression Testing

Sau mỗi thay đổi quan trọng, cần thực hiện Regression Test để đảm bảo:

- Chức năng cũ vẫn hoạt động.
- Không phát sinh lỗi ngoài ý muốn.
- Kiến trúc hiện tại không bị ảnh hưởng.

Regression Test đặc biệt quan trọng đối với:

- Knowledge Processing.
- Retrieval.
- Daily Digest.
- Question Answering.

---

# 12.11 Manual Testing

Bên cạnh kiểm thử tự động, một số chức năng cần được kiểm thử thủ công.

Ví dụ:

- Chất lượng Summary.
- Chất lượng Daily Digest.
- Tính dễ đọc của câu trả lời.
- Định dạng tin nhắn trên Zalo.
- Chất lượng Retrieval trong các tình huống thực tế.

Các nội dung liên quan đến LLM cần được đánh giá bằng con người vì không thể xác minh hoàn toàn bằng kiểm thử tự động.

---

# 12.12 Acceptance Criteria

Một Module được xem là đạt yêu cầu khi:

- Hoàn thành đúng trách nhiệm.
- Xử lý đúng dữ liệu hợp lệ.
- Xử lý phù hợp dữ liệu không hợp lệ.
- Không làm ảnh hưởng tới các Module khác.
- Tuân thủ các nguyên tắc thiết kế của hệ thống.

Một Pipeline được xem là đạt yêu cầu khi hoàn thành toàn bộ luồng xử lý theo đúng thiết kế và tạo ra kết quả nhất quán.

---

# 12.13 Test Maintainability

Các bài kiểm thử cần được thiết kế với khả năng bảo trì lâu dài.

Nguyên tắc bao gồm:

- Mỗi bài kiểm thử chỉ kiểm tra một mục tiêu.
- Tránh phụ thuộc giữa các Test Case.
- Dễ đọc.
- Dễ mở rộng khi hệ thống phát triển.

Khi thay đổi Implementation nhưng không thay đổi hành vi của Module, các Test Case tương ứng không nên cần chỉnh sửa.

---

# 12.14 Tổng kết

Chương này đã mô tả chiến lược kiểm thử của AI-Radar dựa trên kiến trúc Module và các Pipeline của hệ thống.

Thay vì tập trung vào việc đạt độ bao phủ kiểm thử cao nhất, AI-Radar ưu tiên xây dựng các bài kiểm thử có giá trị, phản ánh đúng trách nhiệm của từng Module và đảm bảo tính ổn định của hai Pipeline cốt lõi: Knowledge Update và Question Answering.

Chiến lược này giúp hệ thống duy trì khả năng bảo trì, mở rộng và phát triển lâu dài mà vẫn giữ được tính đơn giản phù hợp với mục tiêu của dự án.

---