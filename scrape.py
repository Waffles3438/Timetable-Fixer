"""Scrape U of T Engineering course data for schedule optimization.

Fetches course + section + meeting-time data from the official Timetable
Builder API (the same endpoint the ttb.utoronto.ca web app uses) and writes
it to courses.json, which the optimizer consumes.

    POST https://api.easi.utoronto.ca/ttb/getCourses

Common flags:
    --curriculum <track>  computer|electrical|ece  -> exact required courses
                           scraped live from the academic calendar
                           (computer->ECE297, electrical->ECE295)
    --year <n>            e.g. 2    -> year level for --curriculum
    --session fall|winter|both
                         fall=20269 (Fall 2026), winter=20271 (Winter 2027)
    --department <code>   e.g. ece  -> matches course-code prefix (ECE)
    --codes <c1> <c2>     keep exact course codes
    --prefix <p1> <p2>    keep codes starting with any prefix

Examples:
    python scrape.py --curriculum computer --year 2
    python scrape.py --curriculum electrical --year 2 --session fall
    python scrape.py --codes ECE201H1 MAT290H1
"""
import argparse
import json
import os
import sys
from collections import defaultdict

import requests

API = "https://api.easi.utoronto.ca/ttb"
HEADERS = {
    "Accept": "application/json",
    "Origin": "https://ttb.utoronto.ca",
    "Content-Type": "application/json",
}


def fetch_courses(sessions, divisions, course_levels, page_size=500):
    """POST /getCourses with filter body, paginate, return list of raw entries."""
    all_courses = []
    page = 0
    while True:
        body = {
            "sessions": sessions,
            "divisions": divisions,
            "courseLevels": course_levels,
            "page": page,
            "pageSize": page_size,
            "direction": "ASC",
        }
        r = requests.post(f"{API}/getCourses", headers=HEADERS, json=body, timeout=60)
        r.raise_for_status()
        page_courses = r.json().get("payload", [])
        if not page_courses:
            break
        all_courses.extend(page_courses)
        if len(page_courses) < page_size:
            break
        page += 1
    return all_courses


def filter_by_prefix(courses, prefix):
    """Keep only courses whose code starts with the given prefix(es)."""
    if not prefix:
        return courses
    prefixes = prefix if isinstance(prefix, list) else [prefix]
    return [c for c in courses if any(c["code"].startswith(p) for p in prefixes)]


def filter_by_codes(courses, codes):
    """Keep only courses whose code is in the given list (case-insensitive)."""
    wanted = {c.upper() for c in codes}
    return [c for c in courses if c["code"].upper() in wanted]


# Department code -> course-code prefix. Year is appended (e.g. "ECE" + "2" -> "ECE2").
DEPARTMENT_PREFIX = {
    "ece": "ECE",
    "che": "CHE",
    "civ": "CIV",
    "mie": "MIE",
    "mse": "MSE",
    "bme": "BME",
    "cme": "CME",
    "esc": "ESC",
    "min": "MIN",
    "phy": "PHY",
    "aer": "AER",
    "tep": "TEP",
    "mat": "MAT",
}

SESSION_CODES = {
    "fall": ["20269"],
    "winter": ["20271"],
    "both": ["20269", "20271"],
}

# Year -> course-level code used by the ttb API (year 1 = 100/A, year 2 = 200/B).
YEAR_LEVEL = {"1": ["100/A"], "2": ["200/B"], "3": ["300/C"], "4": ["400/D"]}


def main():
    parser = argparse.ArgumentParser(description="Scrape U of T timetable data.")
    parser.add_argument("--sessions", nargs="+", default=None,
                        help="Session codes, e.g. 20269 20271 (overrides --session)")
    parser.add_argument("--session", choices=["fall", "winter", "both"], default="both",
                        help="Semester selector (fall=20269, winter=20271)")
    parser.add_argument("--department", default=None,
                        help="Department code, e.g. ece (maps to course-code prefix)")
    parser.add_argument("--year", default=None,
                        help="Year level, e.g. 2 (maps to course-code level digit)")
    parser.add_argument("--curriculum", default=None,
                        choices=[ "computer", "electrical"],
                        help="Pull exact required courses from the academic calendar "
                             "(computer->ECE297, electrical->ECE295) e.g. --curriculum computer --year 2")
    parser.add_argument("--divisions", nargs="+", default=["APSC"],
                        help="Division codes, e.g. APSC")
    parser.add_argument("--levels", nargs="+", default=None,
                        help="Course level codes, e.g. 200/B (defaults to year's level)")
    parser.add_argument("--prefix", nargs="+", default=None,
                        help="Keep only course codes starting with these, e.g. ECE2 MAT2")
    parser.add_argument("--codes", nargs="+", default=None,
                        help="Keep only these exact course codes, e.g. ECE201H1 MAT290H1")
    parser.add_argument("--out", default="courses.json")
    args = parser.parse_args()

    sessions = args.sessions if args.sessions else SESSION_CODES[args.session]

    # Pick the course level: explicit --levels, else infer from --year.
    levels = args.levels
    if levels is None:
        if args.year in YEAR_LEVEL:
            levels = YEAR_LEVEL[args.year]
        else:
            levels = ["200/B"]

    # Build prefix filter from --department/--year if provided.
    prefixes = list(args.prefix) if args.prefix else []
    if args.department:
        dept = args.department.lower()
        if dept not in DEPARTMENT_PREFIX:
            print(f"Unknown department '{args.department}'. Known: "
                  f"{', '.join(sorted(DEPARTMENT_PREFIX))}", file=sys.stderr)
            sys.exit(1)
        year = args.year if args.year else ""
        prefixes.append(DEPARTMENT_PREFIX[dept] + year)

    # Derive exact required course codes from the academic calendar when
    # --curriculum is given (no hardcoded course lists).
    curriculum_codes = None
    if args.curriculum:
        from curriculum import get_program_courses
        if not args.year:
            print("--curriculum requires --year (e.g. --year 2)", file=sys.stderr)
            sys.exit(1)
        track = args.curriculum if args.curriculum in ("computer", "electrical") else None
        prog = get_program_courses("ece", args.year, track=track)
        # restrict to the requested session if not "both"
        if args.session != "both":
            curriculum_codes = set(prog.get(args.session, []))
        else:
            curriculum_codes = set().union(*prog.values()) if prog else set()
        if not curriculum_codes:
            print(f"No {args.year}-year courses found for '{args.curriculum}' "
                  f"in session '{args.session}'.", file=sys.stderr)
            sys.exit(1)
        print(f"  curriculum {args.curriculum} year {args.year} "
              f"({args.session}): {len(curriculum_codes)} courses")

    print(f"Fetching division={args.divisions} levels={levels} "
          f"sessions={sessions} ...")
    raw = fetch_courses(sessions, args.divisions, levels)
    print(f"  raw API entries: {len(raw)}")

    courses = filter_by_prefix(raw, prefixes) if prefixes else raw
    if prefixes:
        print(f"  after prefix filter {prefixes}: {len(courses)} entries")
    if curriculum_codes:
        courses = filter_by_codes(courses, curriculum_codes)
        print(f"  after curriculum filter: {len(courses)} entries")
    if args.codes:
        courses = filter_by_codes(courses, args.codes)
        print(f"  after codes filter {args.codes}: {len(courses)} entries")

    codes = sorted({c["code"] for c in courses})
    print(f"  distinct course codes ({len(codes)}): {', '.join(codes)}")

    if not courses:
        print("No courses matched. Check your session/division/prefix arguments.",
              file=sys.stderr)
        sys.exit(1)

    with open(args.out, "w") as f:
        json.dump(courses, f, indent=2)
    print(f"Saved {len(courses)} entries to {args.out}")

    # Keep the website's copy in sync if the web folder exists.
    web_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "web", "courses.json")
    if os.path.isdir(os.path.dirname(web_path)):
        with open(web_path, "w") as f:
            json.dump(courses, f, indent=2)
        print(f"Synced web/courses.json ({len(courses)} entries)")


if __name__ == "__main__":
    main()
