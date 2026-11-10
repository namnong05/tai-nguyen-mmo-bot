import os
from dotenv import load_dotenv

load_dotenv()

def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Thiếu biến môi trường {name}; hãy cấu hình file .env")
    return value

BOT_TOKEN = required("BOT_TOKEN")
ADMIN_IDS = {int(x.strip()) for x in required("ADMIN_IDS").split(",") if x.strip()}
SEPAY_API_KEY = required("SEPAY_API_KEY")
BANK_BIN = os.getenv("BANK_BIN", "").strip()
BANK_ACCOUNT = os.getenv("BANK_ACCOUNT", "").strip()
BANK_ACCOUNT_NAME = os.getenv("BANK_ACCOUNT_NAME", "").strip()
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@")
DEPOSIT_TTL_MINUTES = int(os.getenv("DEPOSIT_TTL_MINUTES", "15"))
PORT = int(os.getenv("PORT", "8000"))
