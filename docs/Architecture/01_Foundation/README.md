# Foundation View

Foundation View cung cấp góc nhìn tổng quan về kiến trúc AI-Radar ở mức hệ thống.

View này trả lời:
- Hệ thống này là hệ thống gì.
- Tại sao lại thiết kế theo hướng này.
- Những ràng buộc nào chi phối kiến trúc?

Nó cố tình tránh đề cập đến các chi tiết triển khai, hành vi khi chạy và các vấn đề liên quan đến việc triển khai.

Đây là View đầu tiên của Architecture và nên được đọc trước các View còn lại.

---

# Documents

| Document | Description |
|-----------|-------------|
| `principles.md` | Các nguyên tắc kiến trúc của AI-Radar. |
| `system_context.md` | Bối cảnh hoạt động và các tác nhân bên ngoài hệ thống. |
| `high_level_architecture.md` | Kiến trúc tổng thể của AI-Radar ở mức High-Level. |
| `building_blocks.md` | Các khối chức năng chính tạo nên hệ thống. |
| `constraints.md` | Các ràng buộc và giới hạn của kiến trúc. |

---

# Reading Order

```text
Principles
      │
      ▼
System Context
      │
      ▼
High-Level Architecture
      │
      ▼
Core Building Blocks
      │
      ▼
Constraints
```

Sau khi hoàn thành Foundation View, tiếp tục đọc **Structure View**.