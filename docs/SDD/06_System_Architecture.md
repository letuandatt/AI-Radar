# 6. System Architecture

---

## 6.1 Architecture Overview

AI-Radar được thiết kế theo mô hình **Knowledge-Centric Architecture**, trong đó mọi thành phần của hệ thống đều xoay quanh việc xây dựng, duy trì và khai thác một kho tri thức thống nhất (Knowledge Base).

Khác với nhiều hệ thống RAG truyền thống chỉ bắt đầu xử lý khi người dùng gửi câu hỏi, AI-Radar hoạt động theo mô hình **Continuous Knowledge Acquisition**.

Điều này có nghĩa là hệ thống liên tục học hỏi từ các nguồn dữ liệu mới theo lịch định kỳ, sau đó lưu trữ tri thức đã được chuẩn hóa vào Knowledge Base trước khi có bất kỳ truy vấn nào từ người dùng.

Nhờ vậy, thời gian phản hồi của RAG được giảm đáng kể vì quá trình:

* Crawl
* Cleaning
* Parsing
* AI Summarization
* Embedding

đã hoàn thành từ trước.

Người dùng chỉ tương tác với một kho tri thức đã được xây dựng sẵn.

---

## 6.2 Architectural Principles

Kiến trúc của AI-Radar được xây dựng dựa trên sáu nguyên tắc chính.

### Principle 1 — Knowledge First

Tri thức là tài sản quan trọng nhất của hệ thống.

Toàn bộ pipeline đều phục vụ việc chuyển đổi dữ liệu thô thành Knowledge Object.

Không module nào thao tác trực tiếp với bài báo sau khi Knowledge Object đã được tạo.

Điều này giúp:

* chuẩn hóa dữ liệu,
* giảm kích thước lưu trữ,
* tăng chất lượng retrieval,
* giảm token sử dụng khi RAG.

---

### Principle 2 — Separation of Responsibility

Mỗi module chỉ chịu trách nhiệm cho một công việc duy nhất.

Ví dụ:

Fetcher

↓

lấy dữ liệu

Knowledge Builder

↓

xây dựng Knowledge Object

Embedding Service

↓

tạo vector

Retriever

↓

tìm kiếm

Generator

↓

tạo câu trả lời

Không module nào thực hiện đồng thời nhiều nhiệm vụ.

Điều này giúp:

* dễ kiểm thử,
* dễ mở rộng,
* dễ thay thế.

---

### Principle 3 — Pipeline-based Processing

Toàn bộ hệ thống hoạt động dưới dạng các pipeline độc lập.

Không tồn tại một "God Service" điều khiển toàn bộ chương trình.

Mỗi pipeline có thể chạy riêng.

Ví dụ:

Knowledge Update Pipeline

và

Question Answering Pipeline.

Hai pipeline chỉ chia sẻ chung Knowledge Base.

---

### Principle 4 — Asynchronous by Default

Các tác vụ I/O như:

* HTTP Request
* RSS Fetching
* GitHub API
* HuggingFace API

đều được thực hiện bất đồng bộ.

Điều này giúp giảm đáng kể tổng thời gian cập nhật dữ liệu.

---

### Principle 5 — Replaceable Infrastructure

Các thành phần hạ tầng được trừu tượng hóa thông qua interface.

Ví dụ:

Vector Repository

có thể được triển khai bằng:

* Qdrant
* Pinecone
* Milvus

mà không ảnh hưởng tới tầng Business Logic.

Tương tự:

LLM Provider

có thể chuyển đổi giữa:

* Groq
* OpenRouter
* Ollama
* Gemini

thông qua LangChain.

---

### Principle 6 — Knowledge Reuse

Một Knowledge Object chỉ được sinh ra đúng một lần.

Sau đó nó được tái sử dụng cho:

* Daily Digest
* Semantic Retrieval
* Question Answering
* Future Analytics

Điều này giúp giảm số lần gọi LLM và giảm chi phí vận hành.

---

# 6.3 High-Level Architecture

Toàn bộ hệ thống được chia thành bốn tầng chính.

Layer 1

Knowledge Acquisition

↓

Layer 2

Knowledge Processing

↓

Layer 3

Knowledge Storage

↓

Layer 4

Knowledge Consumption

Mỗi tầng chịu trách nhiệm cho một giai đoạn trong vòng đời của tri thức.

---

## Layer 1 — Knowledge Acquisition

Đây là tầng chịu trách nhiệm thu thập dữ liệu.

Nguồn dữ liệu bao gồm:

* Hugging Face
* Hacker News
* GitHub Trending
* Papers With Code
* RSS AI Blogs
* Các nguồn mở rộng trong tương lai

Fetcher chỉ thực hiện:

* lấy dữ liệu,
* parse metadata,
* trả về Raw Article.

Fetcher tuyệt đối không:

* embedding,
* summarize,
* AI classify.

Điều này giúp Fetcher luôn đơn giản và có thể mở rộng dễ dàng.

---

## Layer 2 — Knowledge Processing

Đây là tầng quan trọng nhất.

Raw Article sẽ lần lượt đi qua các bước:

Cleaning

↓

Normalization

↓

Deduplication

↓

LLM Processing

↓

Knowledge Builder

↓

Embedding

↓

Knowledge Object

Knowledge Processing là nơi dữ liệu thô được chuyển đổi thành tri thức.

Đây cũng là tầng duy nhất được phép gọi Large Language Model trong quá trình cập nhật dữ liệu.

---

## Layer 3 — Knowledge Storage

Sau khi Knowledge Object được tạo, hệ thống sẽ sinh embedding và lưu vào Qdrant.

Mỗi record trong Qdrant bao gồm:

* Vector
* Summary
* Title
* Topics
* Keywords
* Published Time
* Source
* URL
* Importance Score

Qdrant đóng vai trò là Semantic Knowledge Repository.

Không phải nơi lưu article.

Không phải document database.

Không phải relational database.

---

## Layer 4 — Knowledge Consumption

Đây là tầng cuối cùng.

Có hai consumer.

Consumer thứ nhất:

Daily Digest

Consumer thứ hai:

Question Answering.

Cả hai đều sử dụng chung Knowledge Base.

Không consumer nào truy cập trực tiếp Fetcher.

---

# 6.4 Knowledge Lifecycle

Một bài viết sẽ trải qua toàn bộ vòng đời sau.

Raw Article

↓

Cleaning

↓

Normalization

↓

Duplicate Detection

↓

Knowledge Extraction

↓

Knowledge Object

↓

Embedding

↓

Qdrant

↓

Retriever

↓

LLM

↓

User

Điểm quan trọng nhất của AI-Radar là:

Knowledge Object trở thành "single source of truth".

Toàn bộ hệ thống không làm việc trên Raw Article nữa.

---

# 6.5 Dual Pipeline Architecture

AI-Radar được chia thành hai pipeline hoàn toàn độc lập.

Đây là quyết định kiến trúc quan trọng nhất của dự án.

---

## Pipeline A — Scheduled Knowledge Update

Pipeline này được GitHub Actions kích hoạt theo lịch.

Ví dụ:

06:00

↓

Crawler

↓

Fetch Articles

↓

Normalize

↓

Remove Duplicate

↓

AI Knowledge Extraction

↓

Knowledge Object

↓

Embedding

↓

Qdrant Upsert

↓

Daily Digest Generation

↓

Zalo Daily Bot

Sau khi hoàn thành, hệ thống quay về trạng thái chờ.

Pipeline này không nhận bất kỳ input nào từ người dùng.

---

## Pipeline B — Interactive Knowledge Query

Pipeline này được kích hoạt khi người dùng gửi câu hỏi.

User Question

↓

Retriever

↓

Qdrant

↓

Relevant Knowledge Objects

↓

Groq

↓

Answer

↓

Zalo Official Account

Pipeline này tuyệt đối không:

* crawl,
* summarize article,
* embedding.

Toàn bộ dữ liệu đã được chuẩn bị từ Pipeline A.

Nhờ vậy thời gian phản hồi luôn thấp.

---

# 6.6 Architectural Decisions

## Decision 01

Không sử dụng RAG để crawl.

RAG chỉ phục vụ truy vấn.

Knowledge Update hoàn toàn độc lập.

---

## Decision 02

Không lưu article thô trong Vector Database.

Chỉ lưu Knowledge Object.

Điều này giúp:

* retrieval chính xác hơn,
* context ngắn hơn,
* embedding chất lượng hơn.

---

## Decision 03

Daily Digest và RAG dùng chung Knowledge Base.

Không tồn tại hai cơ sở dữ liệu riêng biệt.

Điều này giúp:

* giảm chi phí,
* tránh dữ liệu sai lệch,
* dễ đồng bộ.

---

## Decision 04

Qdrant được lựa chọn làm Vector Database.

Lý do:

* chuyên biệt cho vector search,
* hỗ trợ metadata filtering,
* hiệu năng tốt,
* dễ triển khai bằng Docker,
* tích hợp tốt với LangChain.

Kiến trúc vẫn được xây dựng theo hướng abstraction để có thể thay thế bằng vector database khác nếu cần trong tương lai.

---

## Decision 05

Groq chỉ được sử dụng ở hai vị trí.

Knowledge Extraction.

Question Answering.

Không sử dụng LLM cho:

* Crawl
* Cleaning
* Parsing
* Deduplication
* Scheduling

Nhờ vậy chi phí được tối ưu trong khi vẫn tận dụng được khả năng suy luận của mô hình ở các bước mang lại giá trị cao nhất.

---

## 6.7 Summary

Kiến trúc AI-Radar được xây dựng theo mô hình Knowledge-Centric với hai pipeline độc lập:

1. **Scheduled Knowledge Update Pipeline** chịu trách nhiệm thu thập, xử lý và xây dựng kho tri thức.
2. **Interactive Knowledge Query Pipeline** khai thác kho tri thức để trả lời câu hỏi của người dùng.

Hai pipeline được tách biệt hoàn toàn về vòng đời xử lý nhưng dùng chung một Knowledge Base trên Qdrant. Thiết kế này giúp hệ thống đạt được ba mục tiêu chính:

* Tri thức luôn được cập nhật định kỳ.
* Truy vấn RAG có độ trễ thấp.
* Kiến trúc đủ linh hoạt để mở rộng thêm nguồn dữ liệu hoặc thay thế hạ tầng mà không ảnh hưởng đến logic nghiệp vụ.
