import os
import aiosqlite
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)
DB_PATH = os.getenv("DB_PATH", "bot_database.db")
if os.path.dirname(DB_PATH):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                preferred_quality TEXT DEFAULT 'best',
                is_premium INTEGER DEFAULT 0,
                premium_until TEXT,
                daily_downloads INTEGER DEFAULT 0,
                last_download_date TEXT,
                joined_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS downloads_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                url TEXT,
                platform TEXT,
                format_type TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()
    logger.info("Database initialized successfully.")

async def get_or_create_user(user_id: int, username: str = None, full_name: str = None) -> dict:
    today_str = date.today().isoformat()
    now_str = datetime.now().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()

        if not user:
            await db.execute("""
                INSERT INTO users (user_id, username, full_name, preferred_quality, is_premium, daily_downloads, last_download_date, joined_at)
                VALUES (?, ?, ?, 'best', 0, 0, ?, ?)
            """, (user_id, username, full_name, today_str, now_str))
            await db.commit()
            
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                user = await cursor.fetchone()
        else:
            # Update username/full_name if changed
            if username != user['username'] or full_name != user['full_name']:
                await db.execute("UPDATE users SET username = ?, full_name = ? WHERE user_id = ?", (username, full_name, user_id))
                await db.commit()

        # Check premium expiration
        is_premium = user['is_premium']
        if is_premium and user['premium_until']:
            prem_until = datetime.fromisoformat(user['premium_until'])
            if datetime.now() > prem_until:
                await db.execute("UPDATE users SET is_premium = 0, premium_until = NULL WHERE user_id = ?", (user_id,))
                await db.commit()
                is_premium = 0

        # Reset daily downloads if new day
        if user['last_download_date'] != today_str:
            await db.execute("UPDATE users SET daily_downloads = 0, last_download_date = ? WHERE user_id = ?", (today_str, user_id))
            await db.commit()
            daily_downloads = 0
        else:
            daily_downloads = user['daily_downloads']

        return {
            "user_id": user['user_id'],
            "username": user['username'],
            "full_name": user['full_name'],
            "preferred_quality": user['preferred_quality'] or 'best',
            "is_premium": bool(is_premium),
            "premium_until": user['premium_until'],
            "daily_downloads": daily_downloads,
            "joined_at": user['joined_at']
        }

async def update_user_quality(user_id: int, quality: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET preferred_quality = ? WHERE user_id = ?", (quality, user_id))
        await db.commit()

async def record_download(user_id: int, url: str, platform: str, format_type: str):
    today_str = date.today().isoformat()
    now_str = datetime.now().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO downloads_history (user_id, url, platform, format_type, created_at) VALUES (?, ?, ?, ?, ?)",
                         (user_id, url, platform, format_type, now_str))
        await db.execute("""
            UPDATE users 
            SET daily_downloads = CASE WHEN last_download_date = ? THEN daily_downloads + 1 ELSE 1 END,
                last_download_date = ?
            WHERE user_id = ?
        """, (today_str, today_str, user_id))
        await db.commit()

async def check_daily_limit(user_id: int, free_limit: int = 15) -> tuple[bool, int]:
    """Returns (can_download, current_usage)"""
    user = await get_or_create_user(user_id)
    if user['is_premium']:
        return True, user['daily_downloads']
    return user['daily_downloads'] < free_limit, user['daily_downloads']

async def grant_premium(user_id: int, days: int) -> bool:
    until_dt = datetime.now() + timedelta(days=days)
    until_str = until_dt.isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return False
        await db.execute("UPDATE users SET is_premium = 1, premium_until = ? WHERE user_id = ?", (until_str, user_id))
        await db.commit()
        return True

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()

async def get_setting(key: str, default: str = None) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def get_admin_stats() -> dict:
    today_str = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total_users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1") as c:
            premium_users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE last_download_date = ?", (today_str,)) as c:
            active_today = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM downloads_history") as c:
            total_downloads = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM downloads_history WHERE created_at LIKE ?", (f"{today_str}%",)) as c:
            downloads_today = (await c.fetchone())[0]

    return {
        "total_users": total_users,
        "premium_users": premium_users,
        "active_today": active_today,
        "total_downloads": total_downloads,
        "downloads_today": downloads_today
    }

async def get_all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]
