# Software Design Document (SDD)

## Giới thiệu

Thư mục này chứa **Software Design Document (SDD)** của dự án **AI-Radar**.

SDD mô tả toàn bộ thiết kế của hệ thống trước khi triển khai mã nguồn, bao gồm:

- Mục tiêu của hệ thống.
- Phạm vi dự án.
- Triết lý thiết kế.
- Kiến trúc phần mềm.
- Thiết kế dữ liệu.
- Thiết kế Module.
- Các yêu cầu phi chức năng.
- Định hướng phát triển trong tương lai.

Trong AI-Radar, **Software Design Document là nguồn thông tin thiết kế chính (Source of Truth)**.

Mọi quyết định về kiến trúc, cấu trúc dự án và hiện thực mã nguồn đều phải nhất quán với các nội dung trong tài liệu này.

---

# Cách đọc

Các chương được sắp xếp theo trình tự từ yêu cầu đến thiết kế chi tiết.

Khuyến nghị đọc theo đúng thứ tự từ **Chương 01** đến **Appendix**.

---

# Mục lục

| Chương | Nội dung |
|---------|----------|
| 01 | [Introduction](01_Introduction.md) |
| 02 | [Objectives](02_Objectives.md) |
| 03 | [Project Scope](03_Project_Scope.md) |
| 04 | [Design Philosophy](04_Design_Philosophy.md) |
| 05 | [System Requirements](05_System_Requirements.md) |
| 06 | [System Architecture](06_System_Architecture.md) |
| 07 | [Data Model](07_Data_Model.md) |
| 08 | [Module Design](08_Module_Design.md) |
| 09 | [External Integrations](09_External_Integrations.md) |
| 10 | [Non-Functional Requirements](10_Non_Functional_Requirements.md) |
| 11 | [Security](11_Security.md) |
| 12 | [Testing Strategy](12_Testing_Strategy.md) |
| 13 | [Deployment](13_Deployment.md) |
| 14 | [Limitations](14_Limitations.md) |
| 15 | [Future Enhancements](15_Future_Enhancements.md) |
| Appendix | [Glossary, Design Summary và các thông tin tham khảo](Appendix.md) |

---

# Cấu trúc thư mục

```text
SDD/
├── README.md
├── 01_Introduction.md
├── 02_Objectives.md
├── 03_Project_Scope.md
├── 04_Design_Philosophy.md
├── 05_System_Requirements.md
├── 06_System_Architecture.md
├── 07_Data_Model.md
├── 08_Module_Design.md
├── 09_External_Integrations.md
├── 10_Non_Functional_Requirements.md
├── 11_Security.md
├── 12_Testing_Strategy.md
├── 13_Deployment.md
├── 14_Limitations.md
├── 15_Future_Enhancements.md
└── Appendix.md
```

---

# Lưu ý

Software Design Document mô tả **thiết kế** của hệ thống, không mô tả chi tiết cách hiện thực.

Các tài liệu như **Architecture**, **Decision Log**, **API** và mã nguồn sẽ được xây dựng dựa trên các quyết định đã được thống nhất trong SDD.