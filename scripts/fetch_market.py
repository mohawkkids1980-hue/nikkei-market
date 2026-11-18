#!/usr/bin/env python3
"""日経モーニング10 用：米国市場センチメント指標の取得スクリプト

VIX / CNN Fear & Greed Index / Cboe Put/Call Ratio を公開データから取得し、
data/market.json（最新値）と data/history.csv（全日分の蓄積）に書き出す。
標準ライブラリのみ使用。各指標は独立して取得し、失敗した指標は出力から省く
（タスク側が Web 検索で補う）。
"""
import csv
import datetime as dt
import json
import os
import sys
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json,text/csv,*/*",
        "Referer": "https://www.cnn.com/",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def log(msg):
    print(msg, file=sys.stderr)


# ---------- VIX ----------
def fetch_vix():
    # 1) Cboe 公式（遅延）ヒストリカル
    try:
        url = "https://cdn.cboe.com/api/global/delayed_quotes/charts/historical/_VIX.json"
        rows = json.loads(get(url))["data"]
        rows = [r for r in rows if r.get("close") not in (None, "")]
        last, prev = rows[-1], rows[-2]
        v, p = float(last["close"]), float(prev["close"])
        return {"value": round(v, 2), "changePct": round((v / p - 1) * 100, 2),
                "date": str(last["date"])[:10], "source": "Cboe",
                "url": "https://www.cboe.com/tradable_products/vix/"}
    except Exception as e:
        log(f"VIX (Cboe) failed: {e}")
    # 2) FRED（セントルイス連銀）VIXCLS
    try:
        text = get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS")
        rows = [r for r in csv.reader(text.splitlines())][1:]
        rows = [r for r in rows if len(r) >= 2 and r[1] not in ("", ".")]
        last, prev = rows[-1], rows[-2]
        v, p = float(last[1]), float(prev[1])
        return {"value": round(v, 2), "changePct": round((v / p - 1) * 100, 2),
                "date": last[0], "source": "FRED (VIXCLS)",
                "url": "https://fred.stlouisfed.org/series/VIXCLS"}
    except Exception as e:
        log(f"VIX (FRED) failed: {e}")
    return None


# ---------- CNN Fear & Greed ----------
def fetch_fear_greed():
    try:
        d = json.loads(get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata"))
        fg = d["fear_and_greed"]
        ts = str(fg.get("timestamp", ""))
        try:
            date = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            date = dt.datetime.utcfromtimestamp(float(ts) / 1000).date().isoformat()
        out = {"value": round(float(fg["score"]), 1),
               "rating": str(fg["rating"]).title(),
               "date": date, "source": "CNN",
               "url": "https://www.cnn.com/markets/fear-and-greed"}
        if fg.get("previous_close") is not None:
            out["prev"] = round(float(fg["previous_close"]), 1)
        return out
    except Exception as e:
        log(f"Fear & Greed failed: {e}")
    return None


# ---------- Cboe Put/Call Ratio ----------
def _cboe_ratios(date):
    url = ("https://cdn.cboe.com/data/us/options/market_statistics/daily/"
           f"{date.isoformat()}_daily_options")
    d = json.loads(get(url))
    ratios = {}
    for r in d.get("ratios", []):
        name = str(r.get("name", "")).upper()
        try:
            ratios[name] = float(r.get("value"))
        except (TypeError, ValueError):
            pass
    return ratios


def fetch_put_call():
    found = []  # [(date, ratios)] 新しい順に2営業日分
    day = dt.datetime.now(dt.timezone(dt.timedelta(hours=-5))).date()  # 米東部の今日（概算）
    for _ in range(10):
        try:
            ratios = _cboe_ratios(day)
            if ratios:
                found.append((day, ratios))
                if len(found) == 2:
                    break
        except Exception:
            pass
        day -= dt.timedelta(days=1)
    if not found:
        log("Put/Call failed: no Cboe daily data found")
        return None
    key = next((k for k in ("TOTAL PUT/CALL RATIO", "INDEX PUT/CALL RATIO",
                            "EQUITY PUT/CALL RATIO") if k in found[0][1]), None)
    if key is None:
        log(f"Put/Call failed: unknown ratio names {list(found[0][1])}")
        return None
    out = {"value": round(found[0][1][key], 2),
           "label": "Cboe " + key.replace(" PUT/CALL RATIO", "").title() + " Put/Call",
           "date": found[0][0].isoformat(), "source": "Cboe",
           "url": "https://www.cboe.com/us/options/market_statistics/daily/"}
    if len(found) == 2 and key in found[1][1]:
        out["prev"] = round(found[1][1][key], 2)
    return out


def append_history(market, fetched_at):
    path = os.path.join(DATA_DIR, "history.csv")
    header = ["fetched_at", "vix_date", "vix", "vix_change_pct",
              "fg_date", "fear_greed", "fg_rating", "pc_date", "put_call", "pc_label"]
    v, f, p = market.get("vix", {}), market.get("fearGreed", {}), market.get("putCall", {})
    row = [fetched_at, v.get("date", ""), v.get("value", ""), v.get("changePct", ""),
           f.get("date", ""), f.get("value", ""), f.get("rating", ""),
           p.get("date", ""), p.get("value", ""), p.get("label", "")]
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(header)
        w.writerow(row)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    market = {}
    for key, fn in (("vix", fetch_vix), ("fearGreed", fetch_fear_greed),
                    ("putCall", fetch_put_call)):
        val = fn()
        if val:
            market[key] = val
    fetched_at = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds")
    out = {"fetchedAt": fetched_at, "market": market}
    with open(os.path.join(DATA_DIR, "market.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    append_history(market, fetched_at)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    # 1件も取れなければ失敗として終了（GitHub上で失敗が分かるように）
    sys.exit(0 if market else 1)


if __name__ == "__main__":
    main()
