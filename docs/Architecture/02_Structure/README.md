# Structure View

Structure View mô tả cách AI-Radar được tổ chức ở mức thành phần và quan hệ phụ thuộc.

View này tập trung vào cấu trúc tĩnh của hệ thống. 

View này sẽ trả lời:
- Cách tổ chức hệ thống.
- Cách các thành phần phụ thuộc nhau.
- Kiến trúc hệ thống được ánh xạ vào mã nguồn như thế nào.

---

# Documents

| Document | Description |
|-----------|-------------|
| `package_structure.md` | Tổ chức các package trong hệ thống. |
| `dependency_rules.md` | Quy tắc phụ thuộc giữa các package. |
| `module_responsibilities.md` | Trách nhiệm của từng nhóm module. |
| `component_interaction.md` | Quan hệ giữa các thành phần chính. |
| `source_mapping.md` | Ánh xạ từ kiến trúc sang cấu trúc source code. |

---

# Reading Order

```text
Package Structure
        │
        ▼
Dependency Rules
        │
        ▼
Module Responsibilities
        │
        ▼
Component Interaction
        │
        ▼
Source Mapping
```

Sau khi hoàn thành Structure View, tiếp tục đọc **Runtime View**.