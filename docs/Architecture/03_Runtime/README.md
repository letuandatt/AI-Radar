# Runtime View

Runtime View mô tả hành vi của AI-Radar trong quá trình thực thi.

View này tập trung vào các pipeline, luồng dữ liệu và sự phối hợp giữa các thành phần của hệ thống.

---

# Documents

| Document | Description |
|-----------|-------------|
| `knowledge_update_pipeline.md` | Runtime của Knowledge Update Pipeline. |
| `daily_digest_pipeline.md` | Runtime của Daily Digest Pipeline. |
| `question_answering_pipeline.md` | Runtime của Question Answering Pipeline. |
| `data_flow.md` | Luồng dữ liệu giữa các thành phần. |
| `sequence_diagrams.md` | Các Sequence Diagram của hệ thống. |

---

# Reading Order

```text
Knowledge Update Pipeline
            │
            ▼
Daily Digest Pipeline
            │
            ▼
Question Answering Pipeline
            │
            ▼
Data Flow
            │
            ▼
Sequence Diagrams
```

Sau khi hoàn thành Runtime View, tiếp tục đọc **Operations View**.