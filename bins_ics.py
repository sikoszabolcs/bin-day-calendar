#!/usr/bin/env python3
"""bins_ics.py - turn the Wiltshire collection calendar PDF into an ICS file.

    python bins_ics.py --uprn 100121050845 -o bins.ics
    python bins_ics.py --pdf Waste_collection_calendar.pdf -o bins.ics

Events are all-day, one per stream per collection date, with a reminder at 18:00 the
evening before. Dates come straight from the PDF (no rule, no guessing).
"""
import argparse
import datetime as dt
import hashlib

from binday_calendar import fetch_pdf, extract_text, parse_streams

TITLES = {
    "BLACK":   "Household waste bin",
    "BLUE":    "Blue lid recycling bin",
    "BLUEBOX": "Black box (glass)",
    "GREEN":   "Garden waste bin",
}
# order streams for the same day
ORDER = ["BLACK", "BLUE", "BLUEBOX", "GREEN"]


def event(date, title, uid_seed):
    uid = hashlib.sha1(uid_seed.encode()).hexdigest()[:20] + "@binday"
    nxt = date + dt.timedelta(days=1)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return "\r\n".join([
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{date:%Y%m%d}",
        f"DTEND;VALUE=DATE:{nxt:%Y%m%d}",
        f"SUMMARY:{title}",
        "DESCRIPTION:Put the container out by 7am. Source: Wiltshire Council calendar.",
        "TRANSP:TRANSPARENT",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{title} tomorrow",
        "TRIGGER:-PT6H",
        "END:VALARM",
        "END:VEVENT",
    ])


def build_ics(streams, merge_same_day=True):
    by_day = {}
    for name in ORDER:
        for d in streams.get(name, []):
            by_day.setdefault(d, []).append(name)

    events = []
    for d in sorted(by_day):
        names = by_day[d]
        if merge_same_day:
            title = "Bins: " + " + ".join(TITLES[n] for n in names)
            events.append(event(d, title, f"{d}-{'-'.join(names)}"))
        else:
            for n in names:
                events.append(event(d, TITLES[n], f"{d}-{n}"))

    body = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//binday//bins_ics//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Bin collections",
        "X-WR-TIMEZONE:Europe/London",
        *events,
        "END:VCALENDAR",
    ])
    return body + "\r\n"


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--uprn")
    src.add_argument("--pdf")
    ap.add_argument("-o", "--out", default="bins.ics")
    ap.add_argument("--separate", action="store_true", help="one event per bin instead of one per day")
    args = ap.parse_args()

    pdf = open(args.pdf, "rb").read() if args.pdf else fetch_pdf(args.uprn)
    streams = parse_streams(extract_text(pdf))
    ics = build_ics(streams, merge_same_day=not args.separate)
    open(args.out, "w", newline="").write(ics)
    n = ics.count("BEGIN:VEVENT")
    print(f"wrote {args.out}: {n} events, {min(min(v) for v in streams.values())} to {max(max(v) for v in streams.values())}")


if __name__ == "__main__":
    main()
