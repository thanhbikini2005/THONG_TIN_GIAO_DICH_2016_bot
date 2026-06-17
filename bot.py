"""
GVR Stock Bot - Lấy dữ liệu cổ phiếu GVR và gửi về Telegram
Nguồn dữ liệu: SSI iBoard API (public, không cần auth)
"""

import requests
import json
import time
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CẤU HÌNH - Sửa các giá trị này trong file .env
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "YOUR_CHAT_ID")
SYMBOL             = os.getenv("SYMBOL", "GVR")
INTERVAL_SECONDS   = int(os.getenv("INTERVAL_SECONDS", "300"))  # mặc định 5 phút

# ============================================================
# HEADERS chung cho SSI iBoard
# ============================================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://iboard.ssi.com.vn/",
    "Origin":  "https://iboard.ssi.com.vn",
}


# ============================================================
# 1. LẤY THÔNG TIN TỔNG QUAN (giá TC, trần, sàn, cao, thấp,
#    tổng KL, KL NN mua/bán)
# ============================================================
def get_overview(symbol: str) -> dict:
    url = f"https://iboard-query.ssi.com.vn/v2/stock/second-chart?symbol={symbol}&type=D"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        # SSI iBoard trả về endpoint khác cho quote
    except Exception:
        pass

    # Endpoint chính xác hơn cho quote snapshot
    url = f"https://iboard-query.ssi.com.vn/v2/stock/quote?symbol={symbol}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        if data.get("data"):
            d = data["data"]
            return {
                "symbol":      symbol,
                "price":       d.get("lastPrice") or d.get("matchPrice"),
                "change":      d.get("priceChange"),
                "pct_change":  d.get("priceChangePercent"),
                "ref":         d.get("refPrice"),
                "ceiling":     d.get("ceilingPrice"),
                "floor":       d.get("floorPrice"),
                "high":        d.get("highPrice"),
                "low":         d.get("lowPrice"),
                "total_vol":   d.get("totalMatchVol"),
                "total_val":   d.get("totalMatchVal"),
                "foreign_buy_vol":  d.get("foreignBuyVolTotal"),
                "foreign_sell_vol": d.get("foreignSellVolTotal"),
                "foreign_buy_val":  d.get("foreignBuyValTotal"),
                "foreign_sell_val": d.get("foreignSellValTotal"),
            }
    except Exception as e:
        print(f"[overview] lỗi: {e}")
    return {}


# ============================================================
# 2. LẤY ĐỘ SÂU (order book 3 cấp)
# ============================================================
def get_order_book(symbol: str) -> dict:
    url = f"https://iboard-query.ssi.com.vn/v2/stock/order-book?symbol={symbol}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        if data.get("data"):
            return data["data"]
    except Exception as e:
        print(f"[order_book] lỗi: {e}")
    return {}


# ============================================================
# 3. LẤY KHỚP LỆNH GẦN NHẤT
# ============================================================
def get_recent_matches(symbol: str, limit: int = 10) -> list:
    url = f"https://iboard-query.ssi.com.vn/v2/stock/match?symbol={symbol}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        if data.get("data"):
            return data["data"][:limit]
    except Exception as e:
        print(f"[matches] lỗi: {e}")
    return []


# ============================================================
# 4. LẤY KHỐI LƯỢNG MUA/BÁN CHỦ ĐỘNG (bu/sd)
# ============================================================
def get_bu_sd(symbol: str) -> dict:
    url = f"https://iboard-query.ssi.com.vn/v2/stock/investor?symbol={symbol}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        if data.get("data"):
            d = data["data"]
            return {
                "buy_vol":     d.get("buyVol"),
                "sell_vol":    d.get("sellVol"),
                "unknown_vol": d.get("unknownVol"),
            }
    except Exception as e:
        print(f"[bu_sd] lỗi: {e}")
    return {}


# ============================================================
# 5. GỬI TELEGRAM
# ============================================================
def send_telegram(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[telegram] lỗi: {e}")
        return False


# ============================================================
# 6. ĐỊNH DẠNG TIN NHẮN
# ============================================================
def fmt_num(v, decimals=0):
    if v is None:
        return "N/A"
    try:
        v = float(v)
        if decimals:
            return f"{v:,.{decimals}f}"
        return f"{int(v):,}"
    except Exception:
        return str(v)

def fmt_price(v):
    return fmt_num(v, decimals=2)

def fmt_billion(v):
    """Chuyển VNĐ sang tỷ"""
    if v is None:
        return "N/A"
    try:
        return f"{float(v)/1e9:,.2f} tỷ"
    except Exception:
        return str(v)


def build_message(symbol: str) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    ov   = get_overview(symbol)
    ob   = get_order_book(symbol)
    busd = get_bu_sd(symbol)
    matches = get_recent_matches(symbol, limit=5)

    # --- Header ---
    price    = fmt_price(ov.get("price"))
    change   = ov.get("change", 0) or 0
    pct      = ov.get("pct_change", 0) or 0
    arrow    = "🔺" if float(change) >= 0 else "🔻"

    lines = [
        f"📊 <b>{symbol}</b>  {arrow} <b>{price}</b>  ({change:+.2f} / {pct:+.2f}%)",
        f"🕐 {now}",
        "",
        "━━━━━━ GIÁ THAM CHIẾU ━━━━━━",
        f"TC: {fmt_price(ov.get('ref'))}  |  Trần: {fmt_price(ov.get('ceiling'))}  |  Sàn: {fmt_price(ov.get('floor'))}",
        f"Cao: {fmt_price(ov.get('high'))}  |  Thấp: {fmt_price(ov.get('low'))}",
        "",
        "━━━━━━ TỔNG KHỐI LƯỢNG ━━━━━━",
        f"Tổng KL: {fmt_num(ov.get('total_vol'))}",
        f"Tổng giá trị: {fmt_billion(ov.get('total_val'))}",
    ]

    # --- Mua/bán chủ động ---
    if busd:
        lines += [
            "",
            "━━━━━━ MUA/BÁN CHỦ ĐỘNG ━━━━━━",
            f"🟢 Mua CĐ: {fmt_num(busd.get('buy_vol'))}",
            f"🔴 Bán CĐ: {fmt_num(busd.get('sell_vol'))}",
            f"⚪ Không XĐ: {fmt_num(busd.get('unknown_vol'))}",
        ]

    # --- Độ sâu ---
    if ob:
        bid_prices  = [ob.get(f"bidPrice{i}") for i in range(1,4)]
        bid_vols    = [ob.get(f"bidVolume{i}") for i in range(1,4)]
        ask_prices  = [ob.get(f"askPrice{i}") for i in range(1,4)]
        ask_vols    = [ob.get(f"askVolume{i}") for i in range(1,4)]
        lines += [
            "",
            "━━━━━━ ĐỘ SÂU (3 CẤP) ━━━━━━",
            f"{'KL Mua':>10}  {'G.Mua':>7}  {'G.Bán':>7}  {'KL Bán':>10}",
        ]
        for i in range(3):
            bv = fmt_num(bid_vols[i])  if bid_vols[i]  else "  -  "
            bp = fmt_price(bid_prices[i]) if bid_prices[i] else "  -  "
            ap = fmt_price(ask_prices[i]) if ask_prices[i] else "  -  "
            av = fmt_num(ask_vols[i])  if ask_vols[i]  else "  -  "
            lines.append(f"{bv:>10}  {bp:>7}  {ap:>7}  {av:>10}")

    # --- Khối ngoại ---
    fbuyvol  = ov.get("foreign_buy_vol")
    fsellvol = ov.get("foreign_sell_vol")
    fbuyval  = ov.get("foreign_buy_val")
    fsellval = ov.get("foreign_sell_val")
    if fbuyvol is not None or fbuyval is not None:
        net_vol = (float(fbuyvol or 0) - float(fsellvol or 0))
        net_val = (float(fbuyval or 0) - float(fsellval or 0))
        nn_arrow = "🟢" if net_vol >= 0 else "🔴"
        lines += [
            "",
            "━━━━━━ GIAO DỊCH KHỐI NGOẠI ━━━━━━",
            f"NN Mua: {fmt_num(fbuyvol)} ({fmt_billion(fbuyval)})",
            f"NN Bán: {fmt_num(fsellvol)} ({fmt_billion(fsellval)})",
            f"{nn_arrow} Net KL: {fmt_num(net_vol)}  |  Net GT: {fmt_billion(net_val)}",
        ]

    # --- Khớp lệnh gần nhất ---
    if matches:
        lines += ["", "━━━━━━ KHỚP LỆNH GẦN NHẤT ━━━━━━",
                  f"{'Giờ':>8}  {'Giá':>7}  {'+/-':>5}  {'KL':>8}"]
        for m in matches:
            t   = m.get("time", "")[-8:] if m.get("time") else "--:--:--"
            p   = fmt_price(m.get("price") or m.get("matchPrice"))
            chg = m.get("change") or m.get("priceChange") or 0
            v   = fmt_num(m.get("volume") or m.get("matchVolume"))
            sign = "+" if float(chg) >= 0 else ""
            lines.append(f"{t:>8}  {p:>7}  {sign}{chg:>4}  {v:>8}")

    lines.append(f"\n<a href='https://iboard.ssi.com.vn/dchart/#!/{symbol}'>🔗 Xem chi tiết</a>")
    return "\n".join(lines)


# ============================================================
# 7. CHẠY BOT
# ============================================================
def run_once():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Đang lấy dữ liệu {SYMBOL}...")
    msg = build_message(SYMBOL)
    print(msg)
    ok = send_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, msg)
    print(f"  → Telegram: {'✅ OK' if ok else '❌ Lỗi'}")


def run_loop():
    print(f"🤖 Bot GVR khởi động | symbol={SYMBOL} | interval={INTERVAL_SECONDS}s")
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"[loop] lỗi: {e}")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    import sys
    if "--once" in sys.argv:
        run_once()
    else:
        run_loop()
