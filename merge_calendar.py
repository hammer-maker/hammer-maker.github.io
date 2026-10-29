#!/usr/bin/env python3
"""Merge ChinaCalendar ICS feeds into one calendar. Runs in GitHub Actions or locally."""
from urllib.request import Request, urlopen
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

SOURCES = [
    # Main calendar: legal holidays, public/festival dates and solar terms (upstream scope may vary)
    "https://yangh9.github.io/ChinaCalendar/calendar.ics",
    # Official holiday arrangements and make-up workdays
    "https://yangh9.github.io/ChinaCalendar/cal_holiday.ics",
    # Lunar calendar (includes year-specific lunar dates/festivals)
    "https://yangh9.github.io/ChinaCalendar/cal_lunar.ics",
    # Solar terms
    "https://yangh9.github.io/ChinaCalendar/cal_solarTerm.ics",
    # Traditional and popular commemorative days
    "https://yangh9.github.io/ChinaCalendar/cal_festival.ics",
]

def fetch(url):
    req = Request(url, headers={"User-Agent": "ChinaCalendar-Merger/1.0"})
    with urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8-sig", errors="replace")

def unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text.replace("\r\n", "\n").replace("\r", "\n"))

def blocks(text, tag):
    text = unfold(text)
    pattern = rf"BEGIN:{tag}\n(.*?)\nEND:{tag}"
    return [f"BEGIN:{tag}\n{x}\nEND:{tag}" for x in re.findall(pattern, text, re.S)]

def prop(event, name):
    # Return property value, allowing parameters such as DTSTART;VALUE=DATE
    m = re.search(rf"(?m)^{name}(?:;[^:]*)?:(.*)$", event)
    return m.group(1).strip() if m else ""

def escape_text(s):
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

def main():
    all_events = []
    all_tz = {}
    errors = []
    for url in SOURCES:
        try:
            data = fetch(url)
            for tz in blocks(data, "VTIMEZONE"):
                tzid = prop(tz, "TZID")
                all_tz[tzid or tz] = tz
            all_events.extend((url, e) for e in blocks(data, "VEVENT"))
            print(f"OK {url}")
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            print(f"WARNING {url}: {exc}", file=sys.stderr)

    if not all_events:
        raise SystemExit("No ICS events downloaded; refusing to publish an empty calendar.")

    # Deduplicate events appearing in multiple feeds, while retaining same-day different events.
    unique = {}
    for source, event in all_events:
        start = prop(event, "DTSTART")
        summary = prop(event, "SUMMARY")
        uid = prop(event, "UID")
        key = (start, summary)
        # Prefer the first occurrence, usually from the main calendar.
        unique.setdefault(key if start or summary else (uid, event), event)

    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//China Calendar Combined//ZH",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:中国综合日历（节假日·调休·农历·节气）",
        "X-WR-TIMEZONE:Asia/Shanghai",
        f"X-WR-CALDESC:{escape_text('合并中国法定节假日、调休补班、传统节日、农历及二十四节气；由上游日历源定期重建。')}",
    ]
    for tz in all_tz.values():
        lines.extend(tz.splitlines())
    for event in unique.values():
        lines.extend(event.splitlines())
    lines.extend(["END:VCALENDAR", ""])
    out = Path("public/china-calendar.ics")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\r\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}: {len(unique)} unique events.")
    if errors:
        print("Some feeds failed; output was built from available feeds:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)

if __name__ == "__main__":
    main()
