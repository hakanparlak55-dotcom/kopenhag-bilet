import os, html, datetime as dt, requests

SERPAPI_KEY = os.environ["SERPAPI_KEY"]
TG_TOKEN    = os.environ.get("TELEGRAM_TOKEN")
TG_CHAT     = os.environ.get("TELEGRAM_CHAT_ID")

ORIGIN       = "IST,SAW"
DEST         = os.environ.get("DEST", "CPH")
ADULTS       = 2
CURRENCY     = "TRY"
MAX_PRICE    = int(os.environ.get("MAX_PRICE", "15000"))
NONSTOP_ONLY = os.environ.get("NONSTOP_ONLY", "0") == "1"
ALERT_ONLY   = os.environ.get("ALERT_ONLY", "1") == "1"
IS_SCHEDULED = os.environ.get("GITHUB_EVENT_NAME") == "schedule"

FRIDAYS  = ["2027-01-22", "2027-01-29", "2027-02-05"]
PATTERNS = [(0, 2), (0, 3), (1, 3)]   # Cum→Paz, Cum→Pzt, Cmt→Pzt

AYLAR     = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
             "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
GUNLER    = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
GUN_KISA  = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
SEVIYE    = {"low": "🟢 Ucuz", "typical": "🟡 Normal", "high": "🔴 Pahalı"}


def tl(x):
    return f"{x:,.0f}".replace(",", ".") + " TL"


def tarih(out, ret, kisa=False):
    g = GUN_KISA if kisa else GUNLER
    if out.month == ret.month:
        d = f"{out.day}–{ret.day} {AYLAR[out.month]}"
    else:
        d = f"{out.day} {AYLAR[out.month]} – {ret.day} {AYLAR[ret.month]}"
    return f"{d} ({g[out.weekday()]} → {g[ret.weekday()]})"


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
        "level":   d.get("price_insights", {}).get("price_level", ""),
        "url":     d.get("search_metadata", {}).get("google_flights_url", ""),
    }, None


def blok(r, emoji):
    i = r["info"]
    aktarma = "Direkt uçuş" if i["stops"] == 0 else f'{i["stops"]} aktarmalı'
    return (f'{emoji} <b>{tarih(r["out"], r["ret"])}</b>\n'
            f'💰 <b>{tl(i["price"])}</b>  (kişi başı {tl(i["price"] / ADULTS)})\n'
            f'✈️ {html.escape(i["airline"])} · {aktarma}\n'
            f'🛫 Gidiş: {i["dep"]} → {i["arr"]}\n'
            f'📊 Fiyat seviyesi: {SEVIYE.get(i["level"], "-")}\n'
            f'🔗 <a href="{i["url"]}">Bileti Google Flights\'ta gör</a>')


def satir(r):
    i = r["info"]
    aktarma = "direkt" if i["stops"] == 0 else f'{i["stops"]} aktarma'
    return (f'• {tarih(r["out"], r["ret"], kisa=True)}\n'
            f'   <b>{tl(i["price"])}</b> · {html.escape(i["airline"])} · {aktarma}')


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
        for o, rt in PATTERNS:
            out, ret = f + dt.timedelta(days=o), f + dt.timedelta(days=rt)
            if out <= today:
                continue
            try:
                info, err = search(out.isoformat(), ret.isoformat())
            except Exception as e:
                info, err = None, str(e)
            if info:
                results.append({"out": out, "ret": ret, "info": info})
            else:
                errors.append(f"{tarih(out, ret, kisa=True)}: {err}")

    results.sort(key=lambda r: r["info"]["price"])
    hits = [r for r in results if r["info"]["price"] <= MAX_PRICE]
    rest = [r for r in results if r["info"]["price"] > MAX_PRICE]

    if ALERT_ONLY and IS_SCHEDULED and not hits:
        print("Hedef altında bilet yok."); return

    parts = []
    if hits:
        parts.append(f"🚨 <b>FIRSAT VAR!</b>\n"
                     f"İstanbul → Kopenhag için {tl(MAX_PRICE)} altında "
                     f"{len(hits)} seçenek bulundu.")
        parts += [blok(r, "🔥") for r in hits]
    elif results:
        parts.append(f"📋 <b>Güncel durum</b>\n"
                     f"İstanbul → Kopenhag için {tl(MAX_PRICE)} altında bilet yok.\n\n"
                     f"<b>Şu an en ucuz seçenek:</b>")
        parts.append(blok(results[0], "⭐"))
        rest = results[1:]
    else:
        parts.append("⚠️ Hiç sonuç alınamadı.")

    if rest:
        parts.append("<b>Diğer seçenekler:</b>\n" + "\n".join(satir(r) for r in rest))
    if errors:
        parts.append("⚠️ <b>Aranamayanlar:</b>\n" + "\n".join(html.escape(e) for e in errors))
    parts.append("<i>ℹ️ Tüm fiyatlar 2 kişinin gidiş-dönüş TOPLAM fiyatıdır. "
                 "Dönüş saatlerini linkten görebilirsin.</i>")

    send("\n\n".join(parts))


if __name__ == "__main__":
    main()
