#!/usr/bin/env python3
"""binday_calendar.py - derive the device schedule line from the Wiltshire Council calendar.

    python binday_calendar.py --uprn 100121050845           # fetch and print the line
    python binday_calendar.py --pdf Waste_collection_calendar.pdf
    python binday_calendar.py --uprn ... --email you@example.com

Email needs SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS in the environment.
Exit code 0 = line produced, 2 = parse problem (do it by hand this year).
"""
import argparse
import datetime as dt
import io
import os
import re
import smtplib
import sys
from email.message import EmailMessage

import pdfplumber
import requests

CAL_URL = "https://ilforms.wiltshire.gov.uk/wastecollectiondays/printablecalendar/{uprn}"
PERIOD = 14

# PDF section heading fragment -> device bin name
STREAMS = {
    "Householdwaste": "BLACK",
    "Mixeddryrecycling": "BLUE",
    "Blackboxrecycling": "BLUEBOX",   # checked equal to BLUE, not sent
    "gardenwaste": "GREEN",
}
MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}

# pdfplumber drops the spaces inside the headings, so match without them
SECTION_RE = re.compile(r"(Householdwaste|Mixeddryrecycling|Blackboxrecycling|gardenwaste)")
MONTH_NAMES = "January|February|March|April|May|June|July|August|September|October|November|December"


def fetch_pdf(uprn):
    r = requests.get(CAL_URL.format(uprn=uprn), timeout=30)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        raise RuntimeError("response is not a PDF; council page may have changed")
    return r.content


def extract_text(pdf_bytes):
    """Left and right column texts, so side-by-side boxes don't interleave."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        w, h = page.width, page.height
        left = page.crop((0, 0, w / 2, h)).extract_text() or ""
        right = page.crop((w / 2, 0, w, h)).extract_text() or ""
    return left + "\n" + right


def parse_streams(text):
    """Return {bin: sorted [date, ...]} from the four calendar grids."""
    result = {}
    parts = SECTION_RE.split(text)
    # parts = [pre, heading, body, heading, body, ...]
    for i in range(1, len(parts) - 1, 2):
        bin_name = STREAMS[parts[i]]
        body = parts[i + 1]
        dates = []
        lines = [ln.split() for ln in body.splitlines() if ln.strip()]
        # grid rows come as three lines: month names, years, date groups (one token per month)
        for k in range(len(lines) - 2):
            months, years, cells = lines[k], lines[k + 1], lines[k + 2]
            if not all(re.fullmatch(MONTH_NAMES, m) for m in months):
                continue
            if not all(re.fullmatch(r"\d{4}", y) for y in years):
                continue
            if not (len(months) == len(years) == len(cells)):
                raise RuntimeError(f"{bin_name}: grid row misaligned: {months} {cells}")
            for mon, year, cell in zip(months, years, cells):
                if cell == "Nodates":
                    continue
                if not re.fullmatch(r"\d+(,\d+)*", cell):
                    raise RuntimeError(f"{bin_name}: unexpected cell '{cell}'")
                for d in cell.split(","):
                    dates.append(dt.date(int(year), MONTHS[mon], int(d)))
        if not dates:
            raise RuntimeError(f"{bin_name}: no dates found")
        result[bin_name] = sorted(set(dates))
    missing = set(STREAMS.values()) - set(result)
    if missing:
        raise RuntimeError(f"streams not found in PDF: {sorted(missing)}")
    return result


def derive(dates, period=PERIOD):
    """Anchor + exceptions for one stream.

    Returns (anchor, [(expected, actual_or_None), ...], [unexplained actual dates]).
    """
    anchor = dates[0]
    actual = set(dates)
    expected = []
    d = anchor
    while d <= dates[-1]:
        expected.append(d)
        d += dt.timedelta(days=period)
    unmatched_actual = actual - set(expected)
    exceptions = []
    for e in expected:
        if e in actual:
            continue
        near = [a for a in unmatched_actual if abs((a - e).days) <= 6]
        if near:
            a = min(near, key=lambda x: abs((x - e).days))
            unmatched_actual.discard(a)
            exceptions.append((e, a))
        else:
            exceptions.append((e, None))
    return anchor, exceptions, sorted(unmatched_actual)


def build_line(streams):
    warnings = []
    if streams["BLUE"] != streams["BLUEBOX"]:
        warnings.append("blue bin and black box dates differ; black box ignored")
    fields = []
    excs = []
    last = max(d for ds in streams.values() for d in ds)
    for name in ("BLACK", "BLUE", "GREEN"):
        anchor, exceptions, extra = derive(streams[name])
        fields.append(f"{name}={anchor:%Y-%m-%d}/{PERIOD}")
        for e, a in exceptions:
            excs.append(f"{e:%Y-%m-%d}>{a:%Y-%m-%d}" if a else f"{e:%Y-%m-%d}>")
        if extra:
            warnings.append(f"{name}: dates not explained by the rule: "
                            + ", ".join(x.isoformat() for x in extra))
    line = ";".join(fields)
    if excs:
        line += ";X=" + ",".join(excs)
    line += f";H={last:%Y-%m-%d}"
    return line, warnings


def send_email(to, line, warnings):
    msg = EmailMessage()
    msg["Subject"] = "Bin day device: new schedule line"
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = to
    body = "Paste this into NFC Tools as a Text record and tap the device:\n\n" + line + "\n"
    if warnings:
        body += "\nCheck these by hand:\n" + "\n".join("- " + w for w in warnings) + "\n"
    msg.set_content(body)
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587"))) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--uprn")
    src.add_argument("--pdf")
    ap.add_argument("--email")
    ap.add_argument("--state", help="file holding the last line sent; email only on change")
    args = ap.parse_args()

    pdf_bytes = open(args.pdf, "rb").read() if args.pdf else fetch_pdf(args.uprn)
    try:
        streams = parse_streams(extract_text(pdf_bytes))
        line, warnings = build_line(streams)
    except Exception as e:
        print(f"PARSE FAILED: {e}", file=sys.stderr)
        sys.exit(2)

    print(line)
    for w in warnings:
        print("WARNING:", w, file=sys.stderr)

    changed = True
    if args.state and os.path.exists(args.state):
        changed = open(args.state).read().strip() != line
    if args.email and changed:
        send_email(args.email, line, warnings)
        print("emailed", file=sys.stderr)
    if args.state and changed:
        open(args.state, "w").write(line + "\n")


if __name__ == "__main__":
    main()
