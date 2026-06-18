"""
GVR Stock Bot v2 - Dữ liệu từ TCBS API (ổn định, không cần auth)
+ Debug rõ ràng hơn cho Telegram errors
"""

import requests
import time
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# CẤU HÌNH
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
SYMBOL             = os.getenv("SYMBOL", "GVR")
INTERVAL_SECONDS   = int(os.getenv("INTERVAL_SECONDS", "300"))

TCBS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://tcinvest.tcbs.com.vn/",
    "Origin":  "https://tcinvest.tcbs.com.vn",
}

FIREANT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://fireant.vn/",
}

# ============================================================
# HELPERS
# ============================================================
def fmt_num(v, decimals=0):
    if v is None: return "N/A"
    try:
        v = float(v)
        if decimals: return f"{v:,.{decimals}f}"
        return f"{int(v):,}"
    except Exception: return str(v)

def fmt_price(v): return fmt_num(v, 2)

def fmt_billion(v):
    if v is None: return "N/A"
    try:
        b = float(v) / 1e9
        return f"{b:,.2f} tỷ"
    except Exception: return str(v)

def safe_float(v, default=0.0):
    try: return float(v)
    except Exception: return default


# ============================================================
# 1. TCBS - Giá tổng quan + khối ngoại
# ============================================================
def get_tcbs_overview(symbol: str) -> dict:
    """
    TCBS public API - không cần auth
    """
    url = f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/second-chart?ticker={symbol}&type=D"
    result = {}
    try:
        r = requests.get(url, headers=TCBS_HEADERS, timeout=12)
        print(f"  [TCBS overview] status={r.status_code}")
        data = r.json()
        # endpoint này trả mảng nến ngày, lấy nến cuối
        if isinstance(data, dict) and data.get("data"):
            items = data["data"]
            if items:
                last = items[-1]
                result = {
                    "high":      last.get("h") or last.get("highPrice"),
                    "low":       last.get("l") or last.get("lowPrice"),
                    "open":      last.get("o") or last.get("openPrice"),
                    "close":     last.get("c") or last.get("closePrice"),
                    "total_vol": last.get("v") or last.get("volume"),
                }
    except Exception as e:
        print(f"  [TCBS overview] lỗi: {e}")

    # quote realtime
    url2 = f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/quote?ticker={symbol}"
    try:
        r2 = requests.get(url2, headers=TCBS_HEADERS, timeout=12)
        print(f"  [TCBS quote] status={r2.status_code}")
        d2 = r2.json()
        if isinstance(d2, dict):
            q = d2.get("data") or d2
            if isinstance(q, list) and q: q = q[0]
            if isinstance(q, dict):
                result.update({
                    "symbol":          symbol,
                    "price":           q.get("lastPrice") or q.get("matchPrice") or q.get("close"),
                    "change":          q.get("priceChange") or q.get("change"),
                    "pct_change":      q.get("priceChangeRatio") or q.get("percentChange"),
                    "ref":             q.get("refPrice") or q.get("referencePrice"),
                    "ceiling":         q.get("ceilingPrice") or q.get("ceiling"),
                    "floor":           q.get("floorPrice") or q.get("floor"),
                    "high":            result.get("high") or q.get("highPrice") or q.get("high"),
                    "low":             result.get("low") or q.get("lowPrice") or q.get("low"),
                    "total_vol":       result.get("total_vol") or q.get("totalMatchVol") or q.get("volume"),
                    "total_val":       q.get("totalMatchVal") or q.get("totalValue"),
                    "foreign_buy_vol": q.get("foreignBuyVolTotal") or q.get("fBuyVol"),
                    "foreign_sell_vol":q.get("foreignSellVolTotal") or q.get("fSellVol"),
                    "foreign_buy_val": q.get("foreignBuyValTotal") or q.get("fBuyVal"),
                    "foreign_sell_val":q.get("foreignSellValTotal") or q.get("fSellVal"),
                })
    except Exception as e:
        print(f"  [TCBS quote] lỗi: {e}")
    return result


# ============================================================
# 2. TCBS - Khớp lệnh gần nhất
# ============================================================
def get_tcbs_matches(symbol: str, limit: int = 5) -> list:
    url = f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/intraday?ticker={symbol}&page=0&size={limit}"
    try:
        r = requests.get(url, headers=TCBS_HEADERS, timeout=12)
        print(f"  [TCBS intraday] status={r.status_code}")
        data = r.json()
        items = data.get("data") or data.get("intraday") or []
        if isinstance(items, list):
            return items[:limit]
    except Exception as e:
        print(f"  [TCBS intraday] lỗi: {e}")
    return []


# ============================================================
# 3. TCBS - Độ sâu (order book)
# ============================================================
def get_tcbs_orderbook(symbol: str) -> dict:
    url = f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/orderbook?ticker={symbol}"
    try:
        r = requests.get(url, headers=TCBS_HEADERS, timeout=12)
        print(f"  [TCBS orderbook] status={r.status_code}")
        data = r.json()
        return data.get("data") or data or {}
    except Exception as e:
        print(f"  [TCBS orderbook] lỗi: {e}")
    return {}


# ============================================================
# 4. TCBS - Mua/bán chủ động
# ============================================================
def get_tcbs_busd(symbol: str) -> dict:
    # lấy từ intraday aggregation
    url = f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/trading-statistics?ticker={symbol}"
    try:
        r = requests.get(url, headers=TCBS_HEADERS, timeout=12)
        print(f"  [TCBS busd] status={r.status_code}")
        data = r.json()
        d = data.get("data") or data
        if isinstance(d, dict):
            return {
                "buy_vol":     d.get("buyVol") or d.get("activeBuyVol"),
                "sell_vol":    d.get("sellVol") or d.get("activeSellVol"),
                "unknown_vol": d.get("unknownVol"),
            }
    except Exception as e:
        print(f"  [TCBS busd] lỗi: {e}")
    return {}


# ============================================================
# 5. Fireant fallback - Giá + khối ngoại
# ============================================================
def get_fireant_overview(symbol: str) -> dict:
    url = f"https://restv2.fireant.vn/symbols/{symbol}/quote"
    try:
        r = requests.get(url, headers=FIREANT_HEADERS, timeout=12)
        print(f"  [Fireant quote] status={r.status_code}")
        if r.status_code == 200:
            d = r.json()
            return {
                "symbol":          symbol,
                "price":           d.get("lastPrice") or d.get("price"),
                "change":          d.get("change"),
                "pct_change":      d.get("percentChange") or d.get("changePercent"),
                "ref":             d.get("referencePrice"),
                "ceiling":         d.get("ceilingPrice"),
                "floor":           d.get("floorPrice"),
                "high":            d.get("highPrice") or d.get("high"),
                "low":             d.get("lowPrice") or d.get("low"),
                "total_vol":       d.get("totalVolume") or d.get("volume"),
                "total_val":       d.get("totalValue") or d.get("value"),
                "foreign_buy_vol": d.get("foreignBuyVolume"),
                "foreign_sell_vol":d.get("foreignSellVolume"),
                "foreign_buy_val": d.get("foreignBuyValue"),
                "foreign_sell_val":d.get("foreignSellValue"),
            }
    except Exception as e:
        print(f"  [Fireant] lỗi: {e}")
    return {}


# ============================================================
# 6. Gửi Telegram - có debug chi tiết
# ============================================================
def send_telegram(token: str, chat_id: str, text: str) -> bool:
    if not token or token == "YOUR_BOT_TOKEN":
        print("  ❌ TELEGRAM_BOT_TOKEN chưa được set!")
        return False
    if not chat_id or chat_id == "YOUR_CHAT_ID":
        print("  ❌ TELEGRAM_CHAT_ID chưa được set!")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        print(f"  [Telegram] status={r.status_code}")
        if r.status_code != 200:
            print(f"  [Telegram] response: {r.text[:300]}")
        return r.status_code == 200
    except Exception as e:
        print(f"  [Telegram] exception: {e}")
        return False


# ============================================================
# 7. Build tin nhắn
# ============================================================
def build_message(symbol: str) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # Thử TCBS trước, fallback sang Fireant
    print("  Đang gọi TCBS...")
    ov = get_tcbs_overview(symbol)
    if not ov.get("price"):
        print("  TCBS không có dữ liệu, thử Fireant...")
        ov = get_fireant_overview(symbol)

    ob      = get_tcbs_orderbook(symbol)
    busd    = get_tcbs_busd(symbol)
    matches = get_tcbs_matches(symbol, limit=5)

    price  = safe_float(ov.get("price"))
    change = safe_float(ov.get("change"))
    pct    = safe_float(ov.get("pct_change"))
    # TCBS trả pct dạng 0.0086 → nhân 100
    if abs(pct) < 1 and pct != 0: pct *= 100
    arrow  = "🔺" if change >= 0 else "🔻"

    price_str = fmt_price(ov.get("price")) if ov.get("price") else "N/A"

    lines = [
        f"📊 <b>{symbol}</b>  {arrow} <b>{price_str}</b>  ({change:+.2f} / {pct:+.2f}%)",
        f"🕐 {now}",
        "",
        "━━━━━━ GIÁ THAM CHIẾU ━━━━━━",
        f"TC: {fmt_price(ov.get('ref'))}  |  Trần: {fmt_price(ov.get('ceiling'))}  |  Sàn: {fmt_price(ov.get('floor'))}",
        f"Cao: {fmt_price(ov.get('high'))}  |  Thấp: {fmt_price(ov.get('low'))}",
        "",
        "━━━━━━ TỔNG KHỐI LƯỢNG ━━━━━━",
        f"Tổng KL: {fmt_num(ov.get('total_vol'))}",
        f"Tổng GT: {fmt_billion(ov.get('total_val'))}",
    ]

    # Mua/bán chủ động
    if busd and any(busd.values()):
        lines += [
            "",
            "━━━━━━ MUA/BÁN CHỦ ĐỘNG ━━━━━━",
            f"🟢 Mua CĐ : {fmt_num(busd.get('buy_vol'))}",
            f"🔴 Bán CĐ : {fmt_num(busd.get('sell_vol'))}",
            f"⚪ Không XĐ: {fmt_num(busd.get('unknown_vol'))}",
        ]

    # Độ sâu
    bids = ob.get("bids") or ob.get("bidList") or []
    asks = ob.get("asks") or ob.get("askList") or []
    if bids or asks:
        lines += ["", "━━━━━━ ĐỘ SÂU (3 CẤP) ━━━━━━",
                  f"{'KL Mua':>10}  {'G.Mua':>7}  {'G.Bán':>7}  {'KL Bán':>10}"]
        for i in range(3):
            bp = bids[i].get("p") or bids[i].get("price") if i < len(bids) else None
            bv = bids[i].get("v") or bids[i].get("volume") if i < len(bids) else None
            ap = asks[i].get("p") or asks[i].get("price") if i < len(asks) else None
            av = asks[i].get("v") or asks[i].get("volume") if i < len(asks) else None
            lines.append(
                f"{fmt_num(bv):>10}  {fmt_price(bp):>7}  {fmt_price(ap):>7}  {fmt_num(av):>10}"
            )
    else:
        # Thử field dạng bidPrice1, askPrice1
        has_ob = any(ob.get(f"bidPrice{i}") for i in range(1,4))
        if has_ob:
            lines += ["", "━━━━━━ ĐỘ SÂU (3 CẤP) ━━━━━━",
                      f"{'KL Mua':>10}  {'G.Mua':>7}  {'G.Bán':>7}  {'KL Bán':>10}"]
            for i in range(1, 4):
                bp = ob.get(f"bidPrice{i}"); bv = ob.get(f"bidVolume{i}")
                ap = ob.get(f"askPrice{i}"); av = ob.get(f"askVolume{i}")
                lines.append(
                    f"{fmt_num(bv):>10}  {fmt_price(bp):>7}  {fmt_price(ap):>7}  {fmt_num(av):>10}"
                )

    # Khối ngoại
    fbuyvol  = ov.get("foreign_buy_vol")
    fsellvol = ov.get("foreign_sell_vol")
    fbuyval  = ov.get("foreign_buy_val")
    fsellval = ov.get("foreign_sell_val")
    if any(x is not None for x in [fbuyvol, fsellvol]):
        net_vol = safe_float(fbuyvol) - safe_float(fsellvol)
        net_val = safe_float(fbuyval) - safe_float(fsellval)
        nn_arrow = "🟢" if net_vol >= 0 else "🔴"
        lines += [
            "",
            "━━━━━━ GIAO DỊCH KHỐI NGOẠI ━━━━━━",
            f"NN Mua: {fmt_num(fbuyvol)} ({fmt_billion(fbuyval)})",
            f"NN Bán: {fmt_num(fsellvol)} ({fmt_billion(fsellval)})",
            f"{nn_arrow} Net KL: {fmt_num(net_vol)}  |  Net GT: {fmt_billion(net_val)}",
        ]

    # Khớp lệnh
    if matches:
        lines += ["", "━━━━━━ KHỚP LỆNH GẦN NHẤT ━━━━━━",
                  f"{'Giờ':>8}  {'Giá':>7}  {'+/-':>5}  {'KL':>8}"]
        for m in matches:
            t   = (m.get("t") or m.get("time") or "")
            if len(t) > 8: t = t[-8:]
            p   = m.get("p") or m.get("price") or m.get("matchPrice") or m.get("lastPrice")
            chg = safe_float(m.get("a") or m.get("change") or m.get("priceChange"))
            v   = m.get("v") or m.get("vol") or m.get("volume") or m.get("matchVolume")
            sign = "+" if chg >= 0 else ""
            lines.append(f"{t:>8}  {fmt_price(p):>7}  {sign}{chg:>4}  {fmt_num(v):>8}")

    if ov.get("price"):
        lines.append(f"\n<a href='https://tcinvest.tcbs.com.vn/{symbol}'>🔗 Xem trên TCBS</a>")
    else:
        lines.append("\n⚠️ Có thể ngoài giờ giao dịch hoặc API tạm thời không khả dụng.")

    return "\n".join(lines)


# ============================================================
# 8. CHẠY
# ============================================================
def run_once():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Đang lấy dữ liệu {SYMBOL}...")
    print(f"  TOKEN set: {'✅' if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN != 'YOUR_BOT_TOKEN' else '❌ CHƯA SET'}")
    print(f"  CHAT_ID set: {'✅' if TELEGRAM_CHAT_ID and TELEGRAM_CHAT_ID != 'YOUR_CHAT_ID' else '❌ CHƯA SET'}")
    msg = build_message(SYMBOL)
    print("--- Preview tin nhắn ---")
    print(msg)
    print("------------------------")
    ok = send_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, msg)
    print(f"  → Telegram: {'✅ OK' if ok else '❌ Lỗi'}")
    if not ok:
        sys.exit(1)  # Báo lỗi để GitHub Actions thấy

def run_loop():
    print(f"🤖 Bot {SYMBOL} | interval={INTERVAL_SECONDS}s")
    while True:
        try: run_once()
        except Exception as e: print(f"[loop] lỗi: {e}")
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
    else:
        run_loop()
