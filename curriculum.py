"""Scrape the official U of T Engineering calendar for program course lists.

The Timetable Builder API has no reliable "program requirement" filter, so we
parse the academic calendar (engineering.calendar.utoronto.ca) to discover which
courses a given program/year actually requires. Nothing is hardcoded: the course
codes are extracted live from the calendar HTML tables.
"""
import re

import requests

CALENDAR_BASE = "https://engineering.calendar.utoronto.ca"

# Map a friendly program name to its calendar section slug.
PROGRAM_SLUG = {
    "electrical": "Electrical-and-Computer-Engineering",
    "computer": "Electrical-and-Computer-Engineering",
    "chemical": "Chemical-Engineering-and-Applied-Chemistry",
    "civil": "Civil-Engineering",
    "mechanical": "Mechanical-Engineering",
    "industrial": "Industrial-Engineering",
    "materials": "Materials-Science-and-Engineering",
    "mineral": "Mineral-Engineering",
}

SESSION_CODE = {"fall": "20269", "winter": "20271"}


def _section_url(program):
    slug = PROGRAM_SLUG.get(program.lower())
    if not slug:
        raise ValueError(
            f"Unknown program '{program}'. Known: {', '.join(sorted(PROGRAM_SLUG))}"
        )
    return f"{CALENDAR_BASE}/section/{slug}"


def _split_year_block(html, year_label, track=None):
    """Return the HTML slice for the given year section.

    `year_label` is an ordinal like 'FIRST'/'SECOND'. We anchor on the real
    section heading (e.g. 'SECOND YEAR COMPUTER ENGINEERING') so we don't
    accidentally match the program title ('...PROGRAM IN COMPUTER ENGINEERING')
    or a 'SECOND YEAR' mention inside later text.
    """
    track_word = (track or "computer").upper()
    heading = rf"{year_label} YEAR {track_word} ENGINEERING"
    m = re.search(heading, html)
    if not m:
        return None
    start = m.start()
    # Block ends at the next year heading or the 3rd/4th year section.
    end_m = re.search(
        r"THIRD AND FOURTH YEAR|FOURTH YEAR|"
        r"(?:SECOND|THIRD|FOURTH) YEAR (?:COMPUTER|ELECTRICAL) ENGINEERING",
        html[start + len(heading):],
    )
    end = start + len(heading) + end_m.start() if end_m else len(html)
    return html[start:end]


def _parse_sessions(block):
    """From a year block, return {session: set(course_codes)} using the
    Fall/Winter session headers inside the tables."""
    cur = None
    groups = {}
    for part in re.split(r"(Fall Session[^<]*|Winter Session[^<]*)", block):
        if re.match(r"Fall Session", part):
            cur = "fall"
        elif re.match(r"Winter Session", part):
            cur = "winter"
        elif cur:
            codes = re.findall(r"/course/([A-Z]{3,4}\d{3}[HY]\d)", part)
            groups.setdefault(cur, set()).update(codes)
    return groups


def _split_program_block(html, program):
    """Return the HTML slice for one program's section (Computer vs Electrical
    Engineering). Without a track we return the whole page (caller will then
    pick the first matching year block)."""
    if not program:
        return html
    titles = {
        "computer": "UNDERGRADUATE PROGRAM IN COMPUTER ENGINEERING",
        "electrical": "UNDERGRADUATE PROGRAM IN ELECTRICAL ENGINEERING",
    }
    title = titles.get(program.lower())
    if not title:
        return html
    start = html.find(title)
    if start == -1:
        return html
    # Next program section = next heading that is a *different* program title.
    others = [t for t in titles.values() if t != title]
    pattern = "(" + "|".join(re.escape(o) for o in others) + ")"
    nxt = re.search(pattern, html[start + len(title):])
    end = start + len(title) + nxt.start() if nxt else len(html)
    return html[start:end]


def get_program_courses(program, year, track=None):
    """Return {session: [course_codes]} for a program + year (e.g. '2').

    `track` disambiguates programs that share one calendar section:
        'computer'  -> ECE297 (Software Design & Communication)
        'electrical'-> ECE295 (Hardware Design & Communication)
    Scrapes the calendar live; no hardcoded course lists.
    """
    url = _section_url(program)
    html = requests.get(url, timeout=30).text
    html = _split_program_block(html, track)

    ordinal = {"1": "FIRST", "2": "SECOND", "3": "THIRD", "4": "FOURTH"}.get(str(year))
    if not ordinal:
        raise ValueError(f"Year must be 1-4, got '{year}'")
    block = _split_year_block(html, ordinal, track=track)
    if not block:
        return {}
    return {k: sorted(v) for k, v in _parse_sessions(block).items()}


if __name__ == "__main__":
    import json
    for tr in (None, "computer", "electrical"):
        res = get_program_courses("ece", "2", track=tr)
        print("track:", tr, json.dumps(res))
