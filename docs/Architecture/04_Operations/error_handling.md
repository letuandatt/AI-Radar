# Error Handling Strategy

## Mục đích

Tài liệu này định nghĩa chiến lược xử lý lỗi (Error Handling Strategy) của AI-Radar ở mức kiến trúc và vận hành. 

Mục tiêu là đảm bảo hệ thống có khả năng phục hồi (Resilience) và ổn định (Reliability) khi đối mặt với các sự cố từ môi trường bên ngoài (mạng, API dịch vụ, dữ liệu đầu vào). Chiến lược này được thiết kế để hiện thực hóa nguyên tắc **Fail Gracefully** (Suy giảm dần đều) đã định nghĩa trong Software Design Document, đảm bảo một lỗi cục bộ không làm sập toàn bộ hệ thống hoặc dừng các Pipeline đang chạy.

## Nguyên tắc xử lý lỗi cốt lõi

Toàn bộ kiến trúc xử lý lỗi của AI-Radar tuân thủ 4 nguyên tắc bất biến sau:

1. **Fail Gracefully (Suy giảm dần đều):** Hệ thống luôn cố gắng hoàn thành tối đa công việc có thể. Một nguồn dữ liệu lỗi không được phép dừng toàn bộ quá trình cập nhật tri thức.
2. **Error Isolation (Cô lập lỗi):** Lỗi phải được cô lập ở đúng module hoặc bước xử lý phát sinh ra nó. Pipeline không được để lỗi của một `Raw Article` lan sang các `Raw Article` khác.
3. **No Retry on Bad Data (Không Retry với dữ liệu sai):** Chỉ thực hiện Retry đối với các lỗi tạm thời (Transient Errors). Các lỗi do dữ liệu đầu vào không hợp lệ hoặc logic nghiệp vụ sai tuyệt đối không Retry.
4. **Fail-Fast on Startup (Khởi động nhanh khi thiếu cấu hình):** Nếu các thành phần hạ tầng cốt lõi (như Qdrant, Groq API Key) không thể kết nối hoặc thiếu cấu hình bắt buộc, hệ thống phải từ chối khởi động (crash immediately) thay vì chạy ngầm và thất bại ở runtime.

## Phân loại lỗi và Chiến lược phản ứng

Để xử lý nhất quán, mọi lỗi phát sinh trong hệ thống được phân thành 3 nhóm chính, mỗi nhóm áp dụng một chiến lược phản ứng (Response Strategy) riêng biệt.

### 1. Transient Errors (Lỗi tạm thời / Có thể phục hồi)
Là các lỗi xảy ra do mạng, timeout, hoặc dịch vụ bên ngoài quá tải.
- **Ví dụ:** HTTP Timeout, HTTP 5xx (Internal Server Error), Rate Limit (HTTP 429), Connection Reset.
- **Chiến lược:** **Retry với Exponential Backoff**.
- **Giới hạn:** Tối đa 3 lần Retry. Nếu vẫn thất bại, coi như lỗi nghiêm trọng và áp dụng chiến lược của nhóm 2 hoặc 3.

### 2. Client / Data Errors (Lỗi dữ liệu / Nghiệp vụ)
Là các lỗi do dữ liệu đầu vào không đúng định dạng, thiếu trường bắt buộc, hoặc logic xử lý từ chối.
- **Ví dụ:** Raw Article thiếu Title/URL, Knowledge Object thiếu Summary, Webhook payload sai định dạng, HTTP 4xx (Bad Request, Unauthorized).
- **Chiến lược:** **Log & Skip / Abort**. Ghi log Warning/Error, hủy bỏ xử lý item hiện tại và chuyển sang item tiếp theo. **Tuyệt đối không Retry**.

### 3. Infrastructure / Fatal Errors (Lỗi hạ tầng cốt lõi)
Là các lỗi xảy ra khi các thành phần lưu trữ hoặc điều phối trung tâm không thể kết nối.
- **Ví dụ:** Không thể kết nối Qdrant (Connection Refused), Scheduler mất tín hiệu, Lỗi ghi đĩa (Disk Full).
- **Chiến lược:** **Log Critical & Abort Pipeline**. Ghi log mức Critical, dừng ngay Pipeline hiện tại để tránh làm hỏng trạng thái hệ thống (Inconsistent State).

## Chiến lược xử lý lỗi theo Pipeline

Mỗi Pipeline có đặc thù vận hành khác nhau, do đó chiến lược xử lý lỗi được điều chỉnh cho phù hợp với ngữ cảnh.

### 1. Knowledge Update Pipeline
Đây là Pipeline chạy nền, ưu tiên tính toàn vẹn dữ liệu và khả năng hoàn thành tác vụ (Completion).

| Giai đoạn | Tình huống lỗi | Hành động kiến trúc |
|---|---|---|
| **Acquisition** | Một Fetcher (ví dụ: GitHub) bị Timeout hoặc trả về lỗi. | Ghi log Warning. Bỏ qua nguồn đó, tiếp tục thu thập từ các nguồn khác. Pipeline không dừng. |
| **Processing** | Một `Raw Article` không thể làm sạch hoặc LLM trả về lỗi khi tóm tắt. | Ghi log Error. Hủy bỏ `Raw Article` này, không tạo `Knowledge Object`. Tiếp tục xử lý bài tiếp theo. |
| **Validation** | `Knowledge Object` thiếu các trường bắt buộc (Title, Summary, Source). | Ghi log Warning. Loại bỏ `Knowledge Object`, không thực hiện Embedding. |
| **Storage** | Mất kết nối tới Qdrant. | Ghi log Critical. **Dừng toàn bộ Pipeline**. Dữ liệu chưa kịp lưu sẽ được xử lý lại ở lịch chạy tiếp theo. |
| **Notification** | Zalo API trả về lỗi khi gửi Daily Digest. | Ghi log Error. Hủy bước gửi tin. Tri thức vẫn an toàn trong Qdrant. |

### 2. Daily Digest Pipeline
Pipeline này chỉ đọc (Read-only) và tạo dữ liệu trình bày. Ưu tiên trải nghiệm người dùng và tính ổn định.

| Giai đoạn | Tình huống lỗi | Hành động kiến trúc |
|---|---|---|
| **Retrieval** | Không có `Knowledge Object` mới nào trong ngày. | Ghi log Info. Pipeline dừng sớm hoặc gửi một thông báo mặc định ("Hôm nay không có tin tức AI mới"). |
| **Generation** | Groq API Timeout sau khi đã Retry. | Ghi log Error. Hủy việc tạo Digest. Không gửi tin nhắn rác hoặc tin nhắn lỗi xuống Zalo. |
| **Notification** | Zalo API từ chối gửi tin (Token hết hạn). | Ghi log Error. Hủy bước gửi. |

### 3. Question Answering Pipeline
Pipeline này chạy tương tác (Interactive), ưu tiên độ trễ thấp và phản hồi rõ ràng cho người dùng.

| Giai đoạn | Tình huống lỗi | Hành động kiến trúc |
|---|---|---|
| **Reception** | Webhook payload sai định dạng hoặc sai Secret. | Trả về HTTP 400/401 cho Zalo ngay lập tức. Không kích hoạt Pipeline. |
| **Retrieval** | Không tìm thấy `Knowledge Object` nào có độ tương đồng vượt ngưỡng (Threshold). | Không gọi LLM. Trả về ngay câu trả lời mặc định: *"Hiện tại AI-Radar chưa có thông tin về vấn đề này."* |
| **Generation** | Groq API lỗi sau khi Retry. | Trả về thông báo lỗi thân thiện cho người dùng qua Zalo: *"Hệ thống đang bận, vui lòng thử lại sau."* |

## Cơ chế Retry (Retry Mechanism)

Để tránh gây quá tải cho các dịch vụ bên ngoài (như Groq API hoặc các nguồn RSS) khi chúng đang gặp sự cố, cơ chế Retry của AI-Radar được chuẩn hóa ở tầng `core/` và `integrations/`.

**Đặc điểm kiến trúc:**
1. **Exponential Backoff:** Thời gian chờ giữa các lần Retry tăng theo cấp số nhân (ví dụ: 1s $\rightarrow$ 2s $\rightarrow$ 4s).
2. **Jitter (Độ trễ ngẫu nhiên):** Thêm một khoảng thời gian ngẫu nhiên nhỏ vào thời gian chờ để tránh hiện tượng nhiều tác vụ Retry cùng một lúc (Thundering Herd).
3. **Circuit Breaker (Optional / Tương lai):** Nếu một dịch vụ liên tục thất bại, hệ thống có thể tạm ngừng gọi dịch vụ đó trong một khoảng thời gian (Cooldown) trước khi thử lại. *Lưu ý: Ở phiên bản đầu tiên, chỉ áp dụng Retry cơ bản, chưa triển khai Circuit Breaker phức tạp để tuân thủ nguyên tắc Simplicity First.*

## Kiểm soát đầu vào và đầu ra (Input / Output Validation)

Xử lý lỗi tốt nhất là ngăn chặn lỗi xảy ra. AI-Radar áp dụng cơ chế Validation nghiêm ngặt tại ranh giới của các Module (Module Boundaries).

1. **Input Validation:** 
   - `Fetchers` phải đảm bảo `Raw Article` có đủ URL và Title trước khi trả về.
   - `Webhook Endpoint` phải validate chữ ký (signature) và cấu trúc JSON trước khi chuyển cho Pipeline.
2. **Output Validation:**
   - `Knowledge Processing` phải đảm bảo `Knowledge Object` có đủ Summary và Topics trước khi chuyển cho `VectorStores`.
   - `VectorStores` phải đảm bảo Vector có đúng Dimension trước khi Upsert.
3. **Hành động khi Validation thất bại:** Dữ liệu bị loại bỏ ngay lập tức (Drop), ghi log chi tiết lý do và không được phép lan truyền sang các tầng sau.

## Kết luận

Chiến lược xử lý lỗi của AI-Radar được thiết kế để tối ưu hóa sự ổn định và khả năng tự phục hồi. Bằng việc phân loại rõ ràng các nhóm lỗi (Transient, Client, Infrastructure) và áp dụng nguyên tắc Fail Gracefully, hệ thống đảm bảo rằng Knowledge Base luôn được cập nhật liên tục và trải nghiệm người dùng qua Zalo luôn được duy trì, ngay cả khi các dịch vụ bên ngoài hoạt động không ổn định.