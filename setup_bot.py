import sys
import os

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

import requests
from config import LICHESS_API_TOKEN, BASE_DIR

LICHESS_HOST = "https://lichess.org"


def upgrade_account(token: str):
    if not token:
        print("❌ Error: No API token provided.")
        print("Please create an API token at https://lichess.org/account/oauth/token")
        print("and place it into your .env file as LICHESS_API_TOKEN=lip_...")
        return False

    headers = {
        "Authorization": f"Bearer {token}"
    }

    print("🔍 Testing connection to Lichess API...")
    try:
        res = requests.get(f"{LICHESS_HOST}/api/account", headers=headers, timeout=10)
        if res.status_code == 401:
            print("❌ Invalid API Token (HTTP 401 Unauthorized).")
            print("Please double check that your token was copied correctly.")
            return False
        res.raise_for_status()
        user_info = res.json()
    except requests.RequestException as e:
        print(f"❌ Failed to reach Lichess: {e}")
        return False

    username = user_info.get("username", "Unknown")
    title = user_info.get("title")
    print(f"✅ Authenticated successfully as: {username}")

    if title == "BOT":
        print(f"🎉 Account '{username}' is already an official BOT account! Ready to play.")
        return True

    print(f"\n⚙️ Account '{username}' is currently a standard user account.")
    print("Attempting to upgrade to official Lichess BOT status...")

    try:
        upgrade_res = requests.post(f"{LICHESS_HOST}/api/bot/account/upgrade", headers=headers, timeout=10)
        if upgrade_res.status_code == 200:
            print(f"🎉 SUCCESS! Account '{username}' has been upgraded to a Lichess BOT!")
            print("You can now run 'python bot.py' to start Panic Fish.")
            return True
        elif upgrade_res.status_code == 400:
            error_msg = upgrade_res.text
            print(f"❌ Cannot upgrade account (HTTP 400): {error_msg}")
            print("\n⚠️ IMPORTANT LICHESS RULE:")
            print("Accounts that have already played human games CANNOT be converted into BOT accounts.")
            print("If you have played games on this account, please register a fresh Lichess account and generate a new token.")
            return False
        else:
            print(f"❌ Upgrade failed (HTTP {upgrade_res.status_code}): {upgrade_res.text}")
            return False
    except requests.RequestException as e:
        print(f"❌ Network error while upgrading: {e}")
        return False


def main():
    print("========================================")
    print(" Panic Fish - Lichess Bot Setup Helper  ")
    print("========================================")

    token = LICHESS_API_TOKEN
    if not token or token == "your_lichess_token_here":
        env_path = BASE_DIR / ".env"
        print(f"No token found in {env_path}")
        user_input_token = input("Enter your Lichess API Token (lip_...): ").strip()
        if user_input_token:
            token = user_input_token
            # Write/update .env file
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(f"LICHESS_API_TOKEN={token}\n")
            print(f"Saved token to {env_path}\n")

    success = upgrade_account(token)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
