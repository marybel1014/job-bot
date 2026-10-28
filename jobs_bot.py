import json
import os
import html
from pathlib import Path

import feedparser
import requests

# ===================== НАЛАШТУВАННЯ =====================
# Вакансія проходить, якщо в НАЗВІ є хоча б одне слово з TITLE_INCLUDE
TITLE_INCLUDE = ["ui/ux", "ux/ui", "ui ux", "ux ui", "product designer",
                 "ux designer", "ui designer", "ux/ui designer", "ui/ux designer",
                 "web designer", "interaction designer", "digital designer"]
# ...і в назві немає жодного слова з TITLE_EXCLUDE (відсікаємо надто високі рівні та не ті ролі)
TITLE_EXCLUDE = ["senior", "sr.", "lead", "head of", "principal", "director",
                 "staff", "manager", "intern", "trainee", "researcher",
                 "graphic", "interior", "fashion", "3d", "motion"]

# Регіон: якщо в вакансії вказано локацію, вона має містити одне з цих слів.
# Якщо локація не вказана (RSS), вакансія проходить.
LOCATION_INCLUDE = ["worldwide", "anywhere", "europe", "emea", "ukraine", "global"]

# Твої RSS-стрічки (DOU, Djinni тощо, якщо знайдеш RSS за потрібним фільтром)
RSS_FEEDS = [
    # "https://...",
]

REMOTIVE_QUERY = "designer"
JOBICY_TAG = "designer"   # від 3 до 50 символів

MAX_PER_RUN = 15  # щоб на першому запуску не прийшла сотня повідомлень
# ========================================================

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
SEEN_FILE = Path("seen.json")


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=0), encoding="utf-8")


def fetch_remotive():
    try:
        r = requests.get("https://remotive.com/api/remote-jobs",
                         params={"search": REMOTIVE_QUERY}, timeout=30)
        r.raise_for_status()
        return [{
            "id": f"remotive-{j['id']}",
            "title": j["title"],
            "company": j["company_name"],
            "location": j.get("candidate_required_location", ""),
            "url": j["url"],
            "text": j["title"] + " " + (j.get("description") or ""),
            "source": "Remotive",
        } for j in r.json().get("jobs", [])]
    except Exception as e:
        print("Remotive error:", e)
        return []


def fetch_arbeitnow():
    try:
        r = requests.get("https://www.arbeitnow.com/api/job-board-api", timeout=30)
        r.raise_for_status()
        return [{
            "id": f"arbeitnow-{j['slug']}",
            "title": j["title"],
            "company": j["company_name"],
            "location": j.get("location", ""),
            "url": j["url"],
            "text": j["title"] + " " + (j.get("description") or "") + " " + " ".join(j.get("tags", [])),
            "source": "Arbeitnow",
        } for j in r.json().get("data", [])]
    except Exception as e:
        print("Arbeitnow error:", e)
        return []


def fetch_jobicy():
    try:
        r = requests.get("https://jobicy.com/api/v2/remote-jobs",
                         params={"count": 50, "tag": JOBICY_TAG}, timeout=30)
        r.raise_for_status()
        geo = lambda j: j.get("jobGeo", "")
        return [{
            "id": f"jobicy-{j['id']}",
            "title": j.get("jobTitle", ""),
            "company": j.get("companyName", ""),
            "location": geo(j) if isinstance(geo(j), str) else ", ".join(geo(j)),
            "url": j.get("url", ""),
            "source": "Jobicy",
        } for j in r.json().get("jobs", [])]
    except Exception as e:
        print("Jobicy error:", e)
        return []


def fetch_rss():
    jobs = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries:
                jobs.append({
                    "id": f"rss-{e.get('id') or e.get('link')}",
                    "title": e.get("title", ""),
                    "company": "",
                    "location": "",
                    "url": e.get("link", ""),
                    "text": e.get("title", "") + " " + e.get("summary", ""),
                    "source": feed.feed.get("title", "RSS"),
                })
        except Exception as ex:
            print("RSS error:", url, ex)
    return jobs


def matches(job):
    title = job["title"].lower()
    if not any(k in title for k in TITLE_INCLUDE):
        return False
    if any(k in title for k in TITLE_EXCLUDE):
        return False
    loc = job["location"].lower()
    if loc and not any(k in loc for k in LOCATION_INCLUDE):
        return False
    return True


def send(job):
    lines = [f"<b>{html.escape(job['title'])}</b>"]
    if job["company"]:
        lines.append(html.escape(job["company"]))
    if job["location"]:
        lines.append("📍 " + html.escape(job["location"]))
    lines.append(f"🔗 {job['url']}")
    lines.append(f"<i>{html.escape(job['source'])}</i>")
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": "\n".join(lines),
              "parse_mode": "HTML", "disable_web_page_preview": "true"},
        timeout=30,
    )
    r.raise_for_status()


def main():
    seen = load_seen()
    jobs = fetch_remotive() + fetch_arbeitnow() + fetch_jobicy() + fetch_rss()
    new = [j for j in jobs if j["id"] not in seen and matches(j)]
    print(f"Знайдено {len(jobs)}, нових підходящих {len(new)}")

    for job in new[:MAX_PER_RUN]:
        try:
            send(job)
            seen.add(job["id"])
        except Exception as e:
            print("Telegram error:", e)

    save_seen(seen)


if __name__ == "__main__":
    main()
