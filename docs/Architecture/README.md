# AI-Radar Architecture

AI-Radar Architecture mô tả cách Software Design của hệ thống được hiện thực ở mức kiến trúc.

Architecture không định nghĩa yêu cầu mới và cũng không thay thế Software Design Document (SDD).

Mục tiêu của bộ tài liệu này là giúp người đọc hiểu:

- Hệ thống được tổ chức như thế nào.
- Các thành phần phối hợp với nhau ra sao.
- Runtime của hệ thống hoạt động như thế nào.
- Kiến trúc được thiết kế để vận hành và mở rộng như thế nào.

Architecture được chia thành bốn View, mỗi View tập trung vào một góc nhìn khác nhau của cùng một hệ thống.

---

# Views

| View | Mục đích |
|-------|----------|
| **01 Foundation** | Giới thiệu kiến trúc tổng quan và các nguyên tắc nền tảng của AI-Radar. |
| **02 Structure** | Mô tả cấu trúc các thành phần và quan hệ phụ thuộc trong hệ thống. |
| **03 Runtime** | Mô tả hành vi của hệ thống trong quá trình thực thi. |
| **04 Operations** | Mô tả các khía cạnh vận hành, cấu hình và khả năng mở rộng. |

---

# Reading Order

Để có được cái nhìn đầy đủ về hệ thống, nên đọc theo thứ tự sau:

```text
Foundation
      │
      ▼
Structure
      │
      ▼
Runtime
      │
      ▼
Operations
```

Mỗi View được xây dựng dựa trên kiến thức của View trước đó.

---

# Relationship with Software Design Document

Software Design Document mô tả:

> What should be built?

Architecture mô tả:

> How the system is organized and operates.

Implementation hiện thực:

> How the system is coded.

Architecture không thay đổi các quyết định đã được thống nhất trong Software Design Document.

---

# Design Principles

Toàn bộ tài liệu Architecture tuân thủ các nguyên tắc sau:

- Mô tả hệ thống ở mức kiến trúc.
- Không đi xuống implementation.
- Không lặp lại nội dung của Software Design Document.
- Mỗi tài liệu chỉ tập trung vào một Knowledge Domain.
- Mọi thành phần kiến trúc đều có khả năng ánh xạ sang source code.
- Ưu tiên mô tả bằng sơ đồ khi phù hợp.

---

# Directory Structure

```text
Architecture/

├── README.md
├── 01_Foundation/
├── 02_Structure/
├── 03_Runtime/
└── 04_Operations/
```