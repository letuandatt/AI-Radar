# Folder Structure Design

---

# 1. Mục đích

Tài liệu này mô tả cấu trúc thư mục chính thức của dự án **AI-Radar**.

Khác với Software Design Document (SDD), tài liệu này tập trung vào cách tổ chức mã nguồn nhằm hiện thực hóa các quyết định thiết kế đã được thống nhất.

Mục tiêu của tài liệu là:

- Chuẩn hóa cấu trúc dự án.
- Xác định trách nhiệm của từng thư mục.
- Định nghĩa quy tắc tổ chức source code.
- Làm cơ sở cho Architecture và Implementation.

Tài liệu này được xem là **Source of Truth** cho toàn bộ cấu trúc mã nguồn của AI-Radar.

---

# 2. Design Philosophy

Cấu trúc thư mục của AI-Radar được xây dựng dựa trên các nguyên tắc sau.

## Layer First

Source code được tổ chức theo Layer thay vì theo Feature.

Ví dụ:

- Fetchers
- Knowledge
- Services
- Integrations

thay vì

- Daily Digest
- Chatbot
- RSS

Điều này giúp các Module có thể được tái sử dụng giữa nhiều Pipeline.

---

## Single Responsibility

Mỗi thư mục chỉ đại diện cho một nhóm trách nhiệm.

Ví dụ:

- `fetchers/` chỉ thu thập dữ liệu.
- `knowledge/` chỉ xử lý tri thức.
- `services/` chỉ điều phối nghiệp vụ.
- `integrations/` chỉ giao tiếp với hệ thống bên ngoài.

Không có thư mục nào thực hiện nhiều vai trò khác nhau.

---

## Knowledge-Centric

Toàn bộ source code xoay quanh **Knowledge Object**.

Hai Pipeline chính:

- Knowledge Update
- Question Answering

đều sử dụng cùng một Knowledge Base.

Do đó cấu trúc thư mục cũng phản ánh kiến trúc này.

---

## Extensibility

Việc bổ sung:

- Fetcher mới
- Integration mới
- Knowledge Processor mới

không yêu cầu thay đổi cấu trúc hiện tại.

---

## Documentation First

Mọi thay đổi đối với cấu trúc thư mục cần được cập nhật trong tài liệu này trước khi thay đổi mã nguồn.

---

# 3. High-Level Structure

```text
ai-radar/
│
├── app/
├── docs/
├── scripts/
├── tests/
│
├── .github/
├── requirements.txt
├── pyproject.toml
├── README.md
└── ...
```

Các thư mục cấp cao được phân chia theo vai trò.

| Thư mục | Vai trò |
|----------|----------|
| app | Source code của hệ thống |
| docs | Tài liệu thiết kế và hướng dẫn |
| scripts | Công cụ hỗ trợ vận hành |
| tests | Kiểm thử |
| .github | Workflow CI/CD |

---

# 4. Application Structure

Toàn bộ Business Logic được đặt trong thư mục `app/`.

```text
app/
│
├── config/
├── core/
├── fetchers/
├── integrations/
├── knowledge/
├── models/
├── pipelines/
├── services/
├── storage/
├── vectorstores/
└── main.py
```

Mỗi thư mục đại diện cho một Module độc lập trong hệ thống.

---

# 5. Module Mapping

| SDD Module | Source Folder |
|------------|---------------|
| Configuration | config/ |
| Core Infrastructure | core/ |
| Fetchers | fetchers/ |
| External Integrations | integrations/ |
| Knowledge Processing | knowledge/ |
| Data Models | models/ |
| Pipelines | pipelines/ |
| Business Services | services/ |
| Vector Storage & Retrieval | vectorstores/ |
| Local Storage | storage/ |

Việc tổ chức này đảm bảo mỗi Module trong SDD có một vị trí rõ ràng trong mã nguồn.

---

# 6. Directory Responsibilities

## config/

Chứa toàn bộ cấu hình của hệ thống.

Ví dụ:

- Settings
- Constants
- Prompt Templates

Không chứa Business Logic.

---

## core/

Chứa các thành phần hạ tầng dùng chung.

Ví dụ:

- Logger
- Scheduler
- Exception
- Utility

Các Module khác có thể sử dụng nhưng không được chứa logic nghiệp vụ.

---

## fetchers/

Chịu trách nhiệm thu thập dữ liệu từ bên ngoài.

Ví dụ:

- RSS
- GitHub
- Hugging Face
- Hacker News

Fetcher chỉ trả về dữ liệu gốc.

Không xử lý tri thức.

---

## integrations/

Chứa toàn bộ Integration với dịch vụ bên ngoài.

Ví dụ:

- Groq
- Zalo

Các Integration chỉ đóng vai trò Adapter giữa hệ thống và dịch vụ bên ngoài.

---

## knowledge/

Chịu trách nhiệm xây dựng Knowledge Object.

Bao gồm:

- Cleaning
- Keyword Extraction
- Topic Classification
- Summarization
- Answer Generation

Không thực hiện lưu trữ dữ liệu.

---

## models/

Định nghĩa các đối tượng dữ liệu của hệ thống.

Ví dụ:

- Article
- Knowledge
- Digest
- Response

Model không chứa Business Logic.

---

## pipelines/

Điều phối các Pipeline của hệ thống.

Ví dụ:

- Knowledge Update
- Daily Digest

Pipeline mô tả trình tự xử lý, không chứa chi tiết hiện thực của từng bước.

---

## services/

Chứa Business Logic.

Service phối hợp nhiều Module để hoàn thành một nghiệp vụ.

Service không trực tiếp giao tiếp với API bên ngoài.

---

## storage/

Chứa dữ liệu cục bộ phục vụ vận hành.

Ví dụ:

- History
- Cache
- Temporary Data

Không phải Knowledge Base chính.

---

## vectorstores/

Quản lý Embedding và Semantic Retrieval.

Bao gồm:

- Qdrant
- Retriever

Đây là lớp truy cập Vector Database của hệ thống.

---

# 7. Dependency Rules

Các Module chỉ được phụ thuộc theo hướng từ trên xuống.

```text
Pipelines
        │
        ▼
Services
        │
        ▼
Knowledge
        │
        ▼
Vector Stores
        │
        ▼
Integrations
```

Các nguyên tắc chính:

- Fetcher không phụ thuộc Service.
- Knowledge không phụ thuộc Pipeline.
- Model không phụ thuộc Module khác.
- Integration không chứa Business Logic.
- Core không phụ thuộc Business Module.

Mọi Dependency ngược chiều cần được xem xét trước khi triển khai.

---

# 8. Naming Convention

Các quy tắc đặt tên:

- Thư mục sử dụng chữ thường.
- Module sử dụng chữ thường.
- File sử dụng `snake_case`.
- Tên thể hiện rõ trách nhiệm.

Ví dụ:

```text
github.py
rss.py
client.py
settings.py
digest_service.py
```

Tránh các tên chung chung như:

```text
helper.py
common.py
utils2.py
new.py
```

---

# 9. Growth Rules

Khi mở rộng hệ thống:

- Fetcher mới → `fetchers/`
- Integration mới → `integrations/`
- Knowledge Processor mới → `knowledge/`
- Service mới → `services/`
- Pipeline mới → `pipelines/`
- Data Model mới → `models/`

Không tạo thư mục mới nếu chức năng vẫn thuộc trách nhiệm của Module hiện có.

---

# 10. Final Directory Structure

```text
ai-radar/
│
├── .github/
│   └── workflows/
│
├── app/
│   ├── config/
│   │   ├── constants.py
│   │   ├── prompts.py
│   │   └── settings.py
│   │
│   ├── core/
│   │   ├── exceptions.py
│   │   ├── logger.py
│   │   ├── scheduler.py
│   │   └── utils.py
│   │
│   ├── fetchers/
│   │   ├── base.py
│   │   ├── github.py
│   │   ├── hackernews.py
│   │   ├── huggingface.py
│   │   └── rss.py
│   │
│   ├── integrations/
│   │   ├── groq/
│   │   │   └── client.py
│   │   └── zalo/
│   │       ├── client.py
│   │       ├── formatter.py
│   │       └── webhook.py
│   │
│   ├── knowledge/
│   │   ├── answer_generator.py
│   │   ├── cleaner.py
│   │   ├── keyword_extractor.py
│   │   ├── summarize.py
│   │   └── topic_classifier.py
│   │
│   ├── models/
│   │   ├── article.py
│   │   ├── digest.py
│   │   ├── knowledge.py
│   │   └── response.py
│   │
│   ├── pipelines/
│   │   ├── daily_digest.py
│   │   └── knowledge_update.py
│   │
│   ├── services/
│   │   ├── digest_service.py
│   │   ├── knowledge_service.py
│   │   └── rag_service.py
│   │
│   ├── storage/
│   │   └── history.json
│   │
│   ├── vectorstores/
│   │   ├── qdrant.py
│   │   └── retriever.py
│   │
│   └── main.py
├── docs/
│   ├── SDD/
│   ├── Architecture/
│   ├── API.md
│   ├── DecisionLog.md
│   ├── FolderStructure.md
│   ├── README.md
│   └── rules_me_and_AI.md
│
├── scripts/
│   ├── rebuild_embeddings.py
│   ├── send_digest.py
│   ├── test_retriever.py
│   └── update_knowledge.py
│
├── tests/
│   ├── fetchers/
│   ├── integrations/
│   ├── knowledge/
│   ├── pipelines/
│   ├── services/
│   └── vectorstores/
│
├── README.md
├── PROJECT_INDEX.md
├── SDD_ONBOARDING.md
├── pyproject.toml
├── requirements.txt
└── .env
```

---

# 11. Relationship with Other Documents

Tài liệu này đóng vai trò cầu nối giữa Software Design Document và mã nguồn.

Quan hệ giữa các tài liệu như sau:

```text
Requirements
        │
        ▼
Software Design Document
        │
        ▼
Folder Structure Design
        │
        ▼
Architecture
        │
        ▼
Decision Log
        │
        ▼
Implementation
```

Trong đó:

- **Software Design Document** định nghĩa hệ thống cần được thiết kế như thế nào.
- **Folder Structure Design** định nghĩa các Module sẽ được tổ chức trong mã nguồn ra sao.
- **Architecture** mô tả cách các Module tương tác với nhau.
- **Decision Log** ghi lại các quyết định và Trade-off trong quá trình thiết kế.
- **Implementation** hiện thực toàn bộ thiết kế bằng mã nguồn.

Việc phân tách này giúp mỗi tài liệu có một trách nhiệm rõ ràng và tránh trùng lặp nội dung.

---

# 12. Tổng kết

Cấu trúc thư mục của AI-Radar phản ánh trực tiếp các quyết định thiết kế đã được xác định trong Software Design Document.

Việc tổ chức source code theo Module và Layer giúp hệ thống dễ bảo trì, dễ mở rộng và giữ được tính nhất quán giữa tài liệu thiết kế, kiến trúc và hiện thực mã nguồn.

Mọi thay đổi đối với cấu trúc dự án cần được cập nhật trong tài liệu này trước khi thực hiện trên mã nguồn.