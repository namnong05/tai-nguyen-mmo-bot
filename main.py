import asyncio
import uvicorn
from .db import init_db
from .shopbot import start_polling
from .payments import app
from .config import PORT

async def main():
    await init_db()
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    await asyncio.gather(start_polling(), server.serve())

if __name__ == "__main__":
    asyncio.run(main())
