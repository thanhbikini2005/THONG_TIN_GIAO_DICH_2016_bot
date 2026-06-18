"""
GVR Stock Bot v3
Nguồn dữ liệu (theo thứ tự ưu tiên, tự động fallback):
  1. VietStock API (không block IP quốc tế)
  2. CafeF API
  3. Alpha Vantage (cần API key miễn phí)
  4. Yahoo Finance (toàn cầu, không block)
  5. Wifeed / MSN Finance scrape
"""

import requests, time, os, sys, json, re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
SYMBOL             = os.getenv("SYMBOL", "GVR")
INTERVAL_SECONDS   = int(os.getenv("INTERVAL_SECONDS", "300"))

# ============================================================
# HELPERS
# ============================================================
def fmt_num(v, dec=0):
    if v is None: return "N/A"
    try:
        v = float(v)
        return f"{v:,.{dec}f}" if dec else f"{int(v):,}"
    except: return str(v)

def fmt_price(v): return fmt_num(v, 2)

def fmt_billion(v):
    if v is None: return "N/A"
    try: return f"{float(v)/1e9:,.2f} tỷ"
    except: return "N/A"

def safe_float(v, default=0.0):
    try: return float(v)
    except: return default

def get(url, headers=None, timeout=15, params=None):
    """GET với retry 2 lần"""
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    if headers: h.update(headers)
    for attempt in range(2):
        try:
            r = requests.get(url, headers=h, params=params, timeout=timeout)
            print(f"  GET {url[:80]}... → {r.status_code}")
            return r
        except Exception as e:
            print(f"  GET lỗi (lần {attempt+1}): {e}")
            time.sleep(2)
    return None

# ============================================================
# NGUỒN 1: Yahoo Finance (không block IP quốc tế)
# Symbol VN: GVR.VN
# ============================================================
def src_yahoo(symbol: str) -> dict:
    ticker = f"{symbol}.VN"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"interval": "1d", "range": "5d"}
    r = get(url, params=params)
    if not r or r.status_code != 200: return {}
    try:
        data = r.json()
        meta = data["chart"]["result"][0]["meta"]
        return {
            "source":    "Yahoo Finance",
            "price":     meta.get("regularMarketPrice"),
            "ref":       meta.get("chartPreviousClose") or meta.get("previousClose"),
            "high":      meta.get("regularMarketDayHigh"),
            "low":       meta.get("regularMarketDayLow"),
            "open":      meta.get("regularMarketOpen"),
            "total_vol": meta.get("regularMarketVolume"),
            "ceiling":   None,
            "floor":     None,
            "change":    None,
            "pct_change":meta.get("regularMarketChangePercent"),
        }
    except Exception as e:
        print(f"  [Yahoo] parse lỗi: {e}")
    return {}

# ============================================================
# NGUỒN 2: VietStock (dùng endpoint public)
# ============================================================
def src_vietstock(symbol: str) -> dict:
    url = "https://finance.vietstock.vn/data/financeinfo"
    headers = {
        "Referer": "https://finance.vietstock.vn/",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
    }
    data = f"code={symbol}&s=0&t=D"
    try:
        r = requests.post(url, headers={**{"User-Agent":"Mozilla/5.0"}, **headers},
                          data=data, timeout=15)
        print(f"  [VietStock] status={r.status_code}")
        if r.status_code == 200:
            d = r.json()
            if d: d = d[0] if isinstance(d, list) else d
            return {
                "source":    "VietStock",
                "price":     d.get("ClosePrice") or d.get("Price"),
                "ref":       d.get("RefPrice") or d.get("BasicPrice"),
                "ceiling":   d.get("CeilingPrice") or d.get("Ceiling"),
                "floor":     d.get("FloorPrice") or d.get("Floor"),
                "high":      d.get("HighestPrice") or d.get("High"),
                "low":       d.get("LowestPrice") or d.get("Low"),
                "total_vol": d.get("TotalVolume") or d.get("Volume"),
                "total_val": d.get("TotalValue") or d.get("Value"),
                "change":    d.get("Change"),
                "pct_change":d.get("PerChange"),
                "foreign_buy_vol":  d.get("FBVol"),
                "foreign_sell_vol": d.get("FSVol"),
                "foreign_buy_val":  d.get("FBVal"),
                "foreign_sell_val": d.get("FSVal"),
            }
    except Exception as e:
        print(f"  [VietStock] lỗi: {e}")
    return {}

# ============================================================
# NGUỒN 3: DNSE (Entrade) - API công khai không cần auth
# ============================================================
def src_dnse(symbol: str) -> dict:
    url = f"https://api.entrade.com.vn/market/instruments/{symbol}/quotes"
    r = get(url, headers={"Referer": "https://banggia.dnse.com.vn/"})
    if not r or r.status_code != 200: return {}
    try:
        d = r.json()
        if isinstance(d, list) and d: d = d[0]
        return {
            "source":    "DNSE/Entrade",
            "price":     d.get("lastPrice") or d.get("close"),
            "ref":       d.get("refPrice") or d.get("referencePrice"),
            "ceiling":   d.get("ceilingPrice") or d.get("ceiling"),
            "floor":     d.get("floorPrice") or d.get("floor"),
            "high":      d.get("highPrice") or d.get("high"),
            "low":       d.get("lowPrice") or d.get("low"),
            "total_vol": d.get("totalMatchVolume") or d.get("volume"),
            "total_val": d.get("totalMatchValue"),
            "change":    d.get("change") or d.get("priceChange"),
            "pct_change":d.get("changePercent") or d.get("ratioChange"),
            "foreign_buy_vol":  d.get("foreignBuyVolume") or d.get("fbVol"),
            "foreign_sell_vol": d.get("foreignSellVolume") or d.get("fsVol"),
            "foreign_buy_val":  d.get("foreignBuyValue") or d.get("fbVal"),
            "foreign_sell_val": d.get("foreignSellValue") or d.get("fsVal"),
        }
    except Exception as e:
        print(f"  [DNSE] parse lỗi: {e}")
    return {}

# ============================================================
# NGUỒN 4: BSC (BIDV Securities) public API
# ============================================================
def src_bsc(symbol: str) -> dict:
    url = f"https://online.bsc.com.vn/api/public/quote?symbol={symbol}"
    r = get(url, headers={"Referer": "https://online.bsc.com.vn/"})
    if not r or r.status_code != 200: return {}
    try:
        d = r.json()
        if isinstance(d, dict) and d.get("data"): d = d["data"]
        if isinstance(d, list) and d: d = d[0]
        return {
            "source":    "BSC",
            "price":     d.get("lastPrice") or d.get("matchPrice"),
            "ref":       d.get("refPrice") or d.get("basicPrice"),
            "ceiling":   d.get("ceiling") or d.get("ceilingPrice"),
            "floor":     d.get("floor") or d.get("floorPrice"),
            "high":      d.get("high") or d.get("highPrice"),
            "low":       d.get("low") or d.get("lowPrice"),
            "total_vol": d.get("totalVolume") or d.get("totalMatchVol"),
            "total_val": d.get("totalValue") or d.get("totalMatchVal"),
            "change":    d.get("change"),
            "pct_change":d.get("changeRatio") or d.get("pctChange"),
        }
    except Exception as e:
        print(f"  [BSC] parse lỗi: {e}")
    return {}

# ============================================================
# NGUỒN 5: Wifeed - scrape JSON từ trang
# ============================================================
def src_wifeed(symbol: str) -> dict:
    url = f"https://wifeed.vn/api/thong-tin-co-phieu/{symbol}"
    r = get(url, headers={"Referer": "https://wifeed.vn/"})
    if not r or r.status_code != 200: return {}
    try:
        d = r.json()
        if d.get("data"): d = d["data"]
        return {
            "source":    "Wifeed",
            "price":     d.get("closePrice") or d.get("price"),
            "ref":       d.get("refPrice"),
            "ceiling":   d.get("ceiling"),
            "floor":     d.get("floor"),
            "high":      d.get("high"),
            "low":       d.get("low"),
            "total_vol": d.get("totalVolume") or d.get("volume"),
            "total_val": d.get("totalValue"),
            "change":    d.get("change"),
            "pct_change":d.get("changePercent"),
            "foreign_buy_vol":  d.get("foreignBuyVol"),
            "foreign_sell_vol": d.get("foreignSellVol"),
        }
    except Exception as e:
        print(f"  [Wifeed] parse lỗi: {e}")
    return {}

# ============================================================
# NGUỒN 6: SSI iBoard (dự phòng)
# ============================================================
def src_ssi(symbol: str) -> dict:
    url = f"https://iboard-query.ssi.com.vn/v2/stock/quote?symbol={symbol}"
    r = get(url, headers={"Referer":"https://iboard.ssi.com.vn/","Origin":"https://iboard.ssi.com.vn"})
    if not r or r.status_code != 200: return {}
    try:
        data = r.json()
        d = data.get("data") or {}
        if not d: return {}
        return {
            "source":    "SSI iBoard",
            "price":     d.get("lastPrice") or d.get("matchPrice"),
            "ref":       d.get("refPrice"),
            "ceiling":   d.get("ceilingPrice"),
            "floor":     d.get("floorPrice"),
            "high":      d.get("highPrice"),
            "low":       d.get("lowPrice"),
            "total_vol": d.get("totalMatchVol"),
            "total_val": d.get("totalMatchVal"),
            "change":    d.get("priceChange"),
            "pct_change":d.get("priceChangePercent"),
            "foreign_buy_vol":  d.get("foreignBuyVolTotal"),
            "foreign_sell_vol": d.get("foreignSellVolTotal"),
            "foreign_buy_val":  d.get("foreignBuyValTotal"),
            "foreign_sell_val": d.get("foreignSellValTotal"),
        }
    except Exception as e:
        print(f"  [SSI] parse lỗi: {e}")
    return {}

# ============================================================
# NGUỒN 7: TCBS
# ============================================================
def src_tcbs(symbol: str) -> dict:
    url = f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/quote?ticker={symbol}"
    r = get(url, headers={"Referer":"https://tcinvest.tcbs.com.vn/","Origin":"https://tcinvest.tcbs.com.vn"})
    if not r or r.status_code != 200: return {}
    try:
        data = r.json()
        d = data.get("data") or data
        if isinstance(d, list) and d: d = d[0]
        if not isinstance(d, dict): return {}
        return {
            "source":    "TCBS",
            "price":     d.get("lastPrice") or d.get("close"),
            "ref":       d.get("refPrice"),
            "ceiling":   d.get("ceilingPrice"),
            "floor":     d.get("floorPrice"),
            "high":      d.get("highPrice") or d.get("high"),
            "low":       d.get("lowPrice") or d.get("low"),
            "total_vol": d.get("totalMatchVol") or d.get("volume"),
            "total_val": d.get("totalMatchVal"),
            "change":    d.get("priceChange") or d.get("change"),
            "pct_change":d.get("priceChangeRatio") or d.get("changePercent"),
            "foreign_buy_vol":  d.get("foreignBuyVolTotal") or d.get("fBuyVol"),
            "foreign_sell_vol": d.get("foreignSellVolTotal") or d.get("fSellVol"),
        }
    except Exception as e:
        print(f"  [TCBS] parse lỗi: {e}")
    return {}

# ============================================================
# NGUỒN 8: Khớp lệnh từ TCBS intraday
# ============================================================
def get_matches(symbol: str) -> list:
    sources = [
        f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/intraday?ticker={symbol}&page=0&size=5",
        f"https://iboard-query.ssi.com.vn/v2/stock/match?symbol={symbol}",
    ]
    for url in sources:
        r = get(url)
        if not r or r.status_code != 200: continue
        try:
            data = r.json()
            items = data.get("data") or data.get("intraday") or []
            if isinstance(items, list) and items:
                return items[:5]
        except: pass
    return []

# ============================================================
# NGUỒN 9: Độ sâu từ DNSE
# ============================================================
def get_orderbook(symbol: str) -> dict:
    sources = [
        f"https://api.entrade.com.vn/market/instruments/{symbol}/depth",
        f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/orderbook?ticker={symbol}",
        f"https://iboard-query.ssi.com.vn/v2/stock/order-book?symbol={symbol}",
    ]
    for url in sources:
        r = get(url)
        if not r or r.status_code != 200: continue
        try:
            d = r.json()
            data = d.get("data") or d
            bids = data.get("bids") or data.get("bidList") or []
            asks = data.get("asks") or data.get("askList") or []
            if bids or asks:
                return {"bids": bids, "asks": asks, "raw": data}
            # format bidPrice1...
            if any(data.get(f"bidPrice{i}") for i in range(1,4)):
                return {"raw": data}
        except: pass
    return {}

# ============================================================
# LẤY DỮ LIỆU TỔNG QUAN (thử lần lượt tất cả nguồn)
# ============================================================
def get_overview(symbol: str) -> dict:
    sources = [
        ("DNSE",      src_dnse),
        ("VietStock", src_vietstock),
        ("BSC",       src_bsc),
        ("Wifeed",    src_wifeed),
        ("TCBS",      src_tcbs),
        ("SSI",       src_ssi),
        ("Yahoo",     src_yahoo),
    ]
    for name, fn in sources:
        print(f"  Thử nguồn: {name}...")
        try:
            result = fn(symbol)
            if result and result.get("price"):
                print(f"  ✅ Lấy được từ {name}")
                return result
        except Exception as e:
            print(f"  {name} exception: {e}")
    print("  ⚠️ Tất cả nguồn đều không trả dữ liệu")
    return {}

# ============================================================
# GỬI TELEGRAM
# ============================================================
def send_telegram(token: str, chat_id: str, text: str) -> bool:
    if not token:
        print("  ❌ TELEGRAM_BOT_TOKEN chưa set"); return False
    if not chat_id:
        print("  ❌ TELEGRAM_CHAT_ID chưa set"); return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text,
               "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=15)
        print(f"  [Telegram] status={r.status_code}")
        if r.status_code != 200:
            print(f"  [Telegram] body: {r.text[:400]}")
        return r.status_code == 200
    except Exception as e:
        print(f"  [Telegram] exception: {e}"); return False

# ============================================================
# BUILD TIN NHẮN
# ============================================================
def build_message(symbol: str) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    ov  = get_overview(symbol)
    ob  = get_orderbook(symbol)
    matches = get_matches(symbol)

    src    = ov.get("source", "?")
    price  = safe_float(ov.get("price"))
    ref    = safe_float(ov.get("ref"))
    change = safe_float(ov.get("change")) or (price - ref if price and ref else 0)
    pct    = safe_float(ov.get("pct_change"))
    if pct and abs(pct) < 1 and pct != 0: pct *= 100
    if not pct and ref and price: pct = (price - ref) / ref * 100
    arrow  = "🔺" if change >= 0 else "🔻"

    has_data = bool(ov.get("price"))

    lines = [
        f"📊 <b>{symbol}</b>  {arrow} <b>{fmt_price(ov.get('price'))}</b>"
        + (f"  ({change:+.2f} / {pct:+.2f}%)" if has_data else "  (N/A)"),
        f"🕐 {now}  |  📡 <i>{src}</i>",
    ]

    if has_data:
        lines += [
            "",
            "━━━━━━ GIÁ THAM CHIẾU ━━━━━━",
            f"TC: {fmt_price(ov.get('ref'))}  |  Trần: {fmt_price(ov.get('ceiling'))}  |  Sàn: {fmt_price(ov.get('floor'))}",
            f"Cao: {fmt_price(ov.get('high'))}  |  Thấp: {fmt_price(ov.get('low'))}",
            "",
            "━━━━━━ TỔNG KHỐI LƯỢNG ━━━━━━",
            f"Tổng KL: {fmt_num(ov.get('total_vol'))}",
            f"Tổng GT: {fmt_billion(ov.get('total_val'))}",
        ]

        # Khối ngoại
        fbuyvol  = ov.get("foreign_buy_vol")
        fsellvol = ov.get("foreign_sell_vol")
        fbuyval  = ov.get("foreign_buy_val")
        fsellval = ov.get("foreign_sell_val")
        if any(x is not None for x in [fbuyvol, fsellvol]):
            net_vol = safe_float(fbuyvol) - safe_float(fsellvol)
            net_val = safe_float(fbuyval) - safe_float(fsellval)
            nn = "🟢" if net_vol >= 0 else "🔴"
            lines += [
                "",
                "━━━━━━ GIAO DỊCH KHỐI NGOẠI ━━━━━━",
                f"NN Mua: {fmt_num(fbuyvol)} ({fmt_billion(fbuyval)})",
                f"NN Bán: {fmt_num(fsellvol)} ({fmt_billion(fsellval)})",
                f"{nn} Net KL: {fmt_num(net_vol)}  |  Net GT: {fmt_billion(net_val)}",
            ]

        # Độ sâu
        bids = ob.get("bids", [])
        asks = ob.get("asks", [])
        raw  = ob.get("raw", {})
        if bids or asks:
            lines += ["", "━━━━━━ ĐỘ SÂU ━━━━━━",
                      f"{'KL Mua':>10}  {'G.Mua':>7}  {'G.Bán':>7}  {'KL Bán':>10}"]
            for i in range(min(3, max(len(bids), len(asks)))):
                bp = (bids[i].get("p") or bids[i].get("price")) if i < len(bids) else None
                bv = (bids[i].get("v") or bids[i].get("volume")) if i < len(bids) else None
                ap = (asks[i].get("p") or asks[i].get("price")) if i < len(asks) else None
                av = (asks[i].get("v") or asks[i].get("volume")) if i < len(asks) else None
                lines.append(f"{fmt_num(bv):>10}  {fmt_price(bp):>7}  {fmt_price(ap):>7}  {fmt_num(av):>10}")
        elif raw and any(raw.get(f"bidPrice{i}") for i in range(1,4)):
            lines += ["", "━━━━━━ ĐỘ SÂU ━━━━━━",
                      f"{'KL Mua':>10}  {'G.Mua':>7}  {'G.Bán':>7}  {'KL Bán':>10}"]
            for i in range(1, 4):
                lines.append(
                    f"{fmt_num(raw.get(f'bidVolume{i}')):>10}  "
                    f"{fmt_price(raw.get(f'bidPrice{i}')):>7}  "
                    f"{fmt_price(raw.get(f'askPrice{i}')):>7}  "
                    f"{fmt_num(raw.get(f'askVolume{i}')):>10}"
                )

        # Khớp lệnh
        if matches:
            lines += ["", "━━━━━━ KHỚP LỆNH GẦN NHẤT ━━━━━━",
                      f"{'Giờ':>8}  {'Giá':>7}  {'+/-':>5}  {'KL':>8}"]
            for m in matches:
                t   = str(m.get("t") or m.get("time") or "")[-8:] or "--:--:--"
                p   = m.get("p") or m.get("price") or m.get("lastPrice")
                chg = safe_float(m.get("a") or m.get("change") or m.get("priceChange"))
                v   = m.get("v") or m.get("vol") or m.get("volume")
                sign = "+" if chg >= 0 else ""
                lines.append(f"{t:>8}  {fmt_price(p):>7}  {sign}{chg:>4}  {fmt_num(v):>8}")

        lines.append(f"\n🔗 <a href='https://finance.vietstock.vn/{symbol}/phan-tich-ky-thuat.htm'>VietStock</a>"
                     f"  |  <a href='https://banggia.dnse.com.vn/chung-khoan/{symbol}'>DNSE</a>")
    else:
        # Ngoài giờ - dùng Yahoo lấy giá đóng cửa hôm trước
        print("  Không có giá realtime, thử Yahoo cho giá đóng cửa...")
        yh = src_yahoo(symbol)
        if yh.get("price"):
            lines += [
                "",
                f"📉 Giá đóng cửa gần nhất: <b>{fmt_price(yh.get('price'))}</b>",
                f"Cao: {fmt_price(yh.get('high'))}  |  Thấp: {fmt_price(yh.get('low'))}",
                f"KL: {fmt_num(yh.get('total_vol'))}",
                f"Ref: {fmt_price(yh.get('ref'))}",
                "",
                "⏰ <i>Ngoài giờ giao dịch (9:00–15:15 T2-T6)</i>",
            ]
        else:
            lines.append("\n⚠️ Không lấy được dữ liệu từ bất kỳ nguồn nào.")

    return "\n".join(lines)

# ============================================================
# MAIN
# ============================================================
def run_once():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Lấy dữ liệu {SYMBOL}...")
    print(f"  TOKEN: {'✅' if TELEGRAM_BOT_TOKEN else '❌'}")
    print(f"  CHAT_ID: {'✅' if TELEGRAM_CHAT_ID else '❌'}")
    msg = build_message(SYMBOL)
    print("--- Tin nhắn ---\n" + msg + "\n---")
    ok = send_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, msg)
    print(f"→ Telegram: {'✅ OK' if ok else '❌ Lỗi'}")
    if not ok: sys.exit(1)

def run_loop():
    print(f"🤖 {SYMBOL} Bot | {INTERVAL_SECONDS}s")
    while True:
        try: run_once()
        except Exception as e: print(f"[loop] {e}")
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    run_once() if "--once" in sys.argv else run_loop()
