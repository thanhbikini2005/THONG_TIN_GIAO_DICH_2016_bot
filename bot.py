"""
GVR Stock Bot v5
- Debug toàn bộ API để biết cái nào hoạt động từ GitHub Actions
- Kết luận sau mỗi phần: khối ngoại, độ sâu, khớp lệnh
- 2 chế độ: trong giờ (đầy đủ) / ngoài giờ (giá đóng cửa)
"""

import requests, time, os, sys
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
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/json, */*",
    }
    if headers: h.update(headers)
    try:
        if method == "POST":
            r = requests.post(url, headers=h, data=data, timeout=timeout)
        else:
            r = requests.get(url, headers=h, params=params, timeout=timeout)
        return r
    except Exception as e:
        print(f"    ERR {url[:70]}: {e}")
        return None

def is_trading():
    now = datetime.now(ICT)
    if now.weekday() >= 5: return False
    t = now.hour * 60 + now.minute
    return 9*60 <= t <= 15*60+15

# ============================================================
# DEBUG: Gọi tất cả API và báo cái nào sống
# ============================================================
def debug_all_apis(symbol):
    """Gọi toàn bộ API, in status, trả về dict kết quả"""
    results = {}
    apis = [
        # (tên, url, headers, method)
        ("DNSE_quote",    f"https://api.entrade.com.vn/market/instruments/{symbol}/quotes",
         {"Referer":"https://banggia.dnse.com.vn/"}, "GET"),
        ("DNSE_depth",    f"https://api.entrade.com.vn/market/instruments/{symbol}/depth",
         {"Referer":"https://banggia.dnse.com.vn/"}, "GET"),
        ("DNSE_trades",   f"https://api.entrade.com.vn/market/instruments/{symbol}/transactions",
         {"Referer":"https://banggia.dnse.com.vn/"}, "GET"),
        ("VPS_quote",     f"https://bgapidatafeed.vps.com.vn/getliststockdata/{symbol}",
         {"Referer":"https://banggia.vps.com.vn/"}, "GET"),
        ("VPS_orderbook", f"https://bgapidatafeed.vps.com.vn/getorderbook/{symbol}",
         {"Referer":"https://banggia.vps.com.vn/"}, "GET"),
        ("VPS_match",     f"https://bgapidatafeed.vps.com.vn/getmatchingorders/{symbol}/0",
         {"Referer":"https://banggia.vps.com.vn/"}, "GET"),
        ("SSI_quote",     f"https://iboard-query.ssi.com.vn/v2/stock/quote?symbol={symbol}",
         {"Referer":"https://iboard.ssi.com.vn/","Origin":"https://iboard.ssi.com.vn"}, "GET"),
        ("SSI_match",     f"https://iboard-query.ssi.com.vn/v2/stock/match?symbol={symbol}",
         {"Referer":"https://iboard.ssi.com.vn/"}, "GET"),
        ("SSI_ob",        f"https://iboard-query.ssi.com.vn/v2/stock/order-book?symbol={symbol}",
         {"Referer":"https://iboard.ssi.com.vn/"}, "GET"),
        ("SSI_investor",  f"https://iboard-query.ssi.com.vn/v2/stock/investor?symbol={symbol}",
         {"Referer":"https://iboard.ssi.com.vn/"}, "GET"),
        ("TCBS_quote",    f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/quote?ticker={symbol}",
         {"Referer":"https://tcinvest.tcbs.com.vn/","Origin":"https://tcinvest.tcbs.com.vn"}, "GET"),
        ("TCBS_intraday", f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/intraday?ticker={symbol}&page=0&size=5",
         {"Referer":"https://tcinvest.tcbs.com.vn/"}, "GET"),
        ("TCBS_ob",       f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/orderbook?ticker={symbol}",
         {"Referer":"https://tcinvest.tcbs.com.vn/"}, "GET"),
        ("FANT_quote",    f"https://restv2.fireant.vn/symbols/{symbol}/quote",
         {"Referer":"https://fireant.vn/"}, "GET"),
        ("Yahoo",         f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.VN",
         {}, "GET"),
    ]
    print("\n=== DEBUG: Kiểm tra tất cả API ===")
    for name, url, hdrs, method in apis:
        r = req(url, method=method, headers=hdrs)
        status = r.status_code if r else "FAIL"
        body_preview = ""
        if r and r.status_code == 200:
            try:
                body_preview = str(r.json())[:120]
            except:
                body_preview = r.text[:80]
        print(f"  {name:20s} → {status}  {body_preview}")
        results[name] = (r, status)
    print("=== END DEBUG ===\n")
    return results

# ============================================================
# PARSE dữ liệu từ kết quả debug
# ============================================================
def parse_quote(api_results, symbol):
    """Lấy giá từ API nào sống"""
    # DNSE
    r, s = api_results.get("DNSE_quote", (None, 0))
    if s == 200:
        try:
            d = r.json()
            if isinstance(d, list): d = d[0] if d else {}
            price = d.get("lastPrice") or d.get("close") or d.get("mp")
            if price:
                return {
                    "source":"DNSE", "price":price,
                    "ref":   d.get("refPrice") or d.get("referencePrice"),
                    "ceiling":d.get("ceilingPrice") or d.get("ceiling"),
                    "floor": d.get("floorPrice") or d.get("floor"),
                    "high":  d.get("highPrice") or d.get("high"),
                    "low":   d.get("lowPrice") or d.get("low"),
                    "total_vol": d.get("totalMatchVolume") or d.get("totalVolume") or d.get("volume"),
                    "total_val": d.get("totalMatchValue") or d.get("totalValue"),
                    "change":    d.get("change") or d.get("priceChange"),
                    "pct_change":d.get("changePercent") or d.get("ratioChange"),
                    "buy_vol":   d.get("activeBuyVolume") or d.get("buyVol"),
                    "sell_vol":  d.get("activeSellVolume") or d.get("sellVol"),
                    "unknown_vol": d.get("unknownVolume"),
                    "foreign_buy_vol":  d.get("foreignBuyVolume") or d.get("fbVol"),
                    "foreign_sell_vol": d.get("foreignSellVolume") or d.get("fsSVol") or d.get("fsVol"),
                    "foreign_buy_val":  d.get("foreignBuyValue") or d.get("fbVal"),
                    "foreign_sell_val": d.get("foreignSellValue") or d.get("fsVal"),
                }
        except: pass

    # VPS
    r, s = api_results.get("VPS_quote", (None, 0))
    if s == 200:
        try:
            d = r.json()
            if isinstance(d, list): d = d[0] if d else {}
            price = d.get("lastPrice") or d.get("mp") or d.get("c")
            if price:
                return {
                    "source":"VPS", "price":price,
                    "ref":    d.get("r") or d.get("refPrice"),
                    "ceiling":d.get("ce") or d.get("ceilPrice"),
                    "floor":  d.get("fl") or d.get("floorPrice"),
                    "high":   d.get("h") or d.get("highPrice"),
                    "low":    d.get("lo") or d.get("lowPrice"),
                    "total_vol": d.get("tv") or d.get("totalVol"),
                    "total_val": d.get("totalVal"),
                    "change":    d.get("ch") or d.get("change"),
                    "pct_change":d.get("changePc") or d.get("percentChange"),
                    "foreign_buy_vol":  d.get("fBuyVol") or d.get("buyForeignQtty"),
                    "foreign_sell_vol": d.get("fSellVol") or d.get("sellForeignQtty"),
                    "buy_vol":  d.get("activeBuyVol"),
                    "sell_vol": d.get("activeSellVol"),
                }
        except: pass

    # SSI
    r, s = api_results.get("SSI_quote", (None, 0))
    if s == 200:
        try:
            d = r.json().get("data") or {}
            price = d.get("lastPrice") or d.get("matchPrice")
            if price:
                return {
                    "source":"SSI", "price":price,
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
        except: pass

    # TCBS
    r, s = api_results.get("TCBS_quote", (None, 0))
    if s == 200:
        try:
            data = r.json()
            d = data.get("data") or data
            if isinstance(d, list): d = d[0] if d else {}
            price = d.get("lastPrice") or d.get("close")
            if price:
                return {
                    "source":"TCBS", "price":price,
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
                }
        except: pass

    # Fireant
    r, s = api_results.get("FANT_quote", (None, 0))
    if s == 200:
        try:
            d = r.json()
            price = d.get("lastPrice") or d.get("price")
            if price:
                return {
                    "source":"Fireant", "price":price,
                    "ref":    d.get("referencePrice"),
                    "ceiling":d.get("ceilingPrice"),
                    "floor":  d.get("floorPrice"),
                    "high":   d.get("highPrice"),
                    "low":    d.get("lowPrice"),
                    "total_vol": d.get("totalVolume"),
                    "total_val": d.get("totalValue"),
                    "change":    d.get("change"),
                    "pct_change":d.get("percentChange"),
                    "foreign_buy_vol":  d.get("foreignBuyVolume"),
                    "foreign_sell_vol": d.get("foreignSellVolume"),
                    "foreign_buy_val":  d.get("foreignBuyValue"),
                    "foreign_sell_val": d.get("foreignSellValue"),
                }
        except: pass

    # Yahoo (fallback cuối)
    r, s = api_results.get("Yahoo", (None, 0))
    if s == 200:
        try:
            meta  = r.json()["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            ref   = meta.get("chartPreviousClose") or meta.get("previousClose")
            if price:
                return {
                    "source":"Yahoo Finance", "price":price,
                    "ref": ref, "ceiling":None, "floor":None,
                    "high":  meta.get("regularMarketDayHigh"),
                    "low":   meta.get("regularMarketDayLow"),
                    "total_vol": meta.get("regularMarketVolume"),
                    "total_val": None,
                    "change":    safe_float(price) - safe_float(ref) if price and ref else None,
                    "pct_change":meta.get("regularMarketChangePercent"),
                }
        except: pass

    return {}

def parse_orderbook(api_results):
    for name in ["DNSE_depth","VPS_orderbook","SSI_ob","TCBS_ob"]:
        r, s = api_results.get(name, (None, 0))
        if s != 200: continue
        try:
            raw = r.json()
            d = raw.get("data") or raw
            bids = d.get("bids") or d.get("bidList") or d.get("bid") or []
            asks = d.get("asks") or d.get("askList") or d.get("ask") or []
            if bids or asks:
                print(f"  ✅ Độ sâu từ {name}")
                return bids, asks
            # flat format
            if d.get("bidPrice1") or d.get("bp1"):
                bids, asks = [], []
                for i in range(1,4):
                    p = d.get(f"bidPrice{i}") or d.get(f"bp{i}")
                    v = d.get(f"bidVolume{i}") or d.get(f"bv{i}")
                    if p: bids.append({"p":p,"v":v})
                    p = d.get(f"askPrice{i}") or d.get(f"ap{i}")
                    v = d.get(f"askVolume{i}") or d.get(f"av{i}")
                    if p: asks.append({"p":p,"v":v})
                if bids or asks:
                    print(f"  ✅ Độ sâu (flat) từ {name}")
                    return bids, asks
        except: pass
    return [], []

def parse_matches(api_results, limit=5):
    for name in ["DNSE_trades","VPS_match","TCBS_intraday","SSI_match"]:
        r, s = api_results.get(name, (None, 0))
        if s != 200: continue
        try:
            d = r.json()
            items = (d.get("data") or d.get("intraday") or
                     d.get("items") or d.get("list") or d)
            if isinstance(items, list) and items:
                print(f"  ✅ Khớp lệnh từ {name}")
                return items[:limit]
        except: pass
    return []

def parse_busd(api_results, ov):
    # Thử lấy từ overview trước
    buy  = ov.get("buy_vol")
    sell = ov.get("sell_vol")
    if buy or sell:
        return {"buy_vol":buy, "sell_vol":sell, "unknown_vol":ov.get("unknown_vol")}

    r, s = api_results.get("SSI_investor", (None, 0))
    if s == 200:
        try:
            d = r.json().get("data") or {}
            buy  = d.get("buyVol") or d.get("bu")
            sell = d.get("sellVol") or d.get("sd")
            if buy or sell:
                return {"buy_vol":buy,"sell_vol":sell,"unknown_vol":d.get("unknownVol")}
        except: pass
    return {}

# ============================================================
# KẾT LUẬN
# ============================================================
def conclude_foreign(buy_vol, sell_vol, buy_val, sell_val):
    buy_v  = safe_float(buy_vol)
    sell_v = safe_float(sell_vol)
    net    = buy_v - sell_v
    if net > 500000:
        return "🟢 <b>Khối ngoại MUA MẠNH</b> — tín hiệu tích cực, dòng tiền ngoại đang vào"
    elif net > 100000:
        return "🟢 <b>Khối ngoại mua ròng</b> — ngoại tổ đang tích lũy nhẹ"
    elif net > 0:
        return "🟡 <b>Khối ngoại mua ròng nhẹ</b> — chưa rõ xu hướng"
    elif net > -100000:
        return "🟡 <b>Khối ngoại bán ròng nhẹ</b> — cần theo dõi thêm"
    elif net > -500000:
        return "🔴 <b>Khối ngoại bán ròng</b> — ngoại đang rút dần"
    else:
        return "🔴 <b>Khối ngoại BÁN MẠNH</b> — áp lực bán từ ngoại lớn"

def conclude_orderbook(bids, asks):
    total_bid = sum(safe_float(b.get("v") or b.get("volume") or b.get("qty")) for b in bids)
    total_ask = sum(safe_float(a.get("v") or a.get("volume") or a.get("qty")) for a in asks)
    if total_bid == 0 and total_ask == 0: return ""
    ratio = total_bid / total_ask if total_ask else 999
    if ratio >= 3:
        return f"🟢 <b>Cầu áp đảo cung</b> ({fmt_num(total_bid)} vs {fmt_num(total_ask)}) — lực mua rất mạnh"
    elif ratio >= 1.5:
        return f"🟢 <b>Cầu lớn hơn cung</b> ({fmt_num(total_bid)} vs {fmt_num(total_ask)}) — thiên về mua"
    elif ratio >= 0.7:
        return f"🟡 <b>Cung cầu cân bằng</b> ({fmt_num(total_bid)} vs {fmt_num(total_ask)}) — giằng co"
    elif ratio >= 0.35:
        return f"🔴 <b>Cung lớn hơn cầu</b> ({fmt_num(total_bid)} vs {fmt_num(total_ask)}) — thiên về bán"
    else:
        return f"🔴 <b>Cung áp đảo cầu</b> ({fmt_num(total_bid)} vs {fmt_num(total_ask)}) — áp lực bán lớn"

def conclude_matches(matches, ref):
    if not matches: return ""
    prices = []
    for m in matches:
        p = m.get("p") or m.get("price") or m.get("lastPrice") or m.get("matchPrice")
        if p: prices.append(safe_float(p))
    if not prices: return ""
    avg = sum(prices) / len(prices)
    last = prices[0]
    trend = "tăng" if last > avg else ("giảm" if last < avg else "đi ngang")
    if trend == "tăng":
        return f"🟢 <b>Giá đang tăng</b> — {len(prices)} lệnh gần nhất xu hướng đi lên"
    elif trend == "giảm":
        return f"🔴 <b>Giá đang giảm</b> — {len(prices)} lệnh gần nhất xu hướng đi xuống"
    return f"🟡 <b>Giá đang giằng co</b> quanh {fmt_price(avg)}"

def conclude_busd(buy_vol, sell_vol):
    b = safe_float(buy_vol); s = safe_float(sell_vol)
    if b == 0 and s == 0: return ""
    total = b + s
    pct_buy = b / total * 100 if total else 0
    if pct_buy >= 65:
        return f"🟢 <b>Lực mua chủ động áp đảo</b> ({pct_buy:.0f}% mua) — tín hiệu tăng"
    elif pct_buy >= 55:
        return f"🟢 <b>Mua chủ động nhỉnh hơn</b> ({pct_buy:.0f}% mua) — nghiêng về tăng"
    elif pct_buy >= 45:
        return f"🟡 <b>Mua/Bán chủ động cân bằng</b> ({pct_buy:.0f}% mua) — thị trường giằng co"
    elif pct_buy >= 35:
        return f"🔴 <b>Bán chủ động nhỉnh hơn</b> ({pct_buy:.0f}% mua) — nghiêng về giảm"
    else:
        return f"🔴 <b>Lực bán chủ động áp đảo</b> ({pct_buy:.0f}% mua) — tín hiệu giảm"

# ============================================================
# GỬI TELEGRAM
# ============================================================
def send_telegram(token, chat_id, text):
    if not token: print("  ❌ TOKEN chưa set"); return False
    if not chat_id: print("  ❌ CHAT_ID chưa set"); return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id":chat_id,"text":text,
                  "parse_mode":"HTML","disable_web_page_preview":True},
            timeout=15
        )
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
    in_trading = is_trading()
    print(f"  Giờ ICT: {now_str} | Trong giờ GD: {in_trading}")

    # Gọi tất cả API 1 lần, dùng chung
    api_results = debug_all_apis(symbol)

    ov = parse_quote(api_results, symbol)
    if not ov.get("price"):
        return (f"⚠️ <b>{symbol}</b> — Không lấy được dữ liệu\n"
                f"🕐 {now_str}\n\nCác API đều không phản hồi từ GitHub Actions.\n"
                f"Vui lòng kiểm tra log để biết nguồn nào hoạt động.")

    src    = ov.get("source","?")
    price  = safe_float(ov.get("price"))
    ref    = safe_float(ov.get("ref"))
    change = safe_float(ov.get("change")) or (price - ref if ref else 0)
    pct    = safe_float(ov.get("pct_change"))
    if pct and abs(pct) < 1 and pct != 0: pct *= 100
    if not pct and ref and price: pct = (price - ref)/ref*100
    arrow  = "🔺" if change >= 0 else "🔻"

    lines = [
        f"📊 <b>{symbol}</b>  {arrow} <b>{fmt_price(price)}</b>  "
        f"({change:+.2f} / {pct:+.2f}%)",
        f"🕐 {now_str}  |  📡 <i>{src}</i>",
        "",
        "━━━━━━ GIÁ THAM CHIẾU ━━━━━━",
        f"TC: {fmt_price(ov.get('ref'))}  |  Trần: {fmt_price(ov.get('ceiling'))}  |  Sàn: {fmt_price(ov.get('floor'))}",
        f"Cao: {fmt_price(ov.get('high'))}  |  Thấp: {fmt_price(ov.get('low'))}",
        "",
        "━━━━━━ TỔNG KHỐI LƯỢNG ━━━━━━",
        f"Tổng KL: {fmt_num(ov.get('total_vol'))}",
        f"Tổng GT: {fmt_billion(ov.get('total_val'))}",
    ]

    if in_trading:
        # --- MUA/BÁN CHỦ ĐỘNG ---
        busd = parse_busd(api_results, ov)
        if busd.get("buy_vol") or busd.get("sell_vol"):
            buy_vol = busd.get("buy_vol"); sell_vol = busd.get("sell_vol")
            lines += [
                "",
                "━━━━━━ MUA/BÁN CHỦ ĐỘNG ━━━━━━",
                f"🟢 Mua CĐ  : {fmt_num(buy_vol)}",
                f"🔴 Bán CĐ  : {fmt_num(sell_vol)}",
                f"⚪ Không XĐ: {fmt_num(busd.get('unknown_vol'))}",
                f"📝 {conclude_busd(buy_vol, sell_vol)}",
            ]

        # --- KHỐI NGOẠI ---
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
                f"NN Mua KL: {fmt_num(fbuyvol)}   |  NN Mua GT: {fmt_billion(fbuyval)}",
                f"NN Bán KL: {fmt_num(fsellvol)}   |  NN Bán GT: {fmt_billion(fsellval)}",
                f"{nn} Net KL: {fmt_num(net_vol)}  |  Net GT: {fmt_billion(net_val)}",
                f"📝 {conclude_foreign(fbuyvol, fsellvol, fbuyval, fsellval)}",
            ]

        # --- ĐỘ SÂU ---
        bids, asks = parse_orderbook(api_results)
        if bids or asks:
            lines += [
                "",
                "━━━━━━ ĐỘ SÂU (3 CẤP) ━━━━━━",
                f"{'KL Mua':>10}  {'G.Mua':>8}  {'G.Bán':>8}  {'KL Bán':>10}",
            ]
            def gv(lst, i, keys):
                if i >= len(lst): return None
                for k in keys:
                    if lst[i].get(k) is not None: return lst[i][k]
                return None
            for i in range(min(3, max(len(bids), len(asks)))):
                bp = gv(bids, i, ["p","price","bidPrice"])
                bv = gv(bids, i, ["v","volume","bidVolume","qty"])
                ap = gv(asks, i, ["p","price","askPrice"])
                av = gv(asks, i, ["v","volume","askVolume","qty"])
                lines.append(f"{fmt_num(bv):>10}  {fmt_price(bp):>8}  {fmt_price(ap):>8}  {fmt_num(av):>10}")
            ob_conclude = conclude_orderbook(bids, asks)
            if ob_conclude:
                lines.append(f"📝 {ob_conclude}")

        # --- KHỚP LỆNH ---
        matches = parse_matches(api_results)
        if matches:
            lines += [
                "",
                "━━━━━━ KHỚP LỆNH GẦN NHẤT ━━━━━━",
                f"{'Giờ':>8}  {'Giá':>8}  {'+/-':>5}  {'KL':>8}",
            ]
            for m in matches:
                t   = str(m.get("t") or m.get("time") or m.get("matchTime") or "")
                t   = t[-8:] if len(t) >= 8 else (t or "--:--:--")
                p   = m.get("p") or m.get("price") or m.get("lastPrice") or m.get("matchPrice")
                chg = safe_float(m.get("a") or m.get("change") or m.get("priceChange") or 0)
                v   = m.get("v") or m.get("vol") or m.get("volume") or m.get("matchVolume")
                sign = "+" if chg >= 0 else ""
                lines.append(f"{t:>8}  {fmt_price(p):>8}  {sign}{chg:>4}  {fmt_num(v):>8}")
            mc = conclude_matches(matches, ref)
            if mc: lines.append(f"📝 {mc}")

        lines.append(
            f"\n🔗 <a href='https://banggia.dnse.com.vn/chung-khoan/{symbol}'>DNSE</a>"
            f"  |  <a href='https://iboard.ssi.com.vn/#!/{symbol}'>SSI</a>"
            f"  |  <a href='https://tcinvest.tcbs.com.vn/{symbol}'>TCBS</a>"
        )
    else:
        lines += [
            "",
            "⏰ <i>Ngoài giờ GD — giá đóng cửa gần nhất</i>",
            "<i>Thông tin đầy đủ (độ sâu, khớp lệnh, khối ngoại) trong giờ 9:00–15:15 T2–T6</i>",
        ]

    return "\n".join(lines)

# ============================================================
# MAIN
# ============================================================
def run_once():
    print(f"\n[{datetime.now(ICT).strftime('%H:%M:%S')}] {SYMBOL}")
    print(f"  TOKEN:   {'✅' if TELEGRAM_BOT_TOKEN else '❌'}")
    print(f"  CHAT_ID: {'✅' if TELEGRAM_CHAT_ID else '❌'}")
    msg = build_message(SYMBOL)
    print("--- Tin nhắn ---\n" + msg + "\n---")
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
