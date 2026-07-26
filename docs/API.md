# Tài liệu API AI-Radar

## 1. Giới thiệu
AI-Radar là một hệ thống Knowledge Intelligence được thiết kế để tự động thu thập, xử lý và truy xuất tri thức liên quan đến AI. Tài liệu này mô tả các interface mà AI-Radar cung cấp để tương tác với hệ thống, bao gồm Internal API và Webhook.

**Phạm vi:**
- **Internal/Admin API:** Được sử dụng bởi bộ lập lịch (ví dụ: GitHub Actions) hoặc quản trị viên để kích hoạt các quy trình nền.
- **External Webhook:** Được sử dụng bởi Zalo Official Account (OA) để nhận tin nhắn từ người dùng và gửi thông báo.

**Mối quan hệ với các tài liệu khác:**
- SDD mô tả yêu cầu và chức năng của hệ thống.
- Architecture mô tả cấu trúc và cách tổ chức hệ thống.
- Decision Log giải thích các quyết định thiết kế.
- API mô tả các interface được cung cấp bởi AI-Radar để tương tác với hệ thống.

**Lưu ý:** AI-Radar không cung cấp REST API công khai cho việc truy cập dữ liệu chung. Mọi thao tác truy xuất tri thức đều được xử lý thông qua Question Answering Pipeline qua kênh Zalo.

## 2. Base URL & Môi trường
Base URL phụ thuộc vào môi trường triển khai.

Ví dụ:

- Local Development
- Production

Giá trị cụ thể được xác định bởi cấu hình triển khai.

Tất cả các endpoint đều tương đối so với Base URL này.

## 3. Xác thực & Bảo mật
Để bảo vệ các endpoint nội bộ khỏi truy cập trái phép, AI-Radar sử dụng cơ chế API Key đơn giản.

### Xác thực Internal API
- **Header:** `X-API-Key`
- **Giá trị:** API Key được cấu hình trong môi trường triển khai.
- **Cách dùng:** Bắt buộc cho tất cả các endpoint dưới đường dẫn `/api/`.

### Bảo mật Webhook
- **Cơ chế:** Xác thực chữ ký Webhook của Zalo OA.
- **Quy trình:** Hệ thống xác thực tham số `signature` trong payload webhook dựa trên Webhook Secret được cấu hình trong môi trường.
- **Hành động:** Các yêu cầu có chữ ký không hợp lệ sẽ bị từ chối với mã `401 Unauthorized`.

## 4. Quy ước chung
- **HTTP Methods:** Chủ yếu là `POST` để kích hoạt hành động và nhận webhooks. `GET` cho kiểm tra sức khỏe hệ thống.
- **Content-Type:** `application/json` cho tất cả phần thân yêu cầu và phản hồi.
- **Encoding:** UTF-8.
- **Quy ước đặt tên:** Tất cả các trường JSON sử dụng `snake_case`.

## 5. Định dạng Phản hồi Chuẩn

### Phản hồi Thành công
```json
{
  "status": "success",
  "data": {
    // Payload cụ thể cho từng endpoint
  },
  "timestamp": "<ISO8601 Timestamp>"
}
```

### Phản hồi Lỗi
```json
{
  "status": "error",
  "code": "ERROR_CODE",
  "message": "Mô tả lỗi dễ hiểu cho con người",
  "timestamp": "<ISO8601 Timestamp>"
}
```

## 6. Xử lý Lỗi
Hệ thống sử dụng các mã trạng thái HTTP chuẩn kết hợp với mã lỗi tùy chỉnh trong phần thân phản hồi.

| HTTP Status | Custom Code | Mô tả | Hành động khuyến nghị |
| :--- | :--- | :--- | :--- |
| 400 | `INVALID_PAYLOAD` | Phần thân yêu cầu bị sai định dạng hoặc thiếu trường bắt buộc. | Kiểm tra lại định dạng yêu cầu. |
| 401 | `UNAUTHORIZED` | Thiếu hoặc sai `X-API-Key` / Chữ ký Webhook. | Xác minh lại thông tin xác thực. |
| 403 | `FORBIDDEN` | Truy cập bị từ chối cho vai trò/ngữ cảnh hiện tại. | Liên hệ quản trị viên. |
| 500 | `INTERNAL_ERROR` | Lỗi máy chủ không mong đợi. | Thử lại sau; kiểm tra log nếu lỗi kéo dài. |
| 503 | `SERVICE_UNAVAILABLE` | Dịch vụ cốt lõi (Qdrant/Groq) ngừng hoạt động. | Chờ dịch vụ phục hồi. |

## 7. API Endpoints

### 7.1 Health Check
Kiểm tra trạng thái hoạt động của ứng dụng và các phụ thuộc cốt lõi.

- **Endpoint:** `GET /health`
- **Xác thực:** Không (Công khai)
- **Phản hồi (200 OK):**
```json
{
  "status": "healthy",
  "services": {
    "qdrant": "connected",
    "groq": "available"
  }
}
```

### 7.2 Trigger Knowledge Update
Kích hoạt thủ công **Knowledge Update Pipeline**. Thường được gọi bởi GitHub Actions Cron hoặc script admin.

- **Endpoint:** `POST /api/v1/update`
- **Xác thực:** Bắt buộc (`X-API-Key`)
- **Request Body:** (Tùy chọn)
```json
{
  "force_refresh": false
}
```

- **Phản hồi (200 OK):**
```json
{
  "status": "success",
  "data": {
    "job_id": "uuid-1234-5678",
    "message": "Knowledge Update Pipeline đã bắt đầu."
  }
}
```

- **Ghi chú:**
  - Pipeline chạy bất đồng bộ. Endpoint này chỉ xác nhận job đã được xếp hàng/bắt đầu.
  - Nếu `force_refresh` là true, hệ thống có thể bỏ qua kiểm tra trùng lặp cho lần chạy hiện tại.

## 8. Webhooks

### 8.1 Zalo OA Webhook
Nhận tin nhắn từ người dùng và gửi xác nhận về nền tảng Zalo.

- **Endpoint:** `POST /webhooks/zalo`
- **Xác thực:** Xác thực chữ ký (Nội bộ)
- **Request Payload (Ví dụ từ Zalo):**
```json
{
  "event": "user_send_msg",
  "sender": {
    "id": "user_zalo_id_123"
  },
  "message": {
    "text": "Framework OCR mới nhất là gì?",
    "type": "text"
  },
  "timestamp": 1722000000
}
```

- **Phản hồi (200 OK):**
```json
{
  "status": "received"
}
```

- **Ghi chú:**
  - Hệ thống phải phản hồi với `200 OK` trong vòng **3 giây** để tránh timeout từ Zalo.
  - Việc sinh câu trả lời thực tế và gửi tin nhắn diễn ra bất đồng bộ sau bước xác nhận này.
  - Nếu chữ ký không hợp lệ, trả về `401 Unauthorized`.

## 9. Tham chiếu Mô hình Dữ liệu

### HealthStatus
| Trường | Kiểu | Mô tả |
| :--- | :--- | :--- |
| `status` | String | Trạng thái tổng thể của hệ thống ("healthy", "degraded"). |
| `services` | Object | Trạng thái của các phụ thuộc riêng lẻ. |

### UpdateTriggerRequest
| Trường | Kiểu | Bắt buộc | Mô tả |
| :--- | :--- | :--- | :--- |
| `force_refresh` | Boolean | Không | Nếu true, bỏ qua một số kiểm tra cache/trùng lặp. |

### ZaloWebhookPayload
| Trường | Kiểu | Mô tả |
| :--- | :--- | :--- |
| `event` | String | Loại sự kiện (ví dụ: "user_send_msg"). |
| `sender.id` | String | ID duy nhất của người dùng Zalo. |
| `message.text` | String | Nội dung tin nhắn của người dùng. |
| `timestamp` | Integer | Unix timestamp của sự kiện. |

## 10. Quản lý Phiên bản
- **Phiên bản hiện tại:** v1
- **Chiến lược:** URI Versioning (nếu áp dụng cho HTTP API). (ví dụ: `/api/v1/...`).
- **Chính sách:** Vì đây là dự án cá nhân, các thay đổi phá vỡ tương thích (breaking changes) có thể xảy ra mà không cần thông báo deprecation trước trong giai đoạn đầu. Tuy nhiên, giao diện Webhook cho Zalo sẽ được giữ ổn định để đảm bảo hoạt động liên tục.