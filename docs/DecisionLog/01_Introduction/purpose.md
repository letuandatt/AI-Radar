# Purpose of Decision Log

## Mục đích
Tài liệu Decision Log ghi lại các quyết định thiết kế, kiến trúc và công nghệ quan trọng của AI-Radar. Nó không thay thế Software Design Document (SDD) hay Architecture Documentation, mà bổ sung góc nhìn về **"Tại sao"** (Why) đằng sau mỗi lựa chọn.

## Vai trò
- **Giải thích Trade-off:** Làm rõ lý do chọn giải pháp A thay vì B dựa trên mục tiêu dự án.
- **Lưu trữ ngữ cảnh:** Giúp người phát triển mới hoặc chính tác giả trong tương lai hiểu được tư duy thiết kế ban đầu.
- **Tránh lặp lại sai lầm:** Ghi nhận các phương án đã được cân nhắc nhưng bị loại bỏ để không phải đánh giá lại chúng một cách vô ích.

## Phạm vi
Decision Log chỉ ghi nhận các quyết định có ảnh hưởng đến:
- Kiến trúc hệ thống.
- Lựa chọn công nghệ (Tech Stack).
- Chiến lược xử lý dữ liệu và AI.
- Quy trình phát triển và vận hành.

Các chi tiết implementation nhỏ (ví dụ: tên biến, cấu trúc hàm) không thuộc phạm vi của tài liệu này.