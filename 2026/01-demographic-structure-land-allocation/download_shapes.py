import re
import os
import sys
import urllib3
import requests
import openpyxl
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Corporate proxy intercepts TLS — disable cert verification globally
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

def folder_id_from_url(url: str) -> str:
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError(f"Cannot extract folder ID from: {url}")
    return match.group(1)

def list_files(session, folder_id):
    """List all files in a Drive folder (handles pagination)."""
    files = []
    params = {
        "q": f"'{folder_id}' in parents and trashed = false",
        "fields": "nextPageToken, files(id, name, mimeType)",
        "corpora": "allDrives",
        "includeItemsFromAllDrives": "true",
        "supportsAllDrives": "true",
        "pageSize": 100,
    }
    while True:
        r = session.get(f"{DRIVE_API}/files", params=params)
        r.raise_for_status()
        data = r.json()
        files.extend(data.get("files", []))
        token = data.get("nextPageToken")
        if not token:
            break
        params["pageToken"] = token
    return files

def download_file(session, file_id, dest_path):
    """Download a single file by ID."""
    r = session.get(
        f"{DRIVE_API}/files/{file_id}",
        params={"alt": "media", "supportsAllDrives": "true"},
        stream=True,
    )
    r.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)

def main():
    token = os.environ.get("GDRIVE_TOKEN", "").strip()
    if not token:
        print("ERROR: Set GDRIVE_TOKEN environment variable with a Google OAuth access token.")
        print("Get one from: https://developers.google.com/oauthplayground/")
        print("  1. Select 'Drive API v3' > https://www.googleapis.com/auth/drive.readonly")
        print("  2. Authorize APIs, exchange code for tokens, copy 'Access token'")
        print("  3. Run: set GDRIVE_TOKEN=ya29.YOUR_TOKEN")
        sys.exit(1)

    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    wb = openpyxl.load_workbook(EXCEL)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))[1:]

    total = sum(1 for r in rows if r[0] and r[2])
    done = 0
    errors = []

    for row in rows:
        province, year, url = row
        if not province or not url:
            continue

        url = url.strip()
        folder_id = folder_id_from_url(url)
        dest = OUTPUT_BASE / province
        dest.mkdir(parents=True, exist_ok=True)

        done += 1
        print(f"\n[{done}/{total}] {province} ({int(year)})  folder={folder_id}")

        try:
            files = list_files(session, folder_id)
        except requests.HTTPError as e:
            print(f"  ERROR listing folder: {e}")
            errors.append((province, str(e)))
            continue

        if not files:
            print("  (no files found in folder)")
            continue

        to_download = [f for f in files if not (dest / f["name"]).exists()]
        skipped = len(files) - len(to_download)
        if skipped:
            print(f"  skip {skipped} existing file(s)")

        def _dl(f):
            fpath = dest / f["name"]
            download_file(session, f["id"], fpath)
            return f["name"]

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_dl, f): f for f in to_download}
            for fut in as_completed(futures):
                f = futures[fut]
                try:
                    print(f"  done: {fut.result()}")
                except Exception as e:
                    print(f"  ERROR {f['name']}: {e}")
                    errors.append((province, f["name"], str(e)))

    print(f"\n{'='*60}")
    print(f"Done. {done} provinces processed.")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(" ", e)

if __name__ == "__main__":
    main()
