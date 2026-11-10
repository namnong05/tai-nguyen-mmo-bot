import hmac
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from . import db
from .config import SEPAY_API_KEY
from .shopbot import bot

app = FastAPI(title="Tai Nguyen MMO SePay webhook")

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/sepay/webhook")
async def sepay_webhook(request: Request):
    auth = request.headers.get("authorization", "")
    expected = f"Apikey {SEPAY_API_KEY}"
    if not hmac.compare_digest(auth, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    transfer_type = str(payload.get("transferType", "")).lower()
    if transfer_type not in ("in", "inbound"):
        return JSONResponse({"success": True, "ignored": "not_incoming"}, status_code=200)

    event_id = str(payload.get("id") or payload.get("referenceCode") or "").strip()
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing transaction id")
    try:
        amount = int(float(payload.get("transferAmount", 0)))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid amount")
    content = str(payload.get("content", "")) + " " + str(payload.get("code", ""))
    normalized = content.upper()

    async with await db.connect() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        existing = await (await conn.execute(
            "SELECT event_id FROM payment_events WHERE event_id=?", (event_id,)
        )).fetchone()
        if existing:
            await conn.rollback()
            return JSONResponse({"success": True, "duplicate": True}, status_code=200)

        deposits = await (await conn.execute(
            "SELECT * FROM deposits WHERE status='pending' ORDER BY id DESC"
        )).fetchall()
        match = next((d for d in deposits if d["code"].upper() in normalized), None)
        if not match:
            await conn.rollback()
            return JSONResponse({"success": True, "matched": False}, status_code=200)

        from datetime import datetime, timezone
        try:
            expires = datetime.fromisoformat(match["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
        except ValueError:
            await conn.rollback()
            raise HTTPException(status_code=500, detail="Invalid deposit expiry")

        if datetime.now(timezone.utc) > expires or amount != match["amount"]:
            await conn.rollback()
            return JSONResponse({"success": True, "matched": True, "credited": False}, status_code=200)

        await conn.execute(
            "INSERT INTO payment_events(event_id,deposit_id,amount) VALUES(?,?,?)",
            (event_id, match["id"], amount)
        )
        await conn.execute(
            "UPDATE deposits SET status='paid',paid_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",
            (match["id"],)
        )
        await conn.execute(
            "UPDATE users SET balance=balance+? WHERE telegram_id=?",
            (match["amount"], match["telegram_id"])
        )
        await conn.commit()

    try:
        await bot.send_message(
            match["telegram_id"],
            f"✅ Đã xác nhận nạp tiền <b>{match['amount']:,} VNĐ</b>.\n"
            f"Mã giao dịch: <code>{match['code']}</code>\nSố dư ví đã được cập nhật."
        )
    except Exception:
        pass
    return JSONResponse({"success": True, "credited": True}, status_code=200)
