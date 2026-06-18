"""
GVR Stock Bot v4
- Trong giờ GD (9:00-15:15): lấy đầy đủ độ sâu, khớp lệnh, khối ngoại, mua/bán CĐ
- Ngoài giờ: lấy giá đóng cửa từ Yahoo
- 8 nguồn dữ liệu tự động fallback
"""

import requests, time, os, sys, json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
SYMBOL             = os.getenv("SYMBOL", "GVR")
INTERVAL_SECONDS   = int(os.getenv("INTERVAL_SECONDS", "300"))

ICT = timezone(timedelta(hours=7))

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
    try:
        b = float(v)
        # Nếu đơn vị là nghìn đồng → /1e6, nếu là đồng → /1e9
        if b > 1e11: b /= 1e9
        elif b > 1e8: b /= 1e6
        return f"{b:,.2f} tỷ"
    except: return "N/A"

def safe_float(v, d=0.0):
    try: return float(v)
    except: return d

def req(url, method="GET", headers=None, data=None, params=None, timeout=12):
    h = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    if headers: h.update(headers)
    try:
        if method == "POST":
            r = requests.post(url, headers=h, data=data, json=params, timeout=timeout)
        else:
            r = requests.get(url, headers=h, params=params, timeout=timeout)
        print(f"  {method} {url[:90]}  →  {r.status_code}")
        return r
    except Exception as e:
        print(f"  {method} {url[:90]}  →  ERR: {e}")
        return None

def is_trading_hours() -> bool:
    now = datetime.now(ICT)
    if now.weekday() >= 5: return False  # Thứ 7, CN
    t = now.hour * 60 + now.minute
    return (9*60 <= t <= 15*60+15)

# ============================================================
# NGUỒN QUOTE (giá + thông tin cơ bản)
# ============================================================

def src_dnse(symbol):
    """DNSE Entrade - thường không block IP nước ngoài"""
    r = req(f"https://api.entrade.com.vn/market/instruments/{symbol}/quotes",
            headers={"Referer": "https://banggia.dnse.com.vn/"})
    if not r or r.status_code != 200: return {}
    try:
        d = r.json()
        if isinstance(d, list): d = d[0] if d else {}
        if not d.get("lastPrice") and not d.get("close"): return {}
        return {
            "source": "DNSE",
            "price":  d.get("lastPrice") or d.get("close"),
            "ref":    d.get("refPrice") or d.get("referencePrice"),
            "ceiling":d.get("ceilingPrice") or d.get("ceiling"),
            "floor":  d.get("floorPrice") or d.get("floor"),
            "high":   d.get("highPrice") or d.get("high"),
            "low":    d.get("lowPrice") or d.get("low"),
            "total_vol": d.get("totalMatchVolume") or d.get("totalVolume") or d.get("volume"),
            "total_val": d.get("totalMatchValue") or d.get("totalValue"),
            "change":    d.get("change") or d.get("priceChange"),
            "pct_change":d.get("changePercent") or d.get("ratioChange"),
            "buy_vol":   d.get("activeBuyVolume") or d.get("buyVol"),
            "sell_vol":  d.get("activeSellVolume") or d.get("sellVol"),
            "foreign_buy_vol":  d.get("foreignBuyVolume") or d.get("fbVol"),
            "foreign_sell_vol": d.get("foreignSellVolume") or d.get("fsSVol"),
            "foreign_buy_val":  d.get("foreignBuyValue") or d.get("fbVal"),
            "foreign_sell_val": d.get("foreignSellValue") or d.get("fsVal"),
        }
    except Exception as e:
        print(f"  [DNSE parse] {e}"); return {}

def src_vps(symbol):
    """VPS Securities public API"""
    r = req(f"https://bgapidatafeed.vps.com.vn/getliststockdata/{symbol}",
            headers={"Referer": "https://banggia.vps.com.vn/"})
    if not r or r.status_code != 200: return {}
    try:
        d = r.json()
        if isinstance(d, list): d = d[0] if d else {}
        if not d: return {}
        price = d.get("lastPrice") or d.get("mp") or d.get("c")
        if not price: return {}
        return {
            "source": "VPS",
            "price":  price,
            "ref":    d.get("refPrice") or d.get("r"),
            "ceiling":d.get("ceilPrice") or d.get("ce"),
            "floor":  d.get("floorPrice") or d.get("fl"),
            "high":   d.get("highPrice") or d.get("h"),
            "low":    d.get("lowPrice") or d.get("lo"),
            "total_vol": d.get("totalVol") or d.get("tv"),
            "total_val": d.get("totalVal"),
            "change":    d.get("change") or d.get("ch"),
            "pct_change":d.get("percentChange") or d.get("changePc"),
            "buy_vol":   d.get("buyForeignQtty") and None or d.get("activeBuyVol"),
            "sell_vol":  d.get("activeSellVol"),
            "foreign_buy_vol":  d.get("buyForeignQtty") or d.get("fBuyVol"),
            "foreign_sell_vol": d.get("sellForeignQtty") or d.get("fSellVol"),
        }
    except Exception as e:
        print(f"  [VPS parse] {e}"); return {}

def src_ssi(symbol):
    """SSI iBoard"""
    r = req(f"https://iboard-query.ssi.com.vn/v2/stock/quote?symbol={symbol}",
            headers={"Referer":"https://iboard.ssi.com.vn/","Origin":"https://iboard.ssi.com.vn"})
    if not r or r.status_code != 200: return {}
    try:
        d = (r.json().get("data") or {})
        if not d.get("lastPrice") and not d.get("matchPrice"): return {}
        return {
            "source": "SSI",
            "price":  d.get("lastPrice") or d.get("matchPrice"),
            "ref":    d.get("refPrice"),
            "ceiling":d.get("ceilingPrice"),
            "floor":  d.get("floorPrice"),
            "high":   d.get("highPrice"),
            "low":    d.get("lowPrice"),
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
        print(f"  [SSI parse] {e}"); return {}

def src_tcbs(symbol):
    """TCBS"""
    r = req(f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/quote?ticker={symbol}",
            headers={"Referer":"https://tcinvest.tcbs.com.vn/","Origin":"https://tcinvest.tcbs.com.vn"})
    if not r or r.status_code != 200: return {}
    try:
        data = r.json()
        d = data.get("data") or data
        if isinstance(d, list): d = d[0] if d else {}
        if not isinstance(d, dict) or not (d.get("lastPrice") or d.get("close")): return {}
        return {
            "source": "TCBS",
            "price":  d.get("lastPrice") or d.get("close"),
            "ref":    d.get("refPrice"),
            "ceiling":d.get("ceilingPrice"),
            "floor":  d.get("floorPrice"),
            "high":   d.get("highPrice") or d.get("high"),
            "low":    d.get("lowPrice") or d.get("low"),
            "total_vol": d.get("totalMatchVol") or d.get("volume"),
            "total_val": d.get("totalMatchVal"),
            "change":    d.get("priceChange") or d.get("change"),
            "pct_change":d.get("priceChangeRatio") or d.get("changePercent"),
            "foreign_buy_vol":  d.get("foreignBuyVolTotal") or d.get("fBuyVol"),
            "foreign_sell_vol": d.get("foreignSellVolTotal") or d.get("fSellVol"),
            "foreign_buy_val":  d.get("foreignBuyValTotal"),
            "foreign_sell_val": d.get("foreignSellValTotal"),
        }
    except Exception as e:
        print(f"  [TCBS parse] {e}"); return {}

def src_vietstock(symbol):
    """VietStock"""
    r = req("https://finance.vietstock.vn/data/financeinfo",
            method="POST",
            headers={"Referer":"https://finance.vietstock.vn/","Content-Type":"application/x-www-form-urlencoded"},
            data=f"code={symbol}&s=0&t=D")
    if not r or r.status_code != 200: return {}
    try:
        d = r.json()
        if isinstance(d, list): d = d[0] if d else {}
        price = d.get("ClosePrice") or d.get("Price")
        if not price: return {}
        return {
            "source": "VietStock",
            "price":  price,
            "ref":    d.get("RefPrice") or d.get("BasicPrice"),
            "ceiling":d.get("CeilingPrice"),
            "floor":  d.get("FloorPrice"),
            "high":   d.get("HighestPrice"),
            "low":    d.get("LowestPrice"),
            "total_vol": d.get("TotalVolume"),
            "total_val": d.get("TotalValue"),
            "change":    d.get("Change"),
            "pct_change":d.get("PerChange"),
            "foreign_buy_vol":  d.get("FBVol"),
            "foreign_sell_vol": d.get("FSVol"),
            "foreign_buy_val":  d.get("FBVal"),
            "foreign_sell_val": d.get("FSVal"),
        }
    except Exception as e:
        print(f"  [VietStock parse] {e}"); return {}

def src_yahoo(symbol):
    """Yahoo Finance - luôn hoạt động, dùng cho ngoài giờ"""
    ticker = f"{symbol}.VN"
    r = req(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            params={"interval":"1d","range":"5d"})
    if not r or r.status_code != 200:
        r = req(f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}",
                params={"interval":"1d","range":"5d"})
    if not r or r.status_code != 200: return {}
    try:
        meta = r.json()["chart"]["result"][0]["meta"]
        ref  = meta.get("chartPreviousClose") or meta.get("previousClose")
        price= meta.get("regularMarketPrice")
        return {
            "source": "Yahoo Finance",
            "price":  price,
            "ref":    ref,
            "ceiling":None, "floor": None,
            "high":   meta.get("regularMarketDayHigh"),
            "low":    meta.get("regularMarketDayLow"),
            "total_vol": meta.get("regularMarketVolume"),
            "total_val": None,
            "change":    safe_float(price) - safe_float(ref) if price and ref else None,
            "pct_change":meta.get("regularMarketChangePercent"),
        }
    except Exception as e:
        print(f"  [Yahoo parse] {e}"); return {}

# ============================================================
# ĐỘ SÂU (order book)
# ============================================================
def get_orderbook(symbol):
    sources = [
        (f"https://api.entrade.com.vn/market/instruments/{symbol}/depth",
         {"Referer":"https://banggia.dnse.com.vn/"}, "dnse"),
        (f"https://bgapidatafeed.vps.com.vn/getorderbook/{symbol}",
         {"Referer":"https://banggia.vps.com.vn/"}, "vps"),
        (f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/orderbook?ticker={symbol}",
         {"Referer":"https://tcinvest.tcbs.com.vn/"}, "tcbs"),
        (f"https://iboard-query.ssi.com.vn/v2/stock/order-book?symbol={symbol}",
         {"Referer":"https://iboard.ssi.com.vn/"}, "ssi"),
    ]
    for url, hdrs, name in sources:
        r = req(url, headers=hdrs)
        if not r or r.status_code != 200: continue
        try:
            raw = r.json()
            d   = raw.get("data") or raw
            # Format mảng bids/asks
            bids = d.get("bids") or d.get("bidList") or d.get("bid") or []
            asks = d.get("asks") or d.get("askList") or d.get("ask") or []
            if bids or asks:
                print(f"  ✅ Order book từ {name}")
                return {"bids": bids, "asks": asks}
            # Format bidPrice1, bidVolume1...
            if d.get("bidPrice1") or d.get("bp1"):
                print(f"  ✅ Order book từ {name} (flat format)")
                rows = []
                for side in ["bid","ask"]:
                    lst = []
                    for i in range(1,4):
                        p = d.get(f"{side}Price{i}") or d.get(f"{side[0]}p{i}")
                        v = d.get(f"{side}Volume{i}") or d.get(f"{side[0]}v{i}")
                        if p: lst.append({"p":p,"v":v})
                    rows.append(lst)
                return {"bids": rows[0], "asks": rows[1]}
        except Exception as e:
            print(f"  [OB {name}] {e}")
    return {}

# ============================================================
# KHỚP LỆNH
# ============================================================
def get_matches(symbol, limit=5):
    sources = [
        (f"https://api.entrade.com.vn/market/instruments/{symbol}/transactions",
         {"Referer":"https://banggia.dnse.com.vn/"}, "dnse"),
        (f"https://bgapidatafeed.vps.com.vn/getmatchingorders/{symbol}/0",
         {"Referer":"https://banggia.vps.com.vn/"}, "vps"),
        (f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/intraday?ticker={symbol}&page=0&size={limit}",
         {"Referer":"https://tcinvest.tcbs.com.vn/"}, "tcbs"),
        (f"https://iboard-query.ssi.com.vn/v2/stock/match?symbol={symbol}",
         {"Referer":"https://iboard.ssi.com.vn/"}, "ssi"),
    ]
    for url, hdrs, name in sources:
        r = req(url, headers=hdrs)
        if not r or r.status_code != 200: continue
        try:
            d = r.json()
            items = d.get("data") or d.get("intraday") or d.get("items") or d
            if isinstance(items, list) and items:
                print(f"  ✅ Khớp lệnh từ {name}")
                return items[:limit]
        except Exception as e:
            print(f"  [Match {name}] {e}")
    return []

# ============================================================
# MUA/BÁN CHỦ ĐỘNG
# ============================================================
def get_busd(symbol):
    sources = [
        (f"https://api.entrade.com.vn/market/instruments/{symbol}/statistics",
         {"Referer":"https://banggia.dnse.com.vn/"}, "dnse"),
        (f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/trading-statistics?ticker={symbol}",
         {"Referer":"https://tcinvest.tcbs.com.vn/"}, "tcbs"),
        (f"https://iboard-query.ssi.com.vn/v2/stock/investor?symbol={symbol}",
         {"Referer":"https://iboard.ssi.com.vn/"}, "ssi"),
    ]
    for url, hdrs, name in sources:
        r = req(url, headers=hdrs)
        if not r or r.status_code != 200: continue
        try:
            d = r.json()
            d = d.get("data") or d
            buy  = (d.get("buyVol") or d.get("activeBuyVol") or
                    d.get("activeBuyVolume") or d.get("bu"))
            sell = (d.get("sellVol") or d.get("activeSellVol") or
                    d.get("activeSellVolume") or d.get("sd"))
            if buy or sell:
                print(f"  ✅ Mua/bán CĐ từ {name}")
                return {
                    "buy_vol":     buy,
                    "sell_vol":    sell,
                    "unknown_vol": d.get("unknownVol") or d.get("un"),
                }
        except Exception as e:
            print(f"  [BuSd {name}] {e}")
    return {}

# ============================================================
# TỔNG QUAN - thử từng nguồn
# ============================================================
def get_overview(symbol):
    fns = [src_dnse, src_vps, src_ssi, src_tcbs, src_vietstock]
    for fn in fns:
        try:
            ov = fn(symbol)
            if ov and ov.get("price"):
                return ov
        except Exception as e:
            print(f"  [{fn.__name__}] {e}")
    return {}

# ============================================================
# GỬI TELEGRAM
# ============================================================
def send_telegram(token, chat_id, text):
    if not token: print("  ❌ TOKEN chưa set"); return False
    if not chat_id: print("  ❌ CHAT_ID chưa set"); return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": chat_id, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": True
        }, timeout=15)
        print(f"  [Telegram] {r.status_code}")
        if r.status_code != 200: print(f"  [Telegram] {r.text[:300]}")
        return r.status_code == 200
    except Exception as e:
        print(f"  [Telegram] {e}"); return False

# ============================================================
# BUILD TIN NHẮN
# ============================================================
def build_message(symbol):
    now_ict = datetime.now(ICT)
    now_str = now_ict.strftime("%d/%m/%Y %H:%M:%S")
    in_trading = is_trading_hours()

    print(f"  Giờ ICT: {now_str} | Trong giờ GD: {in_trading}")

    ov = get_overview(symbol)

    # Nếu không có giá từ API VN → fallback Yahoo
    if not ov.get("price"):
        print("  Không có giá VN, fallback Yahoo...")
        ov = src_yahoo(symbol)

    if not ov.get("price"):
        return (f"⚠️ <b>{symbol}</b> — Không lấy được dữ liệu\n"
                f"🕐 {now_str}\nVui lòng thử lại sau.")

    src    = ov.get("source", "?")
    price  = safe_float(ov.get("price"))
    ref    = safe_float(ov.get("ref"))
    change = safe_float(ov.get("change")) or (price - ref if ref else 0)
    pct    = safe_float(ov.get("pct_change"))
    if pct and abs(pct) < 1 and pct != 0: pct *= 100
    if not pct and ref and price: pct = (price - ref) / ref * 100
    arrow  = "🔺" if change >= 0 else "🔻"

    lines = [
        f"📊 <b>{symbol}</b>  {arrow} <b>{fmt_price(price)}</b>  "
        f"({change:+.2f} / {pct:+.2f}%)",
        f"🕐 {now_str}  |  📡 <i>{src}</i>",
        "",
        "━━━━━━ GIÁ THAM CHIẾU ━━━━━━",
        f"TC: {fmt_price(ov.get('ref'))}  |  "
        f"Trần: {fmt_price(ov.get('ceiling'))}  |  "
        f"Sàn: {fmt_price(ov.get('floor'))}",
        f"Cao: {fmt_price(ov.get('high'))}  |  Thấp: {fmt_price(ov.get('low'))}",
        "",
        "━━━━━━ TỔNG KHỐI LƯỢNG ━━━━━━",
        f"Tổng KL: {fmt_num(ov.get('total_vol'))}",
        f"Tổng GT: {fmt_billion(ov.get('total_val'))}",
    ]

    if in_trading:
        # --- Mua/bán chủ động ---
        # Thử lấy từ overview trước, nếu không có thì gọi riêng
        buy_vol  = ov.get("buy_vol")
        sell_vol = ov.get("sell_vol")
        busd = {}
        if not buy_vol:
            busd = get_busd(symbol)
            buy_vol  = busd.get("buy_vol")
            sell_vol = busd.get("sell_vol")

        if buy_vol or sell_vol:
            unk = ov.get("unknown_vol") or busd.get("unknown_vol")
            lines += [
                "",
                "━━━━━━ MUA/BÁN CHỦ ĐỘNG ━━━━━━",
                f"🟢 Mua CĐ : {fmt_num(buy_vol)}",
                f"🔴 Bán CĐ : {fmt_num(sell_vol)}",
                f"⚪ Không XĐ: {fmt_num(unk)}",
            ]

        # --- Khối ngoại ---
        fbuyvol  = ov.get("foreign_buy_vol")
        fsellvol = ov.get("foreign_sell_vol")
        fbuyval  = ov.get("foreign_buy_val")
        fsellval = ov.get("foreign_sell_val")
        if fbuyvol is not None or fsellvol is not None:
            net_vol = safe_float(fbuyvol) - safe_float(fsellvol)
            net_val = safe_float(fbuyval) - safe_float(fsellval)
            nn = "🟢" if net_vol >= 0 else "🔴"
            lines += [
                "",
                "━━━━━━ GIAO DỊCH KHỐI NGOẠI ━━━━━━",
                f"NN Mua KL: {fmt_num(fbuyvol)}",
                f"NN Bán KL: {fmt_num(fsellvol)}",
                f"NN Mua GT: {fmt_billion(fbuyval)}",
                f"NN Bán GT: {fmt_billion(fsellval)}",
                f"{nn} Net KL: {fmt_num(net_vol)}  |  Net GT: {fmt_billion(net_val)}",
            ]

        # --- Độ sâu ---
        ob = get_orderbook(symbol)
        bids = ob.get("bids", [])
        asks = ob.get("asks", [])
        if bids or asks:
            lines += [
                "",
                "━━━━━━ ĐỘ SÂU (3 CẤP) ━━━━━━",
                f"{'KL Mua':>10}  {'G.Mua':>8}  {'G.Bán':>8}  {'KL Bán':>10}",
            ]
            for i in range(min(3, max(len(bids), len(asks)))):
                def gv(lst, idx, key_list):
                    if idx >= len(lst): return None
                    item = lst[idx]
                    for k in key_list:
                        if item.get(k) is not None: return item[k]
                    return None
                bp = gv(bids, i, ["p","price","bidPrice"])
                bv = gv(bids, i, ["v","volume","bidVolume","qty"])
                ap = gv(asks, i, ["p","price","askPrice"])
                av = gv(asks, i, ["v","volume","askVolume","qty"])
                lines.append(
                    f"{fmt_num(bv):>10}  {fmt_price(bp):>8}  "
                    f"{fmt_price(ap):>8}  {fmt_num(av):>10}"
                )

        # --- Khớp lệnh ---
        matches = get_matches(symbol)
        if matches:
            lines += [
                "",
                "━━━━━━ KHỚP LỆNH GẦN NHẤT ━━━━━━",
                f"{'Giờ':>8}  {'Giá':>8}  {'+/-':>5}  {'KL':>8}",
            ]
            for m in matches:
                t   = str(m.get("t") or m.get("time") or m.get("matchTime") or "")
                t   = t[-8:] if len(t) >= 8 else (t or "--:--:--")
                p   = (m.get("p") or m.get("price") or
                       m.get("lastPrice") or m.get("matchPrice"))
                chg = safe_float(m.get("a") or m.get("change") or
                                 m.get("priceChange") or 0)
                v   = (m.get("v") or m.get("vol") or
                       m.get("volume") or m.get("matchVolume"))
                sign = "+" if chg >= 0 else ""
                lines.append(
                    f"{t:>8}  {fmt_price(p):>8}  {sign}{chg:>4}  {fmt_num(v):>8}"
                )

        lines.append(
            f"\n🔗 <a href='https://banggia.dnse.com.vn/chung-khoan/{symbol}'>DNSE</a>"
            f"  |  <a href='https://iboard.ssi.com.vn/#!/{symbol}'>SSI</a>"
            f"  |  <a href='https://tcinvest.tcbs.com.vn/{symbol}'>TCBS</a>"
        )
    else:
        lines += [
            "",
            "⏰ <i>Ngoài giờ giao dịch — hiển thị giá đóng cửa gần nhất</i>",
            "<i>Bot sẽ gửi đầy đủ thông tin trong giờ 9:00–15:15 T2–T6</i>",
        ]

    return "\n".join(lines)

# ============================================================
# MAIN
# ============================================================
def run_once():
    print(f"\n[{datetime.now(ICT).strftime('%H:%M:%S')}] {SYMBOL}")
    print(f"  TOKEN:   {'✅' if TELEGRAM_BOT_TOKEN else '❌ CHƯA SET'}")
    print(f"  CHAT_ID: {'✅' if TELEGRAM_CHAT_ID else '❌ CHƯA SET'}")
    msg = build_message(SYMBOL)
    print("---\n" + msg + "\n---")
    ok = send_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, msg)
    print(f"→ {'✅ OK' if ok else '❌ Lỗi'}")
    if not ok: sys.exit(1)

def run_loop():
    print(f"🤖 Bot {SYMBOL} | {INTERVAL_SECONDS}s")
    while True:
        try: run_once()
        except Exception as e: print(f"[loop] {e}")
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    run_once() if "--once" in sys.argv else run_loop()
