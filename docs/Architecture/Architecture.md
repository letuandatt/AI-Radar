1. Introduction

Không giống SDD.

Ở đây chỉ nói ngắn gọn:

Purpose
Intended Audience
Guiding Principles

Ví dụ

This document describes the runtime architecture of AI-Radar.

It serves as the single source of truth for the project's implementation.

Every module, dependency, pipeline and interaction described in this document should be reflected in the source code.

2. High-level Architecture

Đây sẽ là sơ đồ lớn nhất.

Ví dụ

                     GitHub Actions
                            │
                Scheduled Knowledge Update
                            │
                            ▼
                    Knowledge Pipeline
                            │
          ┌─────────────────┴──────────────────┐
          ▼                                    ▼
     Knowledge Base                     Daily Digest
       (Qdrant)                              │
          ▲                                  ▼
          │                           Zalo Daily Bot
          │
          │
          ▼
     RAG Pipeline
          ▲
          │
 Zalo Assistant Bot

Sau đó giải thích từng block.

3. System Context

Đây là phần SDD không có.

Ví dụ

                    Internet
                       │
                       ▼
              External Sources
                       │
                       ▼
                  AI-Radar
                 ┌────────┐
                 │Backend │
                 └────────┘
                 ▲        ▲
                 │        │
          Groq API     Qdrant
                 │
                 ▼
             Zalo OA

Đây là Context Diagram.

4. Component Diagram

Đây là phần cực kỳ quan trọng.

Ví dụ

Application Layer

│

├── KnowledgeUpdateUseCase

├── GenerateDigestUseCase

└── AnswerQuestionUseCase

↓

Service Layer

↓

Repository Layer

↓

Infrastructure

Mình sẽ giải thích

dependency direction.

5. Runtime Pipelines

Có 2 pipeline.

Pipeline A

Knowledge Update

Chi tiết tới từng bước.

Ví dụ

Scheduler

↓

Fetcher

↓

Cleaner

↓

Deduplicator

↓

Knowledge Builder

↓

Embedding

↓

Qdrant

↓

Digest Generator

↓

Zalo

Không chỉ vẽ.

Mỗi bước sẽ có:

Input

Output

Failure

Retry

Pipeline B

RAG

Webhook

↓

Question Parser

↓

Retriever

↓

Prompt Builder

↓

Groq

↓

Formatter

↓

Reply
6. Knowledge Lifecycle

Đây sẽ là chương mình tự nghĩ thêm.

Ví dụ

Raw Article

↓

Normalized Article

↓

Knowledge Object

↓

Embedded Object

↓

Retrieved Object

↓

LLM Context

↓

Generated Answer

Mỗi trạng thái sẽ có schema.

7. Data Flow

Ví dụ

Knowledge Update

RSS

↓

Fetcher

↓

Article[]

↓

KnowledgeObject[]

↓

Embedding[]

↓

Qdrant

RAG

Question

↓

Embedding

↓

Retriever

↓

Knowledge[]

↓

Prompt

↓

Answer
8. Dependency Rules

Đây là phần cực ít đồ án có.

Ví dụ

Fetcher

×

Không được import

Retriever
Retriever

×

Không được import

Fetcher

Hay

Application

↓

Service

↓

Repository

↓

Infrastructure

Chỉ được đi một chiều.

9. Directory Mapping

Ví dụ

fetchers/

↓

Knowledge Acquisition Layer
knowledge/

↓

Knowledge Processing
services/

↓

Business Logic
vectorstore/

↓

Knowledge Storage

Tức là mapping giữa

folder

và

architecture.

10. Error Handling

Ví dụ

Fetcher fail

↓

Retry

↓

Skip Source

↓

Continue Pipeline

Hay

Groq timeout

↓

Retry

↓

Fallback Prompt

↓

Abort

11. Sequence Diagram

Mình dự định viết khoảng

8~10 sequence diagram.

Ví dụ

Knowledge Update

Daily Digest

RAG

Startup

Shutdown

Webhook

Embedding

Upsert

12. Extension Points

Ví dụ

Nếu sau này thêm

Discord

↓

chỉ cần

Notification Adapter.

Hay

Pinecone

↓

Vector Repository.

13. Non-goals

Đây là phần mình rất thích.

Ví dụ

AI-Radar deliberately does NOT support:

Multi-tenancy
User Authentication
Distributed Deployment
Real-time Crawling
Horizontal Scaling

để người đọc biết đây là chủ đích thiết kế, không phải thiếu sót.

14. Architecture Decision Highlights

Khác với ADR.

Ở đây chỉ có khoảng 8–10 quyết định quan trọng nhất, mỗi quyết định trình bày trong nửa trang:

Tại sao có hai pipeline thay vì một?
Vì sao dùng Knowledge Object thay vì lưu article thô?
Vì sao Daily Digest và RAG dùng chung Knowledge Base?
Vì sao Qdrant thay vì document database?
Vì sao chỉ gọi LLM ở hai vị trí?
Vì sao scheduler chạy theo batch thay vì realtime?
Vì sao tách hai Zalo Bot nhưng chỉ có một backend?