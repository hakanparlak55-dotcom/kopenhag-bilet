import os, datetime as dt, requests

SERPAPI_KEY = os.environ["SERPAPI_KEY"]
TG_TOKEN    = os.environ.get("TELEGRAM_TOKEN")
TG_CHAT     = os.environ.get("TELEGRAM_CHAT_ID")

ORIGIN       = "IST,SAW"          # iki İstanbul havalimanı birlikte
DEST         = os.environ.get("DEST", "CPH")
ADULTS       = 2
CURRENCY     = "TRY"
MAX_PRICE    = int(os.environ.get("MAX_PRICE", "18000"))  # 2 kişi toplam hedef
NONSTOP_ONLY = os.environ.get("NONSTOP_ONLY", "0") == "1"
ALERT_ONLY   = os.environ.get("ALERT_ONLY", "1") == "1"   # 1 = sadece hedef altı varsa mesaj at
IS_SCHEDULED = os.environ.get("GITHUB_EVENT_NAME") == "schedule"

FRIDAYS  = ["2027-01-22", "2027-01-29", "2027-02-05"]
PATTERNS = [(0, 2, "Cum→Paz"), (0, 3, "Cum→Pzt"), (1, 3, "Cmt→Pzt")]


def search(out_date, ret_date):
    params = {
        "engine": "google_flights", "departure_id": ORIGIN, "arrival_id": DEST,
        "outbound_date": out_date, "return_date": ret_date, "type": "1",
        "adults": ADULTS, "currency": CURRENCY, "hl": "tr", "gl": "tr",
        "api_key": SERPAPI_KEY,
    }
    if NONSTOP_ONLY:
        params["stops"] = "1"
    r = requests.get("https://serpapi.com/search.json", params=params, timeout=90)
    r.raise_for_status()
    d = r.json()
    if "error" in d:
        return None, d["error"]
    offers = [o for o in d.get("best_flights", []) + d.get("other_flights", []) if o.get("price")]
    if not offers:
        return None, "uçuş bulunamadı"
    best = min(offers, key=lambda o: o["price"])
    legs = best["flights"]
    return {
        "price":   best["price"],
        "airline": ", ".join(sorted({l.get("airline", "?") for l in legs})),
        "dep":     f'{legs[0]["departure_airport"]["id"]} {legs[0]["departure_airport"]["time"][-5:]}',
        "arr":     f'{legs[-1]["arrival_airport"]["id"]} {legs[-1]["arrival_airport"]["time"][-5:]}',
        "stops":   len(legs) - 1,
        "level":   d.get("price_insights", {}).get("price_level", "-"),
        "url":     d.get("search_metadata", {}).get("google_flights_url", ""),
    }, None


def send(text):
    if not (TG_TOKEN and TG_CHAT):
        print(text); return
    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                  data={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML",
                        "disable_web_page_preview": "true"}, timeout=30)


def main():
    today, results, errors = dt.date.today(), [], []
    for fri in FRIDAYS:
        f = dt.date.fromisoformat(fri)
        for o, rt, label in PATTERNS:
            out, ret = f + dt.timedelta(days=o), f + dt.timedelta(days=rt)
            if out <= today:
                continue
            try:
                info, err = search(out.isoformat(), ret.isoformat())
            except Exception as e:
                info, err = None, str(e)
            tag = f"{out:%d.%m} – {ret:%d.%m} ({label})"
            if info:
                results.append((tag, info))
            else:
                errors.append(f"{tag}: {err}")

    results.sort(key=lambda x: x[1]["price"])
    hits = [r for r in results if r[1]["price"] <= MAX_PRICE]

    # Otomatik taramada: hedef altı yoksa sessiz kal. Elle çalıştırınca: her zaman listeyi gönder.
    if ALERT_ONLY and IS_SCHEDULED and not hits:
        print("Hedef altında bilet yok."); return

    header = "🚨 <b>FIRSAT VAR!</b>\n" if hits else "📋 Güncel fiyatlar (hedef altı yok)\n"
    lines = [header + f"✈️ <b>İstanbul → {DEST}</b> | 2 kişi gidiş-dönüş | hedef ≤ {MAX_PRICE:,} TL\n"]
    for tag, i in results:
        mark = "🔥" if i["price"] <= MAX_PRICE else "•"
        stops = "direkt" if i["stops"] == 0 else f'{i["stops"]} aktarma'
        lines.append(f'{mark} <b>{i["price"]:,} TL</b> — {tag}\n'
                     f'   {i["airline"]} | {i["dep"]} → {i["arr"]} | {stops} | fiyat: {i["level"]}\n'
                     f'   <a href="{i["url"]}">Google Flights\'ta aç</a>')
    if errors:
        lines.append("\n⚠️ " + "\n⚠️ ".join(errors))
    send("\n".join(lines))


if __name__ == "__main__":
    main()
