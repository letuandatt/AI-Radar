# Decision: Use Groq API as LLM Provider

## Decision
Hệ thống sử dụng **Groq API** làm nhà cung cấp dịch vụ Large Language Model (LLM) chính cho cả hai tác vụ: Knowledge Extraction (trong Update Pipeline) và Question Answering (trong QA Pipeline).

## Context
LLM là thành phần đắt đỏ nhất và chậm nhất trong hệ thống RAG. Việc lựa chọn provider cần cân bằng giữa ba yếu tố: Tốc độ phản hồi (Latency), Chi phí (Cost) và Chất lượng suy luận (Reasoning Capability).

## Why This Decision?
1.  **Speed (Inference Speed):** Groq sử dụng kiến trúc LPU (Language Processing Unit) giúp tốc độ sinh token cực nhanh, phù hợp với yêu cầu độ trễ thấp của QA Pipeline và giúp rút ngắn thời gian chạy của Update Pipeline.
2.  **Cost-Effectiveness:** Groq cung cấp free tier hào phóng và chi phí trả phí rất cạnh tranh so với các đối thủ như OpenAI hay Anthropic, phù hợp với quy mô cá nhân của AI-Radar.
3.  **Model Quality:** Hỗ trợ các mô hình mã nguồn mở chất lượng cao như `llama3-70b` và `mixtral-8x7b`, đủ khả năng thực hiện các tác vụ phức tạp như tóm tắt, trích xuất metadata và trả lời câu hỏi chuyên sâu.

## Why Not Alternatives?
-   **Not OpenAI (GPT-4):** Mặc dù chất lượng rất tốt, nhưng chi phí cao hơn đáng kể và tốc độ phản hồi chậm hơn so với Groq trong các tác vụ xử lý batch lớn.
-   **Not Local LLM (Ollama):** Chạy local đòi hỏi tài nguyên phần cứng lớn (GPU RAM) và khó duy trì hiệu năng ổn định trên môi trường server giá rẻ. Groq giúp offload hoàn toàn gánh nặng tính toán.
-   **Not Anthropic/Claude:** Chất lượng rất tốt nhưng chi phí và tốc độ chưa tối ưu bằng Groq cho các tác vụ xử lý số lượng lớn bài báo hàng ngày.

## Impact
-   Module `integrations/groq/` được thiết kế để đóng gói mọi tương tác với Groq API.
-   Sử dụng hai model khác nhau tùy tác vụ:
    -   `llama3-70b-8192`: Cho các tác vụ cần suy luận sâu (QA, Tóm tắt phức tạp).
    -   `mixtral-8x7b-32768`: Cho các tác vụ nhẹ, tốc độ cao (Phân loại chủ đề, Trích xuất từ khóa).
-   API Key được quản lý chặt chẽ qua Environment Variables (`GROQ_API_KEY`).