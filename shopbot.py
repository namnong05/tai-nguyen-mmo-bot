import asyncio
import io
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from . import db
from .config import (
    BOT_TOKEN, ADMIN_IDS, BANK_BIN, BANK_ACCOUNT, BANK_ACCOUNT_NAME,
    SUPPORT_USERNAME, DEPOSIT_TTL_MINUTES
)

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
pending_stock_upload = {}  # admin_id -> (sku, expiry UTC)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def home_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍️ Tất Cả Sản Phẩm", callback_data="products")],
        [InlineKeyboardButton(text="💰 Số Dư", callback_data="balance"),
         InlineKeyboardButton(text="🎒 Kho Đã Mua", callback_data="warehouse")],
        [InlineKeyboardButton(text="💳 Nạp Tiền", callback_data="deposit_help"),
         InlineKeyboardButton(text="🛟 Hỗ Trợ", callback_data="support")]
    ])

async def send_products(target, edit=False):
    async with await db.connect() as conn:
        rows = await (await conn.execute(
            "SELECT p.id,p.name,p.price,p.description,COUNT(s.id) AS stock_count "
            "FROM products p LEFT JOIN stock s ON s.product_id=p.id AND s.status='available' "
            "WHERE p.active=1 GROUP BY p.id ORDER BY p.id DESC"
        )).fetchall()
    if not rows:
        text = "🛍️ <b>Danh sách sản phẩm</b>\nHiện chưa có sản phẩm."
        if edit:
            await target.message.edit_text(text, reply_markup=home_keyboard())
        else:
            await target.answer(text, reply_markup=home_keyboard())
        return
    for row in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"🛒 Mua — {row['price']:,}đ", callback_data=f"buy:{row['id']}")
        ]])
        text = (f"📦 <b>{row['name']}</b>\n{row['description']}\n"
                f"💵 Giá: <b>{row['price']:,}đ</b>\n"
                f"📦 Còn: <b>{row['stock_count']}</b>")
        if edit:
            await target.message.answer(text, reply_markup=kb)
        else:
            await target.answer(text, reply_markup=kb)

@dp.message(Command("start"))
async def start(message: Message):
    await db.touch_user(message.from_user)
    await message.answer(
        "👋 Chào mừng đến với <b>TÀI NGUYÊN MMO</b>\n\n"
        "Chọn chức năng bên dưới hoặc dùng /sanpham, /sodu, /kho, /naptien, /hotro.",
        reply_markup=home_keyboard()
    )

@dp.message(Command("sanpham"))
async def products_cmd(message: Message):
    await db.touch_user(message.from_user)
    await send_products(message)

@dp.message(Command("sodu"))
async def balance_cmd(message: Message):
    async with await db.connect() as conn:
        row = await (await conn.execute(
            "SELECT balance FROM users WHERE telegram_id=?", (message.from_user.id,)
        )).fetchone()
    balance = row["balance"] if row else 0
    await message.answer(f"💎 Số dư ví hiện tại: <b>{balance:,} VNĐ</b>", reply_markup=home_keyboard())

@dp.message(Command("kho"))
async def warehouse_cmd(message: Message):
    async with await db.connect() as conn:
        rows = await (await conn.execute(
            "SELECT o.id,p.name,s.resource,o.created_at FROM orders o "
            "JOIN products p ON p.id=o.product_id JOIN stock s ON s.id=o.stock_id "
            "WHERE o.telegram_id=? ORDER BY o.id DESC LIMIT 30", (message.from_user.id,)
        )).fetchall()
    if not rows:
        await message.answer("🎒 Kho hàng của bạn hiện đang trống.", reply_markup=home_keyboard())
        return
    for r in rows:
        await message.answer(
            f"🎒 <b>{r['name']}</b> · Đơn #{r['id']}\n"
            f"<pre>{r['resource']}</pre>\nNgày mua: {r['created_at']}"
        )

@dp.message(Command("naptien"))
async def deposit_cmd(message: Message):
    await db.touch_user(message.from_user)
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Cú pháp: <code>/naptien 50000</code>\nSố tiền tối thiểu 10.000đ.")
        return
    amount = int(parts[1])
    if amount < 10000 or amount > 100000000:
        await message.answer("Số tiền nạp phải từ 10.000đ đến 100.000.000đ.")
        return
    import secrets
    code = "MMO" + secrets.token_hex(4).upper()
    expires = datetime.now(timezone.utc) + timedelta(minutes=DEPOSIT_TTL_MINUTES)
    async with await db.connect() as conn:
        await conn.execute(
            "INSERT INTO deposits(telegram_id,code,amount,expires_at) VALUES(?,?,?,?)",
            (message.from_user.id, code, amount, expires.isoformat())
        )
        await conn.commit()
    lines = [
        "💸 <b>THÔNG TIN CHUYỂN KHOẢN</b>",
        f"🏦 Ngân hàng: <b>{BANK_BIN or 'Chưa cấu hình'}</b>",
        f"💳 STK: <code>{BANK_ACCOUNT or 'Chưa cấu hình'}</code>",
        f"👤 Chủ TK: <b>{BANK_ACCOUNT_NAME or 'Chưa cấu hình'}</b>",
        f"💵 Số tiền: <b>{amount:,} VNĐ</b>",
        f"📝 Nội dung: <code>{code}</code>",
        f"⏳ Hết hạn: {DEPOSIT_TTL_MINUTES} phút",
        "⚠️ Chuyển khoản đúng số tiền và nội dung. Ví chỉ được cộng khi hệ thống xác nhận giao dịch thực tế."
    ]
    await message.answer("\n".join(lines))
    if BANK_BIN and BANK_ACCOUNT:
        qr = (f"https://img.vietqr.io/image/{quote(BANK_BIN)}-{quote(BANK_ACCOUNT)}-compact2.png"
              f"?amount={amount}&addInfo={quote(code)}&accountName={quote(BANK_ACCOUNT_NAME)}")
        await message.answer_photo(qr, caption="Quét QR để chuyển khoản")

@dp.message(Command("hotro"))
async def support_cmd(message: Message):
    contact = f"@{SUPPORT_USERNAME}" if SUPPORT_USERNAME else "Vui lòng liên hệ quản trị viên của shop."
    await message.answer(f"🛟 <b>TRUNG TÂM HỖ TRỢ</b>\nLiên hệ Admin: {contact}")

@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "<b>🛠️ ADMIN TÀI NGUYÊN MMO</b>\n"
        "/addproduct SKU | Tên | Giá | Mô tả\n"
        "/addstock SKU — sau đó gửi file TXT\n"
        "/products — xem sản phẩm/tồn kho\n"
        "/orders — 20 đơn gần nhất\n"
        "/users — số người dùng"
    )

@dp.message(Command("addproduct"))
async def add_product(message: Message):
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").partition(" ")[2]
    fields = [x.strip() for x in raw.split("|")]
    if len(fields) < 4 or not fields[2].isdigit():
        await message.answer("Cú pháp: /addproduct SKU | Tên | Giá | Mô tả")
        return
    sku, name, price, desc = fields[0], fields[1], int(fields[2]), "|".join(fields[3:])
    if not sku or not name or price < 0:
        await message.answer("SKU/tên không hợp lệ hoặc giá âm.")
        return
    try:
        async with await db.connect() as conn:
            await conn.execute(
                "INSERT INTO products(sku,name,price,description) VALUES(?,?,?,?)",
                (sku, name, price, desc)
            )
            await conn.commit()
        await message.answer(f"✅ Đã tạo sản phẩm <b>{name}</b> (SKU: {sku}).")
    except Exception:
        await message.answer("❌ Không tạo được. SKU có thể đã tồn tại.")

@dp.message(Command("addstock"))
async def add_stock(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Cú pháp: /addstock SKU")
        return
    sku = parts[1].strip()
    async with await db.connect() as conn:
        product = await (await conn.execute("SELECT id FROM products WHERE sku=? AND active=1", (sku,))).fetchone()
    if not product:
        await message.answer("Không tìm thấy SKU đang hoạt động.")
        return
    pending_stock_upload[message.from_user.id] = (
        sku, datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    await message.answer(f"📥 Hãy gửi file .txt cho SKU <b>{sku}</b> trong 5 phút. Mỗi dòng là một tài nguyên.")

@dp.message(F.document)
async def stock_file_upload(message: Message):
    if not is_admin(message.from_user.id) or message.from_user.id not in pending_stock_upload:
        return
    sku, expiry = pending_stock_upload[message.from_user.id]
    if datetime.now(timezone.utc) > expiry:
        pending_stock_upload.pop(message.from_user.id, None)
        await message.answer("Phiên nhập kho đã hết hạn. Gửi lại /addstock SKU.")
        return
    doc = message.document
    if not doc.file_name.lower().endswith(".txt") or doc.file_size > 2_000_000:
        await message.answer("Chỉ nhận file TXT tối đa 2MB.")
        return
    buffer = io.BytesIO()
    await bot.download(doc, destination=buffer)
    lines = [x.strip() for x in buffer.getvalue().decode("utf-8-sig", errors="replace").splitlines() if x.strip()]
    if not lines:
        await message.answer("File không có dòng tài nguyên hợp lệ.")
        return
    async with await db.connect() as conn:
        product = await (await conn.execute("SELECT id FROM products WHERE sku=?", (sku,))).fetchone()
        await conn.executemany(
            "INSERT INTO stock(product_id,resource) VALUES(?,?)",
            [(product["id"], item) for item in lines]
        )
        await conn.commit()
    pending_stock_upload.pop(message.from_user.id, None)
    await message.answer(f"✅ Đã nhập <b>{len(lines)}</b> tài nguyên cho SKU <b>{sku}</b>.")

@dp.message(Command("products"))
async def admin_products(message: Message):
    if not is_admin(message.from_user.id):
        return
    async with await db.connect() as conn:
        rows = await (await conn.execute(
            "SELECT p.sku,p.name,p.price,COUNT(s.id) AS qty FROM products p "
            "LEFT JOIN stock s ON s.product_id=p.id AND s.status='available' "
            "GROUP BY p.id ORDER BY p.id DESC"
        )).fetchall()
    if not rows:
        await message.answer("Chưa có sản phẩm.")
        return
    text = "\n".join(f"{r['sku']} · {r['name']} · {r['price']:,}đ · tồn {r['qty']}" for r in rows)
    await message.answer("<b>SẢN PHẨM / TỒN KHO</b>\n" + text)

@dp.message(Command("orders"))
async def admin_orders(message: Message):
    if not is_admin(message.from_user.id):
        return
    async with await db.connect() as conn:
        rows = await (await conn.execute(
            "SELECT o.id,o.telegram_id,p.name,o.price,o.created_at FROM orders o "
            "JOIN products p ON p.id=o.product_id ORDER BY o.id DESC LIMIT 20"
        )).fetchall()
    if not rows:
        await message.answer("Chưa có đơn hàng.")
        return
    text = "\n".join(f"#{r['id']} · user {r['telegram_id']} · {r['name']} · {r['price']:,}đ · {r['created_at']}" for r in rows)
    await message.answer("<b>20 ĐƠN GẦN NHẤT</b>\n" + text)

@dp.message(Command("users"))
async def admin_users(message: Message):
    if not is_admin(message.from_user.id):
        return
    async with await db.connect() as conn:
        row = await (await conn.execute("SELECT COUNT(*) AS n FROM users")).fetchone()
    await message.answer(f"👥 Người dùng đã tương tác: <b>{row['n']}</b>")

@dp.callback_query(F.data == "products")
async def products_callback(query: CallbackQuery):
    await query.answer()
    await send_products(query.message)

@dp.callback_query(F.data == "balance")
async def balance_callback(query: CallbackQuery):
    async with await db.connect() as conn:
        row = await (await conn.execute("SELECT balance FROM users WHERE telegram_id=?", (query.from_user.id,))).fetchone()
    await query.answer()
    await query.message.answer(f"💎 Số dư: <b>{(row['balance'] if row else 0):,} VNĐ</b>")

@dp.callback_query(F.data == "warehouse")
async def warehouse_callback(query: CallbackQuery):
    await query.answer()
    await warehouse_cmd_from_callback(query)

async def warehouse_cmd_from_callback(query):
    async with await db.connect() as conn:
        rows = await (await conn.execute(
            "SELECT o.id,p.name,s.resource FROM orders o JOIN products p ON p.id=o.product_id "
            "JOIN stock s ON s.id=o.stock_id WHERE o.telegram_id=? ORDER BY o.id DESC LIMIT 20",
            (query.from_user.id,)
        )).fetchall()
    if not rows:
        await query.message.answer("🎒 Kho hàng của bạn hiện đang trống.")
        return
    for r in rows:
        await query.message.answer(f"🎒 <b>{r['name']}</b> · #{r['id']}\n<pre>{r['resource']}</pre>")

@dp.callback_query(F.data == "deposit_help")
async def deposit_help_callback(query: CallbackQuery):
    await query.answer()
    await query.message.answer("Để tạo yêu cầu nạp, gửi lệnh /naptien 50000 (thay bằng số tiền bạn muốn nạp).")

@dp.callback_query(F.data == "support")
async def support_callback(query: CallbackQuery):
    await query.answer()
    contact = f"@{SUPPORT_USERNAME}" if SUPPORT_USERNAME else "Liên hệ Admin."
    await query.message.answer(f"🛟 Hỗ trợ: {contact}")

@dp.callback_query(F.data.startswith("buy:"))
async def buy_callback(query: CallbackQuery):
    await query.answer()
    product_id = int(query.data.split(":")[1])
    async with await db.connect() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        product = await (await conn.execute(
            "SELECT * FROM products WHERE id=? AND active=1", (product_id,)
        )).fetchone()
        user = await (await conn.execute(
            "SELECT balance FROM users WHERE telegram_id=?", (query.from_user.id,)
        )).fetchone()
        item = await (await conn.execute(
            "SELECT id,resource FROM stock WHERE product_id=? AND status='available' ORDER BY id LIMIT 1",
            (product_id,)
        )).fetchone()
        if not product or not item:
            await conn.rollback()
            await query.message.answer("❌ Sản phẩm không tồn tại hoặc đã hết hàng.")
            return
        balance = user["balance"] if user else 0
        if balance < product["price"]:
            await conn.rollback()
            await query.message.answer(
                f"❌ Số dư không đủ. Giá: {product['price']:,}đ · Ví: {balance:,}đ. Dùng /naptien để nạp."
            )
            return
        await conn.execute("UPDATE users SET balance=balance-? WHERE telegram_id=?",
                           (product["price"], query.from_user.id))
        await conn.execute("UPDATE stock SET status='sold', sold_at=CURRENT_TIMESTAMP WHERE id=? AND status='available'",
                           (item["id"],))
        await conn.execute(
            "INSERT INTO orders(telegram_id,product_id,stock_id,price) VALUES(?,?,?,?)",
            (query.from_user.id, product_id, item["id"], product["price"])
        )
        await conn.commit()
    await query.message.answer(
        f"✅ <b>Mua hàng thành công: {product['name']}</b>\n"
        f"🎁 Tài nguyên của bạn:\n<pre>{item['resource']}</pre>"
    )

async def start_polling():
    await dp.start_polling(bot)
