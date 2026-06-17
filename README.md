# 📊 GVR Stock Bot → Telegram

Bot tự động lấy dữ liệu cổ phiếu (GVR hoặc bất kỳ mã nào) từ **SSI iBoard API** (miễn phí, không cần đăng ký) và gửi về Telegram.

## Dữ liệu được gửi

| Mục | Chi tiết |
|-----|----------|
| Giá & biến động | Giá khớp, +/-, %, TC / Trần / Sàn, Cao / Thấp |
| Khối lượng tổng | Tổng KL, Tổng giá trị |
| Mua/bán chủ động | Mua CĐ, Bán CĐ, Không xác định |
| Độ sâu (3 cấp) | KL Mua / Giá Mua / Giá Bán / KL Bán |
| Khối ngoại | NN Mua, NN Bán, Net KL, Net Giá trị |
| Khớp lệnh gần nhất | 5 lệnh khớp cuối: giờ, giá, +/-, KL |

---

## Cách chạy trên GitHub Actions (miễn phí, không cần server)

### Bước 1: Tạo Telegram Bot

1. Nhắn tin `/newbot` cho [@BotFather](https://t.me/BotFather)
2. Đặt tên → nhận **BOT_TOKEN** (dạng `123456:ABC-xyz...`)
3. Nhắn tin cho [@userinfobot](https://t.me/userinfobot) để lấy **CHAT_ID** của bạn
4. Start bot của bạn (nhắn `/start`)

### Bước 2: Tạo GitHub Repository

```bash
git init
git add .
git commit -m "init GVR bot"
gh repo create gvr-stock-bot --public --push
```

### Bước 3: Thêm Secrets vào GitHub

Vào **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Giá trị |
|--------|---------|
| `TELEGRAM_BOT_TOKEN` | Token từ BotFather |
| `TELEGRAM_CHAT_ID` | Chat ID của bạn |

Muốn đổi mã CK: vào **Variables** (không phải Secrets) → thêm `SYMBOL = HPG`

### Bước 4: Bật Actions

Vào tab **Actions** → chọn workflow `GVR Stock Bot` → **Enable workflow**

Bot sẽ tự chạy mỗi **5 phút** vào **thứ 2–6, từ 9:00–15:15** (giờ Hà Nội).

---

## Chạy thủ công trên máy local

```bash
# Cài dependencies
pip install -r requirements.txt

# Copy và điền thông tin
cp .env.example .env
nano .env   # điền TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID

# Chạy 1 lần
python bot.py --once

# Chạy vòng lặp (tự gửi mỗi 5 phút)
python bot.py
```

---

## Cấu trúc file

```
gvr-stock-bot/
├── bot.py                        # Script chính
├── requirements.txt
├── .env.example                  # Template cấu hình
└── .github/
    └── workflows/
        └── stock_bot.yml         # GitHub Actions schedule
```

---

## Đổi mã cổ phiếu

Trong `.env` (local) hoặc GitHub Variable:
```
SYMBOL=HPG   # hoặc VIC, VNM, TCB, ...
```

---

## Nguồn dữ liệu

API công khai của **SSI iBoard** (`iboard-query.ssi.com.vn`) — dữ liệu có độ trễ ~1 phút so với real-time.

> Nếu API SSI thay đổi, có thể thay bằng TCBS API (`apipubaws.tcbs.com.vn`) hoặc VietStock.
