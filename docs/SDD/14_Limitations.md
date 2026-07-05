# 14. Limitations

---

# 14.1 Mục đích

Chương này mô tả các giới hạn đã được chấp nhận trong thiết kế của AI-Radar.

Không phải mọi hạn chế đều là thiếu sót.

Nhiều giới hạn là kết quả của quá trình đánh giá Trade-off nhằm giữ cho hệ thống:

- đơn giản,
- dễ bảo trì,
- phù hợp với mục tiêu của dự án.

Việc xác định rõ các giới hạn giúp tránh hiểu nhầm rằng hệ thống còn "thiếu tính năng", trong khi thực tế đó là các quyết định thiết kế có chủ đích.

---

# 14.2 Triết lý

AI-Radar không hướng tới việc giải quyết mọi bài toán liên quan đến AI hoặc Knowledge Management.

Phiên bản đầu tiên tập trung vào:

- Thu thập tri thức.
- Chuẩn hóa tri thức.
- Xây dựng Knowledge Base.
- Tổng hợp Daily AI Intelligence.
- Semantic Question Answering.

Mọi khả năng nằm ngoài phạm vi này đều được xem xét cẩn trọng trước khi bổ sung.

---

# 14.3 Knowledge Scope

AI-Radar chỉ xử lý các nguồn tri thức được cấu hình trước.

Ví dụ:

- RSS Feed.
- AI Blog.
- GitHub Repository.
- Hugging Face.
- Hacker News.

Hệ thống không tự động khám phá nguồn dữ liệu mới trên Internet.

Việc bổ sung nguồn dữ liệu mới cần được cấu hình và tích hợp rõ ràng.

---

# 14.4 Language Support

Phiên bản hiện tại không hướng tới việc xử lý đa ngôn ngữ một cách toàn diện.

Chất lượng của quá trình:

- Summary.
- Classification.
- Retrieval.
- Question Answering.

phụ thuộc vào ngôn ngữ của dữ liệu và khả năng của mô hình LLM được sử dụng.

Việc tối ưu cho nhiều ngôn ngữ không nằm trong phạm vi của phiên bản đầu tiên.

---

# 14.5 Retrieval Capability

AI-Radar sử dụng chiến lược Retrieval đơn giản.

Bao gồm:

- Dense Retrieval.
- Top-K Search.
- Metadata Filtering.

Hệ thống không triển khai:

- GraphRAG.
- Multi-hop Retrieval.
- Hybrid Search phức tạp.
- Query Planning.
- Knowledge Graph.

Đây là quyết định nhằm giữ kiến trúc đơn giản và phù hợp với mục tiêu của dự án.

---

# 14.6 Real-time Processing

AI-Radar không phải hệ thống xử lý thời gian thực.

Knowledge được cập nhật theo lịch thông qua Scheduler.

Do đó:

- Thông tin mới có thể xuất hiện sau một khoảng thời gian nhất định.
- Daily Digest phản ánh dữ liệu đã được xử lý, không phải dữ liệu tức thời.

Đây là Trade-off giữa tính kịp thời và chi phí vận hành.

---

# 14.7 Scalability

Phiên bản hiện tại không hướng tới khả năng mở rộng ở quy mô lớn.

Hệ thống không hỗ trợ:

- Distributed Deployment.
- Horizontal Scaling.
- Multi-node Processing.
- Event Streaming.
- Microservices.

Các khả năng này chỉ được xem xét khi xuất hiện nhu cầu thực tế.

---

# 14.8 User Management

AI-Radar không xây dựng hệ thống quản lý người dùng.

Do đó không bao gồm:

- User Registration.
- Authentication.
- Authorization.
- Role Management.
- Permission Management.

Hệ thống hiện chỉ tập trung vào việc cung cấp tri thức thông qua các kênh tích hợp.

---

# 14.9 Knowledge Management

Knowledge Base được quản lý hoàn toàn bởi hệ thống.

Phiên bản đầu tiên không hỗ trợ:

- Chỉnh sửa Knowledge thủ công.
- Xóa từng Knowledge Object.
- Quản lý phiên bản của Knowledge.
- Giao diện quản trị dữ liệu.

Việc quản lý tri thức được thực hiện thông qua Pipeline xử lý tự động.

---

# 14.10 AI Capability

Chất lượng đầu ra của AI-Radar phụ thuộc vào:

- Chất lượng dữ liệu đầu vào.
- Chất lượng Knowledge Object.
- Khả năng của Embedding Model.
- Khả năng của LLM.

Hệ thống không đảm bảo:

- Câu trả lời luôn chính xác tuyệt đối.
- Summary luôn đầy đủ.
- Topic Classification luôn chính xác.

AI-Radar hỗ trợ việc tiếp cận tri thức, không thay thế quá trình đánh giá của con người.

---

# 14.11 External Dependency

AI-Radar phụ thuộc vào nhiều dịch vụ bên ngoài.

Ví dụ:

- Groq API.
- Qdrant.
- RSS Sources.
- GitHub.
- Hugging Face.
- Zalo Official Account.

Nếu một dịch vụ bên ngoài thay đổi API hoặc ngừng hoạt động, một phần chức năng của hệ thống có thể bị ảnh hưởng.

Đây là giới hạn chung của các hệ thống tích hợp nhiều dịch vụ.

---

# 14.12 Operational Limitations

Hệ thống giả định môi trường triển khai ổn định.

Các yếu tố ngoài khả năng kiểm soát bao gồm:

- Mất kết nối Internet.
- Giới hạn API của nhà cung cấp.
- Nguồn dữ liệu thay đổi cấu trúc.
- Dịch vụ bên ngoài tạm thời không khả dụng.

Các tình huống này được xử lý theo cơ chế Retry hoặc Error Handling đã được thiết kế, nhưng không thể loại bỏ hoàn toàn.

---

# 14.13 Future Evolution

Một số giới hạn hiện tại có thể được loại bỏ trong các phiên bản sau nếu xuất hiện nhu cầu thực tế.

Ví dụ:

- Bổ sung nguồn dữ liệu mới.
- Hỗ trợ nhiều nền tảng nhắn tin.
- Mở rộng Retrieval.
- Hỗ trợ nhiều Embedding Model.
- Nâng cấp chiến lược Knowledge Processing.

Việc mở rộng chỉ được thực hiện khi mang lại giá trị rõ ràng và không làm mâu thuẫn với các nguyên tắc thiết kế đã thống nhất.

---

# 14.14 Tổng kết

Chương này đã mô tả các giới hạn hiện tại của AI-Radar và lý do tồn tại của chúng.

Những giới hạn này không phải là các thiếu sót của hệ thống, mà là kết quả của các quyết định thiết kế dựa trên mục tiêu, phạm vi và các Trade-off đã được thống nhất ngay từ đầu.

Việc xác định rõ các giới hạn giúp duy trì kiến trúc đơn giản, dễ bảo trì và tránh mở rộng hệ thống vượt quá nhu cầu thực tế của dự án.

---