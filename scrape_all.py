"""Generate cached timetable data for every (year x session x track) combination.

Writes one JSON file per combination into web/data/ and refreshes
web/data/manifest.json, which the website reads to populate its
year / semester / track dropdowns. Run this once (or whenever the
timetable API data changes) to pre-populate the cache.

Usage:
    python scrape_all.py
"""
import subprocess
import sys
import os

YEARS = ["1", "2", "3", "4"]
SESSIONS = ["fall", "winter"]
TRACKS = ["computer", "electrical"]

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DATA = os.path.join(HERE, "web", "data")


def main():
    os.makedirs(WEB_DATA, exist_ok=True)
    total = 0
    for year in YEARS:
        for session in SESSIONS:
            for track in TRACKS:
                cmd = [sys.executable, "scrape.py",
                        "--year", year, "--session", session]
                if track:
                    cmd += ["--curriculum", track]
                print("\n=== year=%s session=%s track=%s ===" %
                      (year, session, track or "none"))
                try:
                    subprocess.run(cmd, check=True)
                    total += 1
                except subprocess.CalledProcessError as e:
                    print(f"  FAILED: {e}", file=sys.stderr)
    print(f"\nDone. {total} cached combinations written to {WEB_DATA}")


if __name__ == "__main__":
    main()
