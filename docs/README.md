# Trung tâm Tài liệu AI-Radar (Documentation Hub)

## 1. Mục đích

Thư mục `docs/` chứa toàn bộ hệ thống tài liệu kỹ thuật chính thức của dự án AI-Radar.

Đây là điểm bắt đầu (Entry Point) để tìm hiểu hệ thống, cung cấp cái nhìn tổng quan về các bộ tài liệu, mục đích của từng tài liệu và mối quan hệ giữa chúng.

**Lưu ý:** Đây là tài liệu điều hướng (Navigation), không thay thế nội dung chi tiết của từng bộ tài liệu.

---

## 2. Cấu trúc Tài liệu

Hệ thống tài liệu của AI-Radar được tổ chức thành bốn nhóm chính:

| Tài liệu | Vai trò |
| :--- | :--- |
| **Software Design Document (SDD)** | Định nghĩa yêu cầu, phạm vi và thiết kế của hệ thống. |
| **Architecture** | Mô tả cách hệ thống được tổ chức và vận hành. |
| **Decision Log** | Giải thích các quyết định thiết kế và công nghệ. |
| **API Specification** | Mô tả các interface mà hệ thống cung cấp. |

---

## 3. Tổng quan Tài liệu

### Software Design Document (SDD)

Là tài liệu nền tảng của dự án, mô tả các yêu cầu và thiết kế của hệ thống.

**Đọc khi:** Muốn hiểu hệ thống cần xây dựng những gì.

---

### Architecture

Mô tả cấu trúc, thành phần và cách hệ thống hoạt động ở mức kiến trúc.

**Đọc khi:** Muốn hiểu cách hệ thống được tổ chức và vận hành.

---

### Decision Log

Lưu trữ lý do đằng sau các quyết định quan trọng trong quá trình thiết kế và phát triển.

**Đọc khi:** Muốn hiểu tại sao một giải pháp hoặc công nghệ được lựa chọn.

---

### API Specification

Tài liệu tham chiếu về các interface của hệ thống.

**Đọc khi:** Muốn tích hợp hoặc tương tác với AI-Radar.

---

## 4. Thứ tự Đọc Khuyến nghị

Để hiểu đầy đủ về AI-Radar, nên đọc theo thứ tự:

1. **Software Design Document (SDD)** 
2. **Architecture**
3. **Decision Log**
4. **API Specification**

---

## 5. Mối quan hệ giữa các Tài liệu

Các tài liệu bổ sung cho nhau và được duy trì nhất quán trong suốt vòng đời dự án.

```text
Requirements
        │
        ▼
Software Design Document (SDD)
        │
        ▼
Architecture
        │
        ▼
Decision Log
        │
        ▼
API Specification
        │
        ▼
Implementation
```

- **SDD** xác định hệ thống cần được xây dựng như thế nào.
- **Architecture** hiện thực hóa thiết kế ở mức hệ thống.
- **Decision Log** giải thích các quyết định được đưa ra trong quá trình thiết kế.
- **API Specification** mô tả các interface được cung cấp bởi hệ thống.

---

## 6. Nguyên tắc Bảo trì Tài liệu

AI-Radar áp dụng phương pháp **Documentation-First**.

Khi hệ thống thay đổi, tất cả các tài liệu bị ảnh hưởng cần được cập nhật đồng bộ để đảm bảo tính nhất quán giữa tài liệu và triển khai.

---