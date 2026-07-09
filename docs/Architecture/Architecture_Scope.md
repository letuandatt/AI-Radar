# Define Architecture Scope

## Purpose

Architecture mô tả cách Software Design của AI-Radar được hiện thực ở mức kiến trúc hệ thống.

Architecture không thay thế Software Design Document (SDD).

Architecture không đưa ra quyết định thiết kế mới.

Mọi nội dung trong Architecture phải tuân thủ các quyết định đã được khóa trong SDD.

---

# Responsibilities

Architecture trả lời các câu hỏi sau:

- Các module giao tiếp với nhau như thế nào?
- Luồng dữ liệu chạy trong hệ thống như thế nào?
- Một request đi qua những thành phần nào?
- Runtime Pipeline được thực thi theo trình tự nào?
- Thành phần nào chịu trách nhiệm cho từng bước xử lý?
- Các dịch vụ bên ngoài (Groq, Qdrant, Zalo Official Account...) được tích hợp như thế nào?
- Dependency giữa các package được tổ chức ra sao?
- Các module trong source code phối hợp với nhau như thế nào?

Architecture không trả lời:

- Vì sao hệ thống được thiết kế như vậy.
- Mục tiêu của dự án.
- Business Requirement.
- Chi tiết implementation của class, function hoặc source code.

---

# Relationship with Software Design Document

Software Design Document định nghĩa:

- Mục tiêu của hệ thống.
- Phạm vi dự án.
- Design Philosophy.
- Functional Requirements.
- Non-functional Requirements.
- Data Model.
- Module Design.

Architecture hiện thực các quyết định đó bằng cách mô tả:

- Runtime Architecture.
- Dependency giữa các module.
- Data Flow.
- Request Flow.
- Runtime Pipeline.
- Component Interaction.

Architecture không được thay đổi hoặc bổ sung các quyết định đã được thống nhất trong SDD.

---

# Relationship with Folder Structure Design

Folder Structure Design mô tả cách tổ chức source code.

Architecture mô tả cách các package trong source code phối hợp với nhau trong quá trình hệ thống hoạt động.

Ví dụ:

Folder Structure Design:

```text
app/
├── services/
├── knowledge/
├── vectorstores/
└── integrations/
```

Architecture:

```text
Knowledge Service
        │
        ▼
Embedding Service
        │
        ▼
Qdrant Repository
        │
        ▼
Retriever
```

Folder Structure trả lời:

> Source code nằm ở đâu?

Architecture trả lời:

> Source code phối hợp với nhau như thế nào?

---

# Relationship with Implementation

Architecture là cầu nối giữa Software Design và Source Code.

```text
Software Design Document
            │
            ▼
      Architecture
            │
            ▼
      Implementation
```

Mỗi thành phần trong Architecture phải có khả năng ánh xạ trực tiếp sang cấu trúc source code.

---

# Scope

Architecture tập trung mô tả các nội dung sau:

1. Architectural Principles

2. Runtime Overview

3. Dependency Rules

4. Package Responsibilities

5. Runtime Pipelines

6. Component Interaction

7. Sequence Diagrams

8. Data Flow

9. Deployment View

10. Configuration Strategy

11. Error Handling Strategy

12. Logging Strategy

13. Scalability Strategy

14. Future Evolution

---

# Out of Scope

Architecture không mô tả lại các nội dung đã có trong SDD.

Bao gồm:

- Project Objectives
- Project Scope
- Design Philosophy
- Functional Requirements
- Non-functional Requirements
- Data Model
- Security Requirements
- Testing Strategy
- Deployment Plan

Khi cần, Architecture chỉ tham chiếu tới các chương tương ứng trong SDD.

---

# Level of Abstraction

Architecture mô tả hệ thống ở mức:

- Component
- Package
- Runtime Flow
- Dependency
- Sequence
- Integration

Architecture không đi xuống mức:

- Class
- Function
- Method
- Interface
- Source Code

Các nội dung này thuộc Implementation.

---

# Design Principles

Trong quá trình xây dựng Architecture phải tuân thủ các nguyên tắc sau:

- Không thay đổi các quyết định đã được khóa trong SDD.
- Không lặp lại nội dung của SDD.
- Không mô tả chi tiết implementation.
- Mọi thành phần trong Architecture phải có khả năng ánh xạ sang Folder Structure.
- Mọi Runtime Flow phải phản ánh đúng thiết kế của SDD.

---

# Summary

Software Design Document quyết định:

> **What should be built?**

Architecture mô tả:

> **How the system is organized and operates.**

Implementation hiện thực:

> **How the system is coded.**