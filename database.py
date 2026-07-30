import os
import aiosqlite
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)
DB_PATH = os.getenv("DB_PATH", "bot_database.db")
if os.path.dirname(DB_PATH):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def is_user_admin(user_id: int) -> bool:
    admin_env = os.getenv("ADMIN_IDS", "")
    for item in admin_env.split(","):
        item = item.strip()
        if item.isdigit() and int(item) == user_id:
            return True
    return False

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
                joined_at TEXT,
                referred_by INTEGER DEFAULT NULL,
                referral_count INTEGER DEFAULT 0
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
        # Safe migrations for existing DB
        try:
            await db.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT NULL")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN referral_count INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN coins INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'uz'")
        except Exception:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER UNIQUE,
                status TEXT DEFAULT 'pending',
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS redeem_codes (
                code TEXT PRIMARY KEY,
                reward_type TEXT,
                reward_value INTEGER,
                max_uses INTEGER,
                used_count INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_redeems (
                user_id INTEGER,
                code TEXT,
                redeemed_at TEXT,
                PRIMARY KEY (user_id, code)
            )
        """)
        # Fix unapplied redeem code premiums
        try:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT ur.user_id, rc.reward_value
                FROM user_redeems ur
                JOIN redeem_codes rc ON ur.code = rc.code
                JOIN users u ON ur.user_id = u.user_id
                WHERE LOWER(rc.reward_type) IN ('days', 'vip', 'premium', 'day') AND u.is_premium = 0
            """) as cur:
                unapplied = await cur.fetchall()
            for item in unapplied:
                uid = item['user_id']
                val = item['reward_value']
                until_dt = datetime.now() + timedelta(days=val)
                until_str = until_dt.isoformat()
                await db.execute("UPDATE users SET is_premium = 1, premium_until = ? WHERE user_id = ?", (until_str, uid))
            await db.commit()
        except Exception as e:
            logger.warning(f"Redeem sync error: {e}")

        await db.commit()
    logger.info("Database initialized successfully.")

async def get_user_referrals(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT referral_count FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

async def register_user_with_referral(user_id: int, username: str = None, full_name: str = None, ref_id: int = None) -> tuple[dict, bool, int]:
    today_str = date.today().isoformat()
    now_str = datetime.now().isoformat()
    is_new = False
    referrer_got_bonus = 0

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()

        if not user:
            is_new = True
            valid_ref_id = None
            if ref_id and ref_id != user_id:
                async with db.execute("SELECT user_id, referral_count FROM users WHERE user_id = ?", (ref_id,)) as r_cur:
                    ref_row = await r_cur.fetchone()
                if ref_row:
                    valid_ref_id = ref_id
                    new_count = (ref_row['referral_count'] or 0) + 1
                    await db.execute("UPDATE users SET referral_count = ? WHERE user_id = ?", (new_count, ref_id))
                    await db.execute("INSERT OR IGNORE INTO referrals (referrer_id, referred_id, status, created_at) VALUES (?, ?, 'pending', ?)", (valid_ref_id, user_id, now_str))

            await db.execute("""
                INSERT INTO users (user_id, username, full_name, preferred_quality, is_premium, daily_downloads, last_download_date, joined_at, referred_by, referral_count, coins, language)
                VALUES (?, ?, ?, '720p', 0, 0, ?, ?, ?, 0, 0, 'uz')
            """, (user_id, username, full_name, today_str, now_str, valid_ref_id))
            await db.commit()
            
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                user = await cursor.fetchone()
        else:
            if username != user['username'] or full_name != user['full_name']:
                await db.execute("UPDATE users SET username = ?, full_name = ? WHERE user_id = ?", (username, full_name, user_id))
                await db.commit()
                async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                    user = await cursor.fetchone()

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

        is_admin = is_user_admin(user_id)
        if is_admin:
            is_premium = 1
        pref_q = user['preferred_quality'] or '720p'
        if pref_q == 'best' and not (is_premium or is_admin):
            pref_q = '720p'
            await db.execute("UPDATE users SET preferred_quality = '720p' WHERE user_id = ?", (user_id,))
            await db.commit()

        user_dict = {
            "user_id": user['user_id'],
            "username": user['username'],
            "full_name": user['full_name'],
            "preferred_quality": pref_q,
            "is_premium": bool(is_premium or is_admin),
            "premium_until": "9999-12-31T23:59:59" if is_admin else user['premium_until'],
            "daily_downloads": 0 if is_admin else daily_downloads,
            "joined_at": user['joined_at'],
            "referred_by": user['referred_by'],
            "referral_count": user['referral_count'] or 0,
            "coins": user['coins'] or 0 if 'coins' in user.keys() else 0,
            "language": user['language'] or 'uz' if 'language' in user.keys() else 'uz'
        }
        return user_dict, is_new, referrer_got_bonus

async def get_or_create_user(user_id: int, username: str = None, full_name: str = None) -> dict:
    user_dict, _, _ = await register_user_with_referral(user_id, username, full_name, None)
    return user_dict

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
    if is_user_admin(user_id):
        return True, 0
    user = await get_or_create_user(user_id)
    if user['is_premium']:
        return True, user['daily_downloads']
    return user['daily_downloads'] < free_limit, user['daily_downloads']

async def grant_premium(user_id: int, days: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT is_premium, premium_until FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return False
        
        now = datetime.now()
        current_until = None
        if row['is_premium'] and row['premium_until']:
            try:
                current_until = datetime.fromisoformat(row['premium_until'])
            except Exception:
                current_until = None
        
        start_from = current_until if (current_until and current_until > now) else now
        until_dt = start_from + timedelta(days=days)
        until_str = until_dt.isoformat()
        
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
    total_users, premium_users, active_today, total_downloads, downloads_today = 0, 0, 0, 0, 0
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            try:
                async with db.execute("SELECT COUNT(*) FROM users") as c:
                    row = await c.fetchone()
                    if row: total_users = row[0]
            except Exception as e:
                logger.warning(f"Stats error users: {e}")
            try:
                async with db.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1") as c:
                    row = await c.fetchone()
                    if row: premium_users = row[0]
            except Exception as e:
                logger.warning(f"Stats error premium: {e}")
            try:
                async with db.execute("SELECT COUNT(*) FROM users WHERE last_download_date = ?", (today_str,)) as c:
                    row = await c.fetchone()
                    if row: active_today = row[0]
            except Exception as e:
                logger.warning(f"Stats error active: {e}")
            try:
                async with db.execute("SELECT COUNT(*) FROM downloads_history") as c:
                    row = await c.fetchone()
                    if row: total_downloads = row[0]
            except Exception as e:
                logger.warning(f"Stats error total_downloads: {e}")
            try:
                async with db.execute("SELECT COUNT(*) FROM downloads_history WHERE created_at LIKE ?", (f"{today_str}%",)) as c:
                    row = await c.fetchone()
                    if row: downloads_today = row[0]
            except Exception as e:
                logger.warning(f"Stats error downloads_today: {e}")
            total_coins, total_referrals = 0, 0
            try:
                async with db.execute("SELECT SUM(coins) FROM users") as c:
                    row = await c.fetchone()
                    if row and row[0]: total_coins = row[0]
            except Exception as e:
                logger.warning(f"Stats error total_coins: {e}")
            try:
                async with db.execute("SELECT COUNT(*) FROM referrals") as c:
                    row = await c.fetchone()
                    if row: total_referrals = row[0]
            except Exception as e:
                logger.warning(f"Stats error total_referrals: {e}")
    except Exception as e:
        logger.error(f"Error connecting for stats: {e}")

    return {
        "total_users": total_users,
        "premium_users": premium_users,
        "active_today": active_today,
        "total_downloads": total_downloads,
        "downloads_today": downloads_today,
        "total_coins": total_coins,
        "total_referrals": total_referrals
    }

async def get_all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

async def get_user_coins(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

async def add_user_coins(user_id: int, amount: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET coins = COALESCE(coins, 0) + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
        async with db.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

async def get_user_language(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT language FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 'uz'

async def set_user_language(user_id: int, language: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET language = ? WHERE user_id = ?", (language, user_id))
        await db.commit()

async def get_referral_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            total = row[0] if row else 0
        async with db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND status = 'active'", (user_id,)) as cur:
            row = await cur.fetchone()
            active = row[0] if row else 0
        async with db.execute("SELECT COALESCE(referral_count, 0) FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            legacy_count = row[0] if row else 0
        total = max(total, legacy_count)
    return {"total": total, "active": active, "earned_coins": active * 100}

async def verify_referral_activity(user_id: int) -> tuple[int, int]:
    """Called when user_id successfully downloads a file. Returns (referrer_id, coins_awarded) or (0, 0)"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, referrer_id FROM referrals WHERE referred_id = ? AND status = 'pending'", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return 0, 0
        ref_row_id = row[0]
        referrer_id = row[1]
        
        await db.execute("UPDATE referrals SET status = 'active' WHERE id = ?", (ref_row_id,))
        
        # Check active count this month for cap
        this_month = date.today().strftime("%Y-%m")
        async with db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND status = 'active' AND created_at LIKE ?", (referrer_id, f"{this_month}%")) as cur:
            cnt_row = await cur.fetchone()
            active_this_month = cnt_row[0] if cnt_row else 0
            
        coins_to_award = 100 if active_this_month <= 10 else 10
        await db.execute("UPDATE users SET coins = COALESCE(coins, 0) + ? WHERE user_id = ?", (coins_to_award, referrer_id))
        await db.commit()
        return referrer_id, coins_to_award

async def create_redeem_code(code: str, reward_type: str, reward_value: int, max_uses: int) -> bool:
    now_str = datetime.now().isoformat()
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO redeem_codes (code, reward_type, reward_value, max_uses, used_count, created_at) VALUES (?, ?, ?, ?, 0, ?)",
                             (code.upper(), reward_type, reward_value, max_uses, now_str))
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Error creating code: {e}")
        return False

async def redeem_code(user_id: int, code: str) -> tuple[bool, str, int]:
    now_str = datetime.now().isoformat()
    code_upper = code.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM redeem_codes WHERE code = ?", (code_upper,)) as cur:
            row = await cur.fetchone()
        if not row:
            return False, "NOT_FOUND", 0
        if row['used_count'] >= row['max_uses']:
            return False, "EXPIRED", 0
        
        async with db.execute("SELECT * FROM user_redeems WHERE user_id = ? AND code = ?", (user_id, code_upper)) as cur:
            used_row = await cur.fetchone()
        if used_row:
            return False, "ALREADY_USED", 0
            
        await db.execute("INSERT INTO user_redeems (user_id, code, redeemed_at) VALUES (?, ?, ?)", (user_id, code_upper, now_str))
        await db.execute("UPDATE redeem_codes SET used_count = used_count + 1 WHERE code = ?", (code_upper,))
        await db.commit()

        reward_type = str(row['reward_type']).lower()
        reward_value = row['reward_value']
        
        if reward_type == 'coins':
            async with aiosqlite.connect(DB_PATH) as db2:
                await db2.execute("UPDATE users SET coins = COALESCE(coins, 0) + ? WHERE user_id = ?", (reward_value, user_id))
                await db2.commit()
        elif reward_type in ['vip', 'days', 'premium', 'day']:
            await grant_premium(user_id, reward_value)
            
        return True, reward_type, reward_value

async def get_user_total_downloads(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM downloads_history WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
