import re
import os
import sys
import shutil
import urllib3
import requests
import openpyxl
from pathlib import Path
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ["CURL_CA_BUNDLE"] = ""
os.environ["REQUESTS_CA_BUNDLE"] = ""
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_orig_request = requests.Session.request
def _no_verify_request(self, method, url, **kwargs):
    kwargs["verify"] = False
    return _orig_request(self, method, url, **kwargs)
requests.Session.request = _no_verify_request

EXCEL = Path(__file__).parent / "data" / "link shp file.xlsx"
OUTPUT_BASE = Path(__file__).parent / "data" / "raw" / "ldd-data" / "admin-boundary"
DRIVE_API = "https://www.googleapis.com/drive/v3"

def folder_id_from_url(url):
    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else None

def list_filenames(session, folder_id):
    files, params = [], {
        "q": f"'{folder_id}' in parents and trashed = false",
        "fields": "nextPageToken, files(name)",
        "corpora": "allDrives",
        "includeItemsFromAllDrives": "true",
        "supportsAllDrives": "true",
        "pageSize": 100,
    }
    while True:
        r = session.get(f"{DRIVE_API}/files", params=params)
        r.raise_for_status()
        data = r.json()
        files.extend(f["name"] for f in data.get("files", []))
        token = data.get("nextPageToken")
        if not token:
            break
        params["pageToken"] = token
    return set(files)

def main():
    token = os.environ.get("GDRIVE_TOKEN", "").strip()
    if not token:
        print("ERROR: Set GDRIVE_TOKEN (needed for splitting duplicate provinces).")
        sys.exit(1)
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    wb = openpyxl.load_workbook(EXCEL)
    ws = wb.active
    rows = [(r[0], int(r[1]), r[2].strip()) for r in list(ws.iter_rows(values_only=True))[1:] if r[0] and r[1] and r[2]]

    counts = Counter(r[0] for r in rows)
    duplicates = {name for name, c in counts.items() if c > 1}

    # --- Non-duplicates: simple rename ---
    for province, year, url in rows:
        if province in duplicates:
            continue
        old = OUTPUT_BASE / province
        new = OUTPUT_BASE / f"{province}_{year}"
        if not old.exists():
            print(f"MISSING (already renamed?): {old}")
            continue
        if new.exists():
            print(f"skip (exists): {new.name}")
            continue
        old.rename(new)
        print(f"renamed: {province}  →  {province}_{year}")

    # --- Duplicates: split by querying Drive for each year's file list ---
    for province in duplicates:
        mixed = OUTPUT_BASE / province
        if not mixed.exists():
            print(f"MISSING duplicate folder: {province}")
            continue

        entries = [(year, url) for p, year, url in rows if p == province]
        print(f"\nSplitting {province} ({[e[0] for e in entries]})...")

        for year, url in entries:
            folder_id = folder_id_from_url(url)
            dest = OUTPUT_BASE / f"{province}_{year}"
            dest.mkdir(exist_ok=True)
            remote_names = list_filenames(session, folder_id)
            print(f"  {province}_{year}: {len(remote_names)} files from Drive")
            for fname in remote_names:
                src = mixed / fname
                if src.exists():
                    shutil.move(str(src), dest / fname)
                    print(f"    moved: {fname}")
                else:
                    print(f"    MISSING locally: {fname}")

        remaining = list(mixed.iterdir())
        if remaining:
            print(f"  WARNING: {len(remaining)} unmatched file(s) left in {province}/:")
            for f in remaining:
                print(f"    {f.name}")
        else:
            mixed.rmdir()
            print(f"  removed empty folder: {province}/")

    print("\nDone.")

if __name__ == "__main__":
    main()
