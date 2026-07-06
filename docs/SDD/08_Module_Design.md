# 8. Module Design

---

# 8.1 Overview

Module Design mô tả cách hệ thống AI-Radar được phân chia thành các thành phần độc lập nhằm thực hiện từng chức năng cụ thể.

Mỗi Module đại diện cho một nhóm trách nhiệm (Responsibility) rõ ràng và chỉ đảm nhiệm một mục đích duy nhất trong toàn bộ hệ thống.

Kiến trúc này tuân theo nguyên tắc:

- Single Responsibility Principle (SRP)
- Separation of Concerns (SoC)
- High Cohesion
- Low Coupling

Điều này giúp hệ thống:

- dễ bảo trì,
- dễ mở rộng,
- dễ kiểm thử,
- dễ thay thế từng thành phần mà không ảnh hưởng đến toàn bộ hệ thống.

Các Module được thiết kế theo hướng logic nghiệp vụ thay vì phụ thuộc vào cấu trúc thư mục trong mã nguồn.

Do đó, việc thay đổi cách tổ chức source code sẽ không làm thay đổi kiến trúc tổng thể.

---

# 8.2 Module Dependency

Toàn bộ AI-Radar được chia thành các Module chính sau.

```
                    Scheduler
                         │
                         ▼
                     Fetcher
                         │
                         ▼
              Knowledge Processing
                         │
                         ▼
                  Embedding Module
                         │
                         ▼
                 Vector Storage
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
 Daily Digest Module            Retrieval Module
          │                             │
          ▼                             ▼
    Groq LLM Module              Groq LLM Module
          │                             │
          ▼                             ▼
   Zalo Daily Bot             Zalo Assistant Bot
```

Các Module chỉ giao tiếp theo chiều từ trên xuống.

Không Module nào được phép truy cập ngược về tầng trước đó.

Ví dụ:

- Retrieval Module không được phép gọi Fetcher.
- Daily Digest không được phép Crawl dữ liệu.
- Zalo Integration không chứa Business Logic.

Điều này đảm bảo mỗi Module luôn có phạm vi trách nhiệm rõ ràng.

---

# 8.3 Scheduler Module

## Mục đích

Scheduler Module chịu trách nhiệm kích hoạt các tác vụ định kỳ của hệ thống.

Module này không chứa bất kỳ nghiệp vụ xử lý dữ liệu nào.

Nó chỉ đóng vai trò điều phối việc thực thi các Pipeline theo thời gian đã được cấu hình.

---

## Trách nhiệm

Scheduler Module thực hiện các nhiệm vụ sau:

- Kích hoạt Knowledge Update Pipeline.
- Kích hoạt Daily Digest Pipeline.
- Ghi nhận thời điểm thực thi.
- Theo dõi trạng thái hoàn thành của Job.

Scheduler không tham gia vào:

- Crawl dữ liệu.
- Xử lý dữ liệu.
- Gọi LLM.
- Truy vấn Qdrant.

---

## Input

Scheduler không nhận dữ liệu đầu vào từ người dùng.

Nguồn kích hoạt chủ yếu là:

- GitHub Actions.
- Cron Job.
- Scheduler cục bộ (trong môi trường phát triển).

---

## Output

Scheduler chỉ sinh ra tín hiệu thực thi (Execution Trigger).

Ví dụ:

```

06:00

↓

KnowledgeUpdateService.run()

```

---

## Phụ thuộc

Scheduler chỉ phụ thuộc vào tầng Application Service.

Không được phép gọi trực tiếp:

- Fetcher
- Retriever
- Repository
- Groq Client

---

## Xử lý lỗi

Nếu Scheduler thất bại trong việc kích hoạt Job:

- Ghi log lỗi.
- Dừng Job hiện tại.
- Không thực hiện Retry vô hạn.

Việc Retry sẽ phụ thuộc vào cơ chế của GitHub Actions hoặc Scheduler bên ngoài.

---

## Khả năng mở rộng

Trong tương lai Scheduler có thể được thay thế bằng:

- Celery Beat
- APScheduler
- Kubernetes CronJob

mà không ảnh hưởng đến Business Logic.

---

# 8.4 Fetcher Module

## Mục đích

Fetcher Module chịu trách nhiệm thu thập dữ liệu từ các nguồn công nghệ bên ngoài.

Đây là điểm bắt đầu của toàn bộ Knowledge Update Pipeline.

Fetcher chỉ có nhiệm vụ lấy dữ liệu.

Mọi hoạt động xử lý nội dung đều thuộc về Knowledge Processing Module.

---

## Trách nhiệm

Fetcher chịu trách nhiệm:

- Kết nối tới nguồn dữ liệu.
- Đọc RSS Feed.
- Gọi API công khai.
- Thu thập Metadata.
- Chuẩn hóa định dạng dữ liệu ban đầu.
- Trả về Raw Article.

Fetcher không thực hiện:

- AI Summary.
- Embedding.
- Topic Classification.
- Duplicate Detection.

---

## Input

Thông tin cấu hình nguồn dữ liệu.

Ví dụ:

- RSS URL
- API Endpoint
- Authentication Token (nếu cần)

---

## Output

Fetcher luôn trả về danh sách Raw Article.

Ví dụ:

```

List<RawArticle>

```

Các Module phía sau không cần quan tâm dữ liệu được lấy từ nguồn nào.

---

## Thiết kế

Fetcher được xây dựng theo hướng mở rộng.

```

BaseFetcher

│

├── RSSFetcher

├── GitHubFetcher

├── HuggingFaceFetcher

├── HackerNewsFetcher

└── PapersWithCodeFetcher

```

Mỗi Fetcher chỉ cài đặt cách lấy dữ liệu của riêng nguồn đó.

Các Fetcher đều trả về cùng một kiểu dữ liệu.

Điều này giúp Knowledge Processing hoạt động độc lập với nguồn dữ liệu.

---

## Nguyên tắc thiết kế

Fetcher tuân theo nguyên tắc Open/Closed Principle.

Khi bổ sung một nguồn dữ liệu mới:

- Tạo Fetcher mới.
- Đăng ký vào Source Registry.
- Không sửa Fetcher cũ.

Điều này giúp hệ thống mở rộng dễ dàng mà không làm tăng rủi ro phát sinh lỗi ở các thành phần đã ổn định.

---

## Xử lý lỗi

Nếu một nguồn dữ liệu gặp lỗi:

- Ghi log.
- Bỏ qua nguồn đó.
- Tiếp tục xử lý các nguồn còn lại.

Hệ thống không được phép dừng toàn bộ Pipeline chỉ vì một nguồn dữ liệu không phản hồi.

---

## Khả năng mở rộng

Fetcher Module được thiết kế để hỗ trợ bổ sung nguồn dữ liệu mới với chi phí thay đổi thấp.

Trong tương lai có thể bổ sung:

- TechCrunch
- Reddit
- ArXiv
- Medium
- Dev.to
- Substack
- Anthropic Blog
- OpenAI Blog

mà không cần thay đổi các Module phía sau.

---

# 8.5 Application Service Module

## Mục đích

Application Service là tầng điều phối (Orchestration Layer) của toàn bộ hệ thống AI-Radar.

Module này chịu trách nhiệm điều phối luồng xử lý giữa các Module khác, đồng thời đảm bảo các nghiệp vụ được thực hiện đúng thứ tự.

Application Service không chứa thuật toán AI, không trực tiếp thao tác với cơ sở dữ liệu và cũng không thực hiện các tác vụ tích hợp với hệ thống bên ngoài.

Thay vào đó, Module này đóng vai trò như "nhạc trưởng", điều phối các thành phần còn lại để hoàn thành từng Use Case của hệ thống.

---

## Trách nhiệm

Application Service chịu trách nhiệm:

- Điều phối Knowledge Update Pipeline.
- Điều phối Daily Digest Pipeline.
- Điều phối Question Answering Pipeline.
- Quản lý luồng thực thi giữa các Module.
- Kiểm soát thứ tự xử lý.
- Quản lý Transaction ở mức nghiệp vụ (nếu cần).

Application Service không chịu trách nhiệm:

- Crawl dữ liệu.
- Tạo Embedding.
- Sinh câu trả lời bằng LLM.
- Lưu Vector.
- Gửi tin nhắn Zalo.

---

## Các Service chính

Trong phiên bản đầu tiên của AI-Radar, hệ thống bao gồm ba Application Service chính.

### KnowledgeUpdateService

Điều phối toàn bộ quá trình cập nhật tri thức.

```
Fetcher

↓

Knowledge Processing

↓

Embedding

↓

Vector Storage
```

---

### DailyDigestService

Điều phối việc tạo bản tin công nghệ hằng ngày.

```
Retriever

↓

Groq LLM

↓

Digest Builder

↓

Zalo Bot
```

---

### QuestionAnswerService

Điều phối quá trình trả lời câu hỏi của người dùng.

```
Question

↓

Retriever

↓

Groq LLM

↓

Answer

↓

Zalo Bot
```

---

## Nguyên tắc thiết kế

Application Service không chứa Business Logic chi tiết.

Mọi thuật toán đều nằm trong các Module chuyên trách.

Application Service chỉ chịu trách nhiệm:

- gọi đúng Module,
- theo đúng thứ tự,
- xử lý kết quả,
- quản lý luồng thực thi.

Điều này giúp hệ thống dễ kiểm thử và giảm sự phụ thuộc giữa các Module.

---

## Khả năng mở rộng

Trong tương lai có thể bổ sung thêm:

- WeeklyDigestService
- TrendingAnalysisService
- OCRMonitoringService
- ResearchRecommendationService

mà không ảnh hưởng đến các Service hiện có.

---

# 8.6 Knowledge Processing Module

## Mục đích

Knowledge Processing là Module quan trọng nhất của AI-Radar.

Đây là nơi dữ liệu thô (Raw Article) được chuyển đổi thành Knowledge Object có cấu trúc và sẵn sàng cho quá trình Semantic Retrieval.

Toàn bộ giá trị của hệ thống phụ thuộc rất lớn vào chất lượng xử lý của Module này.

---

## Trách nhiệm

Knowledge Processing chịu trách nhiệm:

- Làm sạch dữ liệu.
- Chuẩn hóa nội dung.
- Loại bỏ bài viết trùng lặp.
- Trích xuất thông tin quan trọng.
- Phân loại chủ đề.
- Sinh Knowledge Object.

Module này không thực hiện:

- Semantic Search.
- Embedding.
- Lưu Vector.
- Gửi thông báo.

---

## Luồng xử lý

```
Raw Article

↓

Cleaner

↓

Normalizer

↓

Deduplicator

↓

Topic Classifier

↓

Knowledge Builder

↓

Knowledge Object
```

---

## Các thành phần chính

### Cleaner

Loại bỏ các thành phần không cần thiết.

Ví dụ:

- HTML Tag.
- Quảng cáo.
- Nội dung điều hướng.
- Footer.
- Header.
- Ký tự đặc biệt.

---

### Normalizer

Chuẩn hóa dữ liệu.

Bao gồm:

- Chuẩn hóa khoảng trắng.
- Chuẩn hóa Encoding.
- Chuẩn hóa ngày tháng.
- Chuẩn hóa URL.
- Chuẩn hóa định dạng văn bản.

---

### Deduplicator

Kiểm tra các bài viết trùng lặp.

Việc phát hiện có thể dựa trên:

- URL.
- Hash.
- Similarity Score.

Việc kiểm tra Similarity được thực hiện bằng cách truy vấn các Knowledge Object đã tồn tại trong Qdrant, không chỉ trên tập dữ liệu vừa được thu thập trong lần chạy hiện tại.

Điều này giúp tránh lưu nhiều Knowledge Object có nội dung gần như giống nhau.

---

### Topic Classifier

Phân loại Knowledge Object vào các nhóm công nghệ.

Ví dụ:

- LLM
- RAG
- AI Agent
- OCR
- MCP
- Computer Vision
- MLOps

Việc phân loại này hỗ trợ Retrieval và Daily Digest.

---

### Knowledge Builder

Đây là thành phần cuối cùng của Module.

Knowledge Builder chịu trách nhiệm:

- Sinh Summary.
- Sinh Key Takeaways.
- Sinh Keywords.
- Tính Importance Score.
- Tạo Knowledge Object hoàn chỉnh.

Knowledge Object sau đó sẽ được chuyển sang Embedding Module.

---

## Nguyên tắc thiết kế

Knowledge Processing chỉ tạo ra tri thức.

Module này không quan tâm dữ liệu sẽ được lưu ở đâu hoặc được sử dụng như thế nào.

Điều này giúp giảm sự phụ thuộc giữa các tầng trong hệ thống.

---

# 8.7 Embedding Module

## Mục đích

Embedding Module chuyển đổi Knowledge Object thành biểu diễn Vector nhằm phục vụ Semantic Retrieval.

Đây là cầu nối giữa dữ liệu nghiệp vụ và Vector Database.

---

## Trách nhiệm

Module chịu trách nhiệm:

- Sinh Embedding.
- Chuẩn hóa Vector.
- Chuẩn bị dữ liệu trước khi lưu vào Qdrant.

Module không chịu trách nhiệm:

- Truy vấn Qdrant.
- Tìm kiếm Vector.
- Gọi LLM.

---

## Input

```
Knowledge Object
```

---

## Output

```
Embedding Record
```

---

## Luồng xử lý

```
Knowledge Object

↓

Embedding Model

↓

Embedding Vector

↓

Embedding Record
```

---

## Thiết kế

Embedding Module được thiết kế độc lập với Provider.

Trong tương lai có thể thay đổi mô hình Embedding mà không ảnh hưởng đến các Module khác.

Ví dụ:

- BAAI/bge
- Nomic Embed
- Jina Embeddings
- Voyage AI

Việc thay đổi Provider chỉ ảnh hưởng đến Module này.

---

# 8.8 Vector Storage Module

## Mục đích

Vector Storage Module chịu trách nhiệm lưu trữ và truy xuất Embedding từ Qdrant.

Module này đóng vai trò là lớp giao tiếp duy nhất với Vector Database.

Các Module khác không được phép thao tác trực tiếp với Qdrant.

---

## Trách nhiệm

Module chịu trách nhiệm:

- Upsert Vector.
- Xóa Vector.
- Truy vấn Metadata.
- Thực hiện Similarity Search.

---

## Input

```
Embedding Record
```

---

## Output

```
Qdrant Collection
```

hoặc

```
List<Knowledge Object>
```

trong trường hợp truy vấn.

---

## Nguyên tắc thiết kế

Toàn bộ thao tác với Vector Database phải đi qua Module này.

Điều này giúp:

- Dễ thay đổi Vector Database.
- Dễ kiểm thử.
- Dễ mở rộng.

Nếu trong tương lai chuyển từ Qdrant sang Milvus hoặc Weaviate, chỉ cần thay đổi Module này.

---

## Xử lý lỗi

Nếu Qdrant không khả dụng:

- Ghi log lỗi.
- Hủy thao tác hiện tại.
- Không tiếp tục các bước Retrieval.

Việc Retry sẽ được cấu hình ở tầng Application Service.

---

# 8.9 Retrieval Module

## Mục đích

Retrieval Module chịu trách nhiệm truy xuất các Knowledge Object phù hợp nhất từ Knowledge Base dựa trên câu hỏi của người dùng.

Đây là thành phần cốt lõi của chức năng Question Answering và là nơi triển khai cơ chế Retrieval-Augmented Generation (RAG) của AI-Radar.

Tuy nhiên, Retrieval Module không tạo ra câu trả lời cuối cùng. Kết quả của Module chỉ là tập hợp các Knowledge Object có liên quan để cung cấp ngữ cảnh (Context) cho Large Language Model.

---

## Trách nhiệm

Retrieval Module thực hiện các nhiệm vụ sau:

- Tiếp nhận câu hỏi từ người dùng.
- Chuyển câu hỏi thành Embedding Vector.
- Thực hiện Semantic Search trên Qdrant.
- Áp dụng Metadata Filtering (nếu có).
- Lựa chọn Top-K Knowledge Object phù hợp.
- Chuẩn bị Prompt Context cho LLM.

Module này không chịu trách nhiệm:

- Sinh câu trả lời.
- Gọi API Zalo.
- Cập nhật Knowledge Base.

---

## Input

```
User Question
```

Ví dụ:

```
OCR mã nguồn mở mới nhất hiện nay là gì?
```

---

## Output

```
List<Knowledge Object>
```

Sau đó được chuyển sang LLM Module để sinh câu trả lời.

---

## Luồng xử lý

```
User Question

↓

Embedding Query

↓

Qdrant Similarity Search

↓

Top-K Knowledge Objects

↓

Metadata Filtering

↓

Prompt Context

↓

LLM
```

---

## Chiến lược Retrieval

AI-Radar sử dụng **Dense Retrieval** dựa trên Vector Embedding.

Mỗi câu hỏi sẽ được chuyển thành Vector và so sánh với các Knowledge Object trong Qdrant để tìm ra những tri thức có mức độ tương đồng cao nhất.

Trong phiên bản đầu tiên của hệ thống, Retrieval Strategy bao gồm:

- Semantic Search.
- Top-K Retrieval.
- Metadata Filtering.
- Context Construction.

---

## Metadata Filtering

Ngoài Semantic Similarity, Retrieval Module có thể lọc kết quả theo Metadata.

Ví dụ:

- Chủ đề (Topic)
- Nguồn dữ liệu (Source)
- Khoảng thời gian (Published Date)

Điều này giúp cải thiện chất lượng Context trước khi gửi cho LLM.

---

## Thiết kế

AI-Radar chỉ triển khai mức **Naive RAG+**.

Các kỹ thuật được sử dụng bao gồm:

- Dense Retrieval.
- Metadata Filtering.
- Prompt Engineering.

Một số kỹ thuật nâng cao như Query Rewrite hoặc Multi-Query Retrieval có thể được bổ sung nếu thực sự mang lại giá trị.

Các biến thể như:

- GraphRAG
- Agentic RAG
- Corrective RAG
- Self-RAG

không nằm trong phạm vi của phiên bản hiện tại do không phù hợp với mục tiêu của hệ thống.

---

## Quyết định thiết kế

AI-Radar hướng tới việc xây dựng một Knowledge Base chất lượng và đáng tin cậy.

Do đó, Retrieval Module được thiết kế đơn giản nhưng ổn định, thay vì theo đuổi các kiến trúc RAG phức tạp.

Đây là một quyết định có chủ đích nhằm cân bằng giữa chất lượng kết quả, độ phức tạp của hệ thống và khả năng bảo trì.

---

# 8.10 LLM Module

## Mục đích

LLM Module chịu trách nhiệm tương tác với Large Language Model thông qua Groq API.

Module này không trực tiếp xử lý dữ liệu mà chỉ nhận Context từ các Module khác để sinh ra kết quả cuối cùng.

---

## Trách nhiệm

LLM Module thực hiện:

- Sinh Summary.
- Sinh Key Takeaways.
- Phân loại Topic.
- Trả lời câu hỏi.
- Sinh Daily Digest.

Module không chịu trách nhiệm:

- Retrieval.
- Embedding.
- Lưu trữ dữ liệu.
- Gửi tin nhắn.

---

## Input

Input của Module bao gồm:

- Prompt Template.
- Context.
- User Question (nếu có).

---

## Output

Output là văn bản do LLM sinh ra.

Ví dụ:

- Summary.
- Daily Digest.
- Answer.
- Topic Classification.

---

## Prompt Management

Prompt không được Hard-code trong mã nguồn.

Toàn bộ Prompt được quản lý tập trung trong thư mục:

```
prompts/
```

Điều này giúp:

- Dễ bảo trì.
- Dễ tinh chỉnh Prompt.
- Không ảnh hưởng Business Logic.

---

## LLM Provider

Trong phiên bản hiện tại, AI-Radar sử dụng Groq API làm LLM Provider.

Việc lựa chọn Groq dựa trên các tiêu chí:

- Hiệu năng phản hồi cao.
- Free Tier phù hợp với nhu cầu cá nhân.
- Dễ tích hợp thông qua API chuẩn.

Thiết kế Module cho phép thay thế Provider khác trong tương lai mà không ảnh hưởng đến các Module còn lại.

---

# 8.11 Daily Digest Module

## Mục đích

Daily Digest Module chịu trách nhiệm tạo bản tin công nghệ hằng ngày từ Knowledge Base.

Đây là chức năng quan trọng nhất của AI-Radar và phản ánh đúng ý nghĩa của tên gọi "Radar" — liên tục quét, phát hiện và tổng hợp các xu hướng AI mới.

---

## Trách nhiệm

Module thực hiện:

- Lựa chọn Knowledge Object nổi bật.
- Sắp xếp theo mức độ quan trọng.
- Gom nhóm theo chủ đề.
- Sinh bản tóm tắt.
- Chuẩn bị nội dung gửi qua Zalo.

---

## Input

```
Knowledge Objects
```

được truy xuất từ Qdrant.

---

## Output

```
Daily Digest
```

sẵn sàng gửi tới người dùng.

---

## Luồng xử lý

```
Knowledge Objects

↓

Ranking

↓

Topic Grouping

↓

Prompt Builder

↓

Groq

↓

Daily Digest

↓

Zalo Bot
```

---

## Quyết định thiết kế

Daily Digest không Crawl dữ liệu.

Daily Digest không Retrieval theo câu hỏi.

Module chỉ làm việc trên Knowledge Base đã được xây dựng trước đó.

Việc tách biệt hai Pipeline giúp hệ thống đơn giản hơn và dễ bảo trì.

---

# 8.12 Zalo Integration Module

## Mục đích

Zalo Integration Module là cầu nối giữa AI-Radar và người dùng cuối.

Module này chịu trách nhiệm gửi thông báo và tiếp nhận câu hỏi thông qua Zalo Official Account.

---

## Trách nhiệm

Module thực hiện:

- Gửi Daily Digest.
- Nhận câu hỏi từ người dùng.
- Chuyển câu hỏi tới Question Answer Service.
- Gửi câu trả lời.

---

## Nguyên tắc thiết kế

Module này không chứa Business Logic.

Mọi xử lý nghiệp vụ đều được thực hiện ở tầng Application Service.

Điều này giúp dễ dàng mở rộng sang các nền tảng khác như:

- Telegram
- Discord
- Slack

mà không cần thay đổi Logic của hệ thống.

---

# 8.13 Chiến lược xử lý lỗi

AI-Radar áp dụng nguyên tắc **Fail Gracefully**.

Khi một Module gặp lỗi, hệ thống cố gắng cô lập lỗi thay vì dừng toàn bộ Pipeline.

Ví dụ:

- Một nguồn RSS lỗi không làm dừng toàn bộ quá trình cập nhật.
- Một bài viết lỗi không ảnh hưởng đến các bài viết khác.
- Một Knowledge Object lỗi không làm dừng quá trình Embedding của các Knowledge Object còn lại.

Toàn bộ lỗi đều được ghi Log để phục vụ việc kiểm tra và bảo trì.

---

## Retry Strategy

Retry chỉ được áp dụng với các lỗi có khả năng phục hồi.

Ví dụ:

- Timeout.
- Temporary Network Failure.
- Rate Limit.

Các lỗi liên quan đến dữ liệu sẽ không Retry mà được ghi nhận và bỏ qua.

---

# 8.14 Tổng kết

Chương này đã mô tả thiết kế của các Module chính trong AI-Radar.

Mỗi Module được xây dựng theo nguyên tắc **Single Responsibility**, chỉ đảm nhận một vai trò duy nhất trong hệ thống.

Việc phân tách rõ ràng giữa Scheduler, Fetcher, Knowledge Processing, Embedding, Retrieval, LLM, Daily Digest và Integration giúp hệ thống có kiến trúc đơn giản, dễ bảo trì và dễ mở rộng.

Kiến trúc Module cũng phản ánh đúng định hướng thiết kế của AI-Radar: xây dựng một nền tảng thu thập, chuẩn hóa và khai thác tri thức AI đáng tin cậy, trong đó Daily Digest và Semantic Question Answering là hai khả năng chính được phát triển trên cùng một Knowledge Base.

---