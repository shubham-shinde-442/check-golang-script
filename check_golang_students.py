
#!/usr/bin/env python3
"""
Check which students have worked with Golang based on their GitHub profiles.

Requirements:
    pip install gspread google-auth requests

Setup:
    1. Create a Google Cloud service account and download the JSON key.
    2. Share your Google Sheet with the service account email.
    3. Set GITHUB_TOKEN env var (optional but highly recommended to avoid rate limits).

Usage:
    GITHUB_TOKEN=ghp_xxx GOOGLE_CREDS=credentials.json SHEET_NAME="My Sheet" python check_golang_students.py
"""

import os
import sys
import time
import requests
import gspread
from google.oauth2.service_account import Credentials

# ── Config ────────────────────────────────────────────────────────────────────

GOOGLE_CREDS_FILE = os.environ.get("GOOGLE_CREDS", "credentials.json")
SHEET_NAME        = os.environ.get("SHEET_NAME", "") 
WORKSHEET_INDEX   = int(os.environ.get("WORKSHEET_INDEX", "1")) 
COLUMN_HEADER     = os.environ.get("COLUMN_HEADER", "GitHub Username")

GITHUB_TOKEN      = os.environ.get("GITHUB_TOKEN", "")   
GITHUB_API        = "https://api.github.com"
REQUEST_DELAY     = 1.0   # seconds between GitHub API calls (be polite)

OUTPUT_FILE       = "golang_students.txt"

# ── Helpers ───────────────────────────────────────────────────────────────────

def github_headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def get_user_languages(username: str) -> set[str]:
    """Return the set of languages used across all public repos of a user."""
    languages: set[str] = set()
    page = 1
    while True:
        url = f"{GITHUB_API}/users/{username}/repos"
        resp = requests.get(
            url,
            headers=github_headers(),
            params={"per_page": 100, "page": page, "type": "owner"},
            timeout=15,
        )

        if resp.status_code == 404:
            print(f"  ⚠  User not found: {username}")
            return languages
        if resp.status_code == 403:
            reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait  = max(reset - int(time.time()), 5)
            print(f"  ⏳ Rate limited — sleeping {wait}s …")
            time.sleep(wait)
            continue
        if resp.status_code != 200:
            print(f"  ✗  HTTP {resp.status_code} for {username}")
            return languages

        repos = resp.json()
        if not repos:
            break

        for repo in repos:
            lang = repo.get("language")
            if lang:
                languages.add(lang)

        if len(repos) < 100:
            break
        page += 1
        time.sleep(REQUEST_DELAY)

    return languages


def has_golang(username: str) -> bool:
    langs = get_user_languages(username)
    return "Go" in langs


def load_usernames_from_sheet() -> list[str]:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds  = Credentials.from_service_account_file(GOOGLE_CREDS_FILE, scopes=scopes)
    client = gspread.authorize(creds)

    if not SHEET_NAME:
        print("Error: set SHEET_NAME env var to your Google Sheet's name.")
        sys.exit(1)

    sheet    = client.open(SHEET_NAME).get_worksheet(WORKSHEET_INDEX)
    records  = sheet.get_all_records()           # list of dicts keyed by header row

    usernames = []
    for row in records:
        username = str(row.get(COLUMN_HEADER, "")).strip()
        if username:
            usernames.append(username)

    return usernames


def main():
    print("=" * 60)
    print("  GitHub Golang Checker")
    print("=" * 60)

    if not GITHUB_TOKEN:
        print("⚠  GITHUB_TOKEN not set — unauthenticated requests are limited to "
              "60/hour. Set it for 5,000/hour.\n")

    print(f"📄 Loading usernames from Google Sheet: '{SHEET_NAME}' …")
    usernames = load_usernames_from_sheet()
    print(f"   Found {len(usernames)} student(s).\n")

    go_students     = []
    no_go_students  = []
    error_students  = []

    for i, username in enumerate(usernames, 1):
        print(f"[{i}/{len(usernames)}] Checking @{username} …", end=" ", flush=True)
        try:
            if has_golang(username):
                print("✅ Go found!")
                go_students.append(username)
            else:
                print("— no Go repos")
                no_go_students.append(username)
        except Exception as exc:
            print(f"ERROR: {exc}")
            error_students.append(username)
        time.sleep(REQUEST_DELAY)

    print("\n" + "=" * 60)
    print(f"  Results: {len(go_students)} / {len(usernames)} students have worked with Go")
    print("=" * 60)

    print(f"\n✅ Students WITH Go experience ({len(go_students)}):")
    for u in go_students:
        print(f"   • {u}  — https://github.com/{u}")

    print(f"\n❌ Students WITHOUT Go experience ({len(no_go_students)}):")
    for u in no_go_students:
        print(f"   • {u}")

    if error_students:
        print(f"\n⚠  Could not check ({len(error_students)}):")
        for u in error_students:
            print(f"   • {u}")

    with open(OUTPUT_FILE, "w") as f:
        f.write(f"Students with Go experience ({len(go_students)} / {len(usernames)})\n")
        f.write("=" * 50 + "\n")
        for u in go_students:
            f.write(f"{u}\n")
        f.write("\n\nStudents WITHOUT Go experience\n")
        f.write("=" * 50 + "\n")
        for u in no_go_students:
            f.write(f"{u}\n")
        if error_students:
            f.write("\n\nCould not check\n")
            f.write("=" * 50 + "\n")
            for u in error_students:
                f.write(f"{u}\n")

    print(f"\n💾 Results saved to '{OUTPUT_FILE}'")


if __name__ == "__main__":
    main()