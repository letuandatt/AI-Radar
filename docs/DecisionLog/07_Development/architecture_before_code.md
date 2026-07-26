# Decision: Documentation-First Development Approach

## Decision
Dự án AI-Radar áp dụng phương pháp **Documentation-First**. Mọi thay đổi về yêu cầu, kiến trúc hoặc thiết kế đều phải được ghi nhận và thống nhất trong tài liệu trước khi bắt đầu viết mã nguồn (Implementation).

## Context
Trong các dự án phần mềm cá nhân hoặc quy mô nhỏ, xu hướng thường là "Code First" – viết code ngay để thấy kết quả nhanh, sau đó mới bổ sung tài liệu nếu cần. Tuy nhiên, cách tiếp cận này thường dẫn đến tình trạng "Technical Debt" về mặt thiết kế, code bị rối rắm do thiếu định hướng rõ ràng, và khó bảo trì khi quay lại sau một thời gian dài.

## Why This Decision?
1.  **Clarity of Thought:** Việc viết tài liệu buộc người phát triển phải suy nghĩ kỹ lưỡng về mục tiêu, phạm vi và trade-off trước khi bắt tay vào làm. Nó giúp loại bỏ các quyết định cảm tính hoặc thiếu căn cứ.
2.  **Single Source of Truth:** Software Design Document (SDD) và Architecture đóng vai trò là nguồn chân lý duy nhất. Khi có bất kỳ mâu thuẫn nào giữa code và tài liệu, tài liệu luôn được ưu tiên điều chỉnh trước, sau đó code mới được sửa theo.
3.  **Ease of Onboarding & Maintenance:** Với tư duy "Public Project Mindset", tài liệu đầy đủ giúp bất kỳ ai (hoặc chính tác giả trong tương lai) có thể hiểu được hệ thống mà không cần đọc từng dòng code.
4.  **Avoid Rework:** Phát hiện lỗ hổng thiết kế ở giai đoạn tài liệu rẻ hơn rất nhiều so với việc phát hiện ra khi code đã chạy và dữ liệu đã được lưu trữ.

## Why Not Alternatives?
-   **Not Code-First:** Code-first thường dẫn đến việc hệ thống phát triển theo hướng "patchwork" (chắp vá), khó mở rộng và thiếu nhất quán.
-   **Not Documentation-After:** Viết tài liệu sau khi code xong thường mang tính hình thức, không phản ánh đúng quá trình tư duy thiết kế và dễ bị lỗi thời ngay khi code được cập nhật lần tiếp theo.

## Impact
-   Quy trình phát triển tuân thủ nghiêm ngặt: `Requirement` → `SDD` → `Architecture` → `Decision Log` → `Implementation`.
-   Không được phép commit code mới nếu chưa có tài liệu tương ứng mô tả thiết kế của nó (trừ các bản fix lỗi nhỏ không ảnh hưởng kiến trúc).
-   Tài liệu được coi là một phần sản phẩm cuối cùng, có chất lượng ngang hàng với mã nguồn.