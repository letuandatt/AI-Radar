# Logging Strategy

## Mục đích

Tài liệu này định nghĩa chiến lược ghi log (Logging Strategy) và khả năng quan sát (Observability) của AI-Radar. 

Mục tiêu là đảm bảo hệ thống cung cấp đủ thông tin để theo dõi sức khỏe (Health Monitoring), truy vết lỗi (Debugging) và phân tích hiệu năng (Performance Analysis) mà không làm phức tạp hóa kiến trúc hoặc rò rỉ thông tin nhạy cảm. Chiến lược này được thiết kế phù hợp với quy mô của một Knowledge Intelligence System cá nhân, ưu tiên sự đơn giản và hiệu quả.

## Nguyên tắc Logging cốt lõi

Toàn bộ hệ thống AI-Radar tuân thủ 4 nguyên tắc logging sau:

1. **Simplicity First:** Chỉ ghi log những sự kiện có giá trị nghiệp vụ hoặc kỹ thuật. Không over-engineer bằng cách tích hợp các hệ thống log phân tán phức tạp (như ELK Stack, Prometheus) khi chưa có nhu cầu thực tế. Log cục bộ (Console/File) là đủ cho phiên bản đầu tiên.
2. **Security by Design:** Tuyệt đối không ghi log các thông tin nhạy cảm (Secrets, API Keys, Tokens). Việc masking (che giấu) thông tin nhạy cảm là bắt buộc ở tầng hạ tầng (`core/`).
3. **Context-Rich:** Mọi log message phải đi kèm với ngữ cảnh đầy đủ (Module, Pipeline, Action) để Developer có thể truy vết (trace) luồng dữ liệu mà không cần phải đoán.
4. **No PII & No Raw Data:** Không ghi log thông tin định danh cá nhân (PII) của người dùng. Không ghi log toàn bộ nội dung `Raw Article` hoặc `Knowledge Object` (vì quá dài và tốn dung lượng), chỉ ghi log các định danh (ID, Title, URL).

## Phân hạng mức độ Log (Log Levels)

Hệ thống sử dụng 4 mức độ log chuẩn, mỗi mức độ được áp dụng cho các tình huống cụ thể:

| Mức độ | Mục đích sử dụng | Ví dụ trong AI-Radar |
|---|---|---|
| **INFO** | Ghi nhận các sự kiện nghiệp vụ quan trọng, đánh dấu các mốc hoàn thành (Milestones) của Pipeline. | `Pipeline Knowledge Update started`, `Fetched 45 articles from RSS`, `Upserted 30 Knowledge Objects to Qdrant`, `Daily Digest sent successfully`. |
| **WARNING** | Ghi nhận các lỗi có thể phục hồi (Transient), các tình huống ngoại lệ nhưng không làm dừng Pipeline. | `GitHub API rate limit reached, retrying...`, `Raw article missing Title, skipping`, `Retrieval returned 0 results for user question`. |
| **ERROR** | Ghi nhận các lỗi nghiệp vụ nghiêm trọng, một tác vụ hoặc item bị thất bại hoàn toàn. | `Groq API failed after 3 retries`, `Failed to connect to Zalo API`, `Embedding dimension mismatch`. |
| **CRITICAL** | Ghi nhận các lỗi hạ tầng cốt lõi làm sập toàn bộ Pipeline hoặc hệ thống. | `Cannot connect to Qdrant at startup`, `Missing GROQ_API_KEY in environment`, `Scheduler misconfiguration`. |

*Lưu ý:* Mức độ **DEBUG** chỉ được kích hoạt trong môi trường phát triển (Development) để phục vụ việc debug chi tiết. Trong môi trường Production, mức độ log mặc định là **INFO**.

## Chiến lược Log theo Pipeline

Mỗi Pipeline có đặc thù vận hành khác nhau, do đó chiến lược log được điều chỉnh để tập trung vào các chỉ số quan trọng nhất của Pipeline đó.

### 1. Knowledge Update Pipeline (Batch Processing)
Ưu tiên log vào **số lượng (throughput)** và **tỷ lệ thành công/thất bại**.
- **Bắt đầu/Kết thúc:** Log thời gian bắt đầu, thời gian kết thúc và tổng thời gian thực thi (Duration).
- **Acquisition:** Log số lượng bài viết fetch được từ từng nguồn (ví dụ: `RSS: 20, GitHub: 15`).
- **Processing:** Log số lượng `Knowledge Object` tạo thành công, số lượng `Raw Article` bị loại bỏ (do lỗi format hoặc LLM error).
- **Storage:** Log số lượng bản ghi đã upsert thành công vào Qdrant.

### 2. Daily Digest Pipeline (Read-Only)
Ưu tiên log vào **trạng thái tạo bản tin** và **trạng thái phân phối**.
- Log số lượng `Knowledge Object` được chọn để đưa vào Digest.
- Log trạng thái gọi Groq API (thành công / thất bại).
- Log trạng thái gửi tin nhắn qua Zalo (Success / Failed).

### 3. Question Answering Pipeline (Interactive)
Ưu tiên log vào **độ trễ (latency)** và **trạng thái truy xuất**.
- Log thời gian phản hồi端到端 (End-to-end latency) từ lúc nhận Webhook đến lúc gửi phản hồi.
- Log trạng thái Retrieval: Có tìm thấy `Knowledge Object` nào vượt ngưỡng (Threshold) hay không?
- Log lỗi nếu LLM không sinh được câu trả lời (để phân biệt giữa việc "hệ thống không có dữ liệu" và "hệ thống bị lỗi").

## Bảo mật Log (Logging Security)

Để tuân thủ nguyên tắc *Security by Simplicity* (SDD Chương 11), tầng Logging thiết lập các ranh giới cứng sau:

1. **Secret Masking:** `core/logger.py` phải tích hợp cơ chế tự động quét và che giấu (mask) các chuỗi ký tự khớp với pattern của API Key hoặc Token trước khi ghi ra Console/File.
2. **No Payload Dumping:** Nghiêm cấm việc log toàn bộ HTTP Request/Response payload từ các dịch vụ bên ngoài (Groq, Zalo). Chỉ log HTTP Status Code, Endpoint và Response Time.
3. **No Raw Content:** Không log trường `content` của `Raw Article` hoặc `summary` của `Knowledge Object`. Chỉ log `title` và `url` để phục vụ việc truy vết bài viết bị lỗi.

## Định dạng và Cấu trúc Log (Format & Structure)

Để cân bằng giữa khả năng đọc của con người (Human-readable) và khả năng xử lý của máy móc (Machine-parseable), hệ thống áp dụng chiến lược định dạng log theo môi trường:

- **Môi trường Development:** Sử dụng định dạng **Text** màu sắc (Colorized), dễ đọc, căn chỉnh dòng thẳng hàng trên Console.
- **Môi trường Production:** Sử dụng định dạng **JSON** (Structured Logging). Mỗi dòng log là một JSON object hợp lệ, giúp dễ dàng grep, filter hoặc tích hợp với các log aggregator trong tương lai.

**Cấu trúc chuẩn của một JSON Log:**
```json
{
  "timestamp": "2024-05-20T06:00:15.123Z",
  "level": "INFO",
  "module": "knowledge_update_pipeline",
  "pipeline": "update",
  "message": "Knowledge Update Pipeline completed successfully",
  "extra": {
    "duration_seconds": 145,
    "articles_fetched": 45,
    "knowledge_objects_created": 30
  }
}
```

## Ánh xạ Source Code (Source Mapping)

Chiến lược logging được hiện thực hóa và quản lý tập trung tại tầng Core Infrastructure, tuân thủ đúng `FolderStructure.md`.

| Thành phần | Vị trí Source Code | Trách nhiệm |
|---|---|---|
| **Logger Core** | `app/core/logger.py` | Khởi tạo Logger, định nghĩa Format (Text/JSON), xử lý Secret Masking, cung cấp interface `get_logger(module_name)` cho các module khác. |
| **Log Configuration** | `app/config/settings.py` | Quản lý biến `LOG_LEVEL` (DEBUG/INFO/WARNING/ERROR) và `LOG_FORMAT` (text/json) từ Environment Variables. |
| **Pipeline Logging** | `app/pipelines/` | Gọi Logger để ghi nhận các Milestone (Start, End, Summary stats). |
| **Integration Logging** | `app/integrations/` | Gọi Logger để ghi nhận HTTP Status, Latency, và các lỗi kết nối (đã được mask secret). |

**Nguyên tắc sử dụng:**
- Các module nghiệp vụ (`fetchers/`, `knowledge/`, `services/`) không tự khởi tạo Logger. Chúng phải gọi `get_logger(__name__)` từ `core/logger.py` để đảm bảo tính nhất quán về định dạng và cấu hình.

## Kết luận

Chiến lược Logging của AI-Radar được thiết kế để tối ưu hóa sự đơn giản và an toàn. Bằng việc tập trung vào các sự kiện nghiệp vụ cốt lõi, áp dụng Structured Logging cho môi trường Production và tuân thủ nghiêm ngặt các quy tắc bảo mật (Masking, No Raw Data), hệ thống đảm bảo khả năng quan sát (Observability) đầy đủ mà không làm tăng độ phức tạp của kiến trúc hay rủi ro rò rỉ thông tin.