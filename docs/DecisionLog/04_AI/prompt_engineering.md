# Decision: Centralized Prompt Engineering

## Decision
Toàn bộ Prompt Templates được quản lý tập trung trong file `config/prompts.py` thay vì hard-code trong source code. Hệ thống ưu tiên **Prompt Engineering** như một phương pháp chính để cải thiện chất lượng đầu ra của LLM.

## Context
Chất lượng của AI-Radar phụ thuộc rất lớn vào cách chúng ta "ra lệnh" cho LLM. Một prompt tốt có thể thay thế cho các thuật toán xử lý phức tạp. Việc hard-code prompt rải rác trong code khiến việc tinh chỉnh (tuning) trở nên khó khăn và dễ gây lỗi cú pháp.

## Why This Decision?
1.  **Maintainability:** Tách biệt Prompt khỏi Logic giúp developer dễ dàng thử nghiệm các biến thể prompt khác nhau mà không cần deploy lại toàn bộ ứng dụng.
2.  **Consistency:** Đảm bảo mọi lời gọi LLM đều sử dụng cùng một cấu trúc prompt chuẩn, giúp đầu ra ổn định và dễ dự đoán.
3.  **Version Control:** Prompt là một phần quan trọng của "Business Logic" trong hệ thống AI. Việc lưu trong file riêng giúp theo dõi lịch sử thay đổi và đánh giá tác động của từng lần chỉnh sửa prompt.
4.  **Context Optimization:** Cho phép tối ưu hóa độ dài prompt để phù hợp với Context Window của các model trên Groq, tránh lãng phí token.

## Why Not Alternatives?
-   **Not Hard-coded Strings:** Hard-code khiến code rối rắm, khó đọc và khó thay đổi. Mỗi lần sửa prompt phải tìm kiếm khắp nơi trong codebase.
-   **Not Dynamic Prompt Generation:** Tự động sinh prompt bằng một LLM khác là quá phức tạp và tốn kém cho một hệ thống cá nhân. Prompt tĩnh được thiết kế kỹ lưỡng vẫn hiệu quả hơn trong hầu hết các trường hợp.

## Impact
-   File `config/prompts.py` chứa các template cho:
    -   Knowledge Extraction (Summary, Keywords, Topics).
    -   Daily Digest Generation.
    -   Question Answering (RAG Context).
-   Các module trong `knowledge/` và `services/` sẽ import và điền dữ liệu vào các template này trước khi gửi cho LangChain/Groq.
-   Prompt được thiết kế theo hướng "Role-playing" (đóng vai biên tập viên/chuyên gia) để tăng chất lượng suy luận của LLM.