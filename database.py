"""
Database layer - SQLite để lưu metadata chương và trạng thái audio
"""
import aiosqlite
import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'chapters.db')

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY,
    num INTEGER UNIQUE NOT NULL,
    title TEXT,
    url TEXT,
    slug TEXT,
    content TEXT,
    audio_path TEXT,
    audio_status TEXT DEFAULT 'none',
    voice TEXT DEFAULT 'vi-VN-HoaiMyNeural',
    word_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_num ON chapters(num);
CREATE INDEX IF NOT EXISTS idx_status ON chapters(audio_status);

CREATE TABLE IF NOT EXISTS playback_state (
    id INTEGER PRIMARY KEY,
    chapter_num INTEGER NOT NULL,
    seek_seconds REAL DEFAULT 0.0,
    duration REAL DEFAULT 0.0,
    playback_rate REAL DEFAULT 1.0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

# audio_status values: none | queued | converting | done | error

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLE_SQL)
        await db.commit()
    logger.info(f"Database initialized: {DB_PATH}")

async def upsert_chapter(num: int, title: str, url: str, slug: str = ''):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO chapters (num, title, url, slug)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(num) DO UPDATE SET
                title=excluded.title,
                url=excluded.url,
                slug=excluded.slug,
                updated_at=CURRENT_TIMESTAMP
        """, (num, title, url, slug))
        await db.commit()

async def upsert_chapters_bulk(chapters: list[dict]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany("""
            INSERT INTO chapters (num, title, url, slug)
            VALUES (:num, :title, :url, :slug)
            ON CONFLICT(num) DO UPDATE SET
                title=excluded.title,
                url=excluded.url,
                slug=excluded.slug,
                updated_at=CURRENT_TIMESTAMP
        """, chapters)
        await db.commit()
    logger.info(f"Upserted {len(chapters)} chapters")

async def get_chapter(num: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM chapters WHERE num=?", (num,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_all_chapters(limit: int = 2000, offset: int = 0) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT num, title, url, audio_status, audio_path, word_count FROM chapters ORDER BY num LIMIT ? OFFSET ?",
            (limit, offset)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def update_chapter_content(num: int, content: str, word_count: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE chapters SET content=?, word_count=?, updated_at=CURRENT_TIMESTAMP
            WHERE num=?
        """, (content, word_count, num))
        await db.commit()

async def update_audio_status(num: int, status: str, audio_path: str = None, voice: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if audio_path:
            await db.execute("""
                UPDATE chapters SET audio_status=?, audio_path=?, voice=?, updated_at=CURRENT_TIMESTAMP
                WHERE num=?
            """, (status, audio_path, voice or 'vi-VN-HoaiMyNeural', num))
        else:
            await db.execute("""
                UPDATE chapters SET audio_status=?, updated_at=CURRENT_TIMESTAMP
                WHERE num=?
            """, (status, num))
        await db.commit()

async def get_chapters_by_status(status: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT num, title, url, audio_status FROM chapters WHERE audio_status=? ORDER BY num",
            (status,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM chapters") as c:
            total = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM chapters WHERE audio_status='done'") as c:
            done = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM chapters WHERE audio_status='queued'") as c:
            queued = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM chapters WHERE audio_status='converting'") as c:
            converting = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM chapters WHERE audio_status='error'") as c:
            error = (await c.fetchone())[0]
    return {
        'total': total,
        'done': done,
        'queued': queued,
        'converting': converting,
        'error': error,
        'none': total - done - queued - converting - error
    }

async def save_playback_state(chapter_num: int, seek_seconds: float, duration: float, playback_rate: float = 1.0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO playback_state (id, chapter_num, seek_seconds, duration, playback_rate, updated_at)
            VALUES (1, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                chapter_num=excluded.chapter_num,
                seek_seconds=excluded.seek_seconds,
                duration=excluded.duration,
                playback_rate=excluded.playback_rate,
                updated_at=CURRENT_TIMESTAMP
        """, (chapter_num, seek_seconds, duration, playback_rate))
        await db.commit()

async def get_playback_state() -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT chapter_num, seek_seconds, duration, playback_rate, updated_at FROM playback_state WHERE id=1") as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
