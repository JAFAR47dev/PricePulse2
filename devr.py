import os
import sys
import traceback

# ==============================
# PYDROID DEV RUNNER
# ==============================

PROJECT_ROOT = "/storage/emulated/0/wfolder"

def main():
    try:
        # 1. Force correct working directory
        os.chdir(PROJECT_ROOT)

        # 2. Add project root to PYTHONPATH
        if PROJECT_ROOT not in sys.path:
            sys.path.insert(0, PROJECT_ROOT)

        # 3. Optional: load secrets from local file
        secrets_path = os.path.join(PROJECT_ROOT, "secrets", "env.py")
        if os.path.exists(secrets_path):
            exec(open(secrets_path).read(), {})

        print("✅ Dev runner started")
        print("📂 Working dir:", os.getcwd())
        print("🐍 Python:", sys.version)

        # 4. Import and run your bot
        from bot.main import main as bot_main

        bot_main()

    except KeyboardInterrupt:
        print("\n⛔ Bot stopped manually")

    except Exception:
        print("\n❌ Bot crashed\n")
        traceback.print_exc()


if __name__ == "__main__":
    main()