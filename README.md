# TÀI NGUYÊN MMO — Telegram Shop (starter)

Telegram shop bán **tài nguyên số hợp pháp** với quản trị hoàn toàn qua Telegram Admin.
Bao gồm: danh mục sản phẩm, nhập kho TXT, mua hàng trừ ví, kho đã mua, yêu cầu nạp tiền,
SePay webhook (API Key), SQLite và Docker.

> Không dùng hệ thống để bán tài khoản bị chiếm đoạt, dữ liệu cá nhân, thông tin đăng nhập
> không được phép phân phối hoặc dịch vụ vi phạm điều khoản nền tảng.

## 1. Chuẩn bị

- Bot token từ [@BotFather](https://t.me/BotFather)
- Telegram numeric user ID của admin (có thể lấy bằng bot hiển thị ID)
- VPS Ubuntu có Docker + Docker Compose
- Tài khoản SePay đã liên kết ngân hàng và bật Webhook

## 2. Cấu hình

```bash
cp .env.example .env
nano .env
```

Điền tối thiểu:
- `BOT_TOKEN`: token bot Telegram
- `ADMIN_IDS`: Telegram numeric ID, nhiều admin phân cách dấu phẩy
- `SEPAY_API_KEY`: API Key dùng cho webhook SePay
- `BANK_BIN`, `BANK_ACCOUNT`, `BANK_ACCOUNT_NAME`: thông tin tài khoản nhận tiền
- `SUPPORT_USERNAME`: username hỗ trợ, không có dấu @

Tạo `SECRET` mạnh cho `SEPAY_API_KEY`; không chia sẻ file `.env` hoặc token bot.

## 3. Chạy bằng Docker

```bash
docker compose up -d --build
docker compose logs -f
```

Mở cổng `8000` trên firewall và cấu hình domain + HTTPS reverse proxy (Nginx/Caddy).
Webhook URL production nên là:

`https://TEN-MIEN-CUA-BAN/sepay/webhook`

Không đưa webhook lên production qua HTTP thường.

## 4. Cấu hình SePay

Trong SePay Dashboard → Tích hợp → Webhooks:
1. Tạo webhook, sự kiện **Có tiền vào**.
2. URL: `https://TEN-MIEN-CUA-BAN/sepay/webhook`
3. Content-Type: JSON.
4. Xác thực: API Key; dán đúng giá trị `SEPAY_API_KEY`.
5. Lưu và gửi thử webhook.

Ứng dụng kiểm tra `Authorization: Apikey ...`, chỉ ghi nhận giao dịch tiền vào,
đối chiếu mã nạp trong nội dung chuyển khoản và số tiền, đồng thời chống cộng tiền trùng
bằng ID giao dịch SePay. Mặc định yêu cầu nạp hết hạn sau 15 phút; giao dịch hết hạn
không tự cộng ví, cần admin đối soát thủ công.

SePay có tài liệu về webhook và các chế độ xác thực:
- https://developer.sepay.vn/vi/sepay-webhooks
- https://docs.sepay.vn/tich-hop-webhooks.html

## 5. Lệnh người dùng

- `/start` — menu
- `/sanpham` — sản phẩm
- `/sodu` — số dư
- `/kho` — tài nguyên đã mua
- `/naptien 50000` — tạo yêu cầu nạp 50.000đ
- `/hotro` — hỗ trợ

## 6. Lệnh Admin (chỉ ADMIN_IDS)

- `/admin` — bảng lệnh admin
- `/addproduct SKU | Tên sản phẩm | Giá | Mô tả`
- `/addstock SKU` — sau đó gửi file `.txt`, mỗi dòng là một tài nguyên
- `/products` — xem sản phẩm và tồn kho
- `/orders` — xem 20 đơn hàng gần nhất
- `/users` — xem số người dùng đã tương tác

Ví dụ:

```text
/addproduct ebook_mmo | Ebook MMO hợp pháp | 49000 | Tài liệu hướng dẫn marketing
/addstock ebook_mmo
```

Sau lệnh `/addstock`, gửi file TXT trong vòng 5 phút. Mỗi dòng không rỗng được xem là
một đơn vị tài nguyên số. Không nhập mật khẩu, cookie, token phiên, dữ liệu cá nhân
hoặc thông tin truy cập không được phép chuyển nhượng.

## 7. Kiểm thử

1. Chạy bot và nhắn `/start`.
2. Admin thêm sản phẩm và nhập kho bằng TXT.
3. Tạo yêu cầu nạp thử với số tiền nhỏ.
4. Dùng chức năng test webhook trong SePay hoặc môi trường test.
5. Kiểm tra `/sodu`, `/kho`, `/orders`.

## 8. Lưu ý vận hành

- Đây là bộ khung MVP; trước khi kinh doanh thật cần kiểm thử webhook với tài khoản SePay
  của bạn, HTTPS, backup SQLite, giới hạn truy cập VPS và quy trình hoàn tiền.
- Không tự cộng tiền dựa trên ảnh chụp giao dịch.
- Sao lưu thư mục `data/` định kỳ.
- Không gửi token bot, API key, mật khẩu VPS hoặc `.env` vào cuộc trò chuyện.
