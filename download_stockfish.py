"""
Stockfish Engine Auto-Downloader
Fetches the latest official Windows Stockfish binary from GitHub Releases
and places stockfish.exe into the ./engine/ directory.
"""

import io
import os
import shutil
import sys
import zipfile
import requests

ENGINE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine")
STOCKFISH_EXE_PATH = os.path.join(ENGINE_DIR, "stockfish.exe")
GITHUB_API_URL = "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest"

HEADERS = {
    "User-Agent": "PanicFish-Bot-Downloader"
}


def download_and_extract_stockfish():
    os.makedirs(ENGINE_DIR, exist_ok=True)

    if os.path.exists(STOCKFISH_EXE_PATH):
        print(f"Stockfish binary already exists at: {STOCKFISH_EXE_PATH}")
        return STOCKFISH_EXE_PATH

    print("Querying GitHub API for the latest Stockfish release...")
    try:
        response = requests.get(GITHUB_API_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        release_data = response.json()
    except Exception as e:
        print(f"Failed to fetch release info from GitHub API: {e}")
        return None

    assets = release_data.get("assets", [])
    if not assets:
        print("No assets found in the latest Stockfish release.")
        return None

    # Find the best Windows asset (universal, avx2, or x86-64)
    target_asset = None
    priority_keywords = [
        ["windows", "x86-64-universal", ".zip"],
        ["windows", "x86-64-avx2", ".zip"],
        ["windows", "x86-64", ".zip"],
        ["windows", ".zip"]
    ]

    for keywords in priority_keywords:
        for asset in assets:
            name = asset.get("name", "").lower()
            if all(kw in name for kw in keywords):
                target_asset = asset
                break
        if target_asset:
            break

    if not target_asset:
        print("Could not automatically locate a Windows zip binary asset.")
        print("Available assets:")
        for a in assets:
            print(" -", a.get("name"))
        return None

    download_url = target_asset["browser_download_url"]
    asset_name = target_asset["name"]
    print(f"Downloading {asset_name} from {download_url}...")

    try:
        download_response = requests.get(download_url, headers=HEADERS, stream=True, timeout=60)
        download_response.raise_for_status()
        zip_bytes = io.BytesIO(download_response.content)

        print("Extracting Stockfish binary...")
        with zipfile.ZipFile(zip_bytes) as z:
            # Find the .exe inside the zip
            exe_names = [f for f in z.namelist() if f.lower().endswith(".exe")]
            if not exe_names:
                print("No .exe file found inside the downloaded archive.")
                return None

            main_exe = exe_names[0]
            with z.open(main_exe) as source, open(STOCKFISH_EXE_PATH, "wb") as target:
                shutil.copyfileobj(source, target)

        print(f"Successfully installed Stockfish to: {STOCKFISH_EXE_PATH}")
        return STOCKFISH_EXE_PATH

    except Exception as e:
        print(f"Error downloading or extracting Stockfish: {e}")
        return None


if __name__ == "__main__":
    path = download_and_extract_stockfish()
    if path:
        print(f"\nReady! Engine path: {path}")
    else:
        sys.exit(1)
