"""
FastAPI Server chính
Truyện Audio Server - Tu Tiên: Khai Cục Từ Dược Đồng Bắt Đầu
"""
import asyncio
import logging
import os
import sys
import io
import json
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database as db
import scraper
import tts_converter

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "audio"
STATIC_DIR = BASE_DIR / "static"
AUDIO_DIR.mkdir(exist_ok=True)

# ─── Conversion Queue ─────────────────────────────────────────────────────────
conversion_queue: asyncio.Queue = asyncio.Queue()
is_converter_running = False
current_converting: Optional[int] = None

async def conversion_worker():
    """Background worker để convert TTS hàng đợi."""
    global is_converter_running, current_converting
    is_converter_running = True
    logger.info("Conversion worker started")

    while True:
        try:
            task = await conversion_queue.get()
            if task is None:
                break

            chapter_num = task['num']
            voice = task.get('voice', tts_converter.DEFAULT_VOICE)
            current_converting = chapter_num

            logger.info(f"Converting chapter {chapter_num}...")
            await db.update_audio_status(chapter_num, 'converting')

            # Get chapter data
            chapter = await db.get_chapter(chapter_num)
            if not chapter:
                logger.error(f"Chapter {chapter_num} not found in DB")
                conversion_queue.task_done()
                current_converting = None
                continue

            # Fetch content if not cached
            content = chapter.get('content')
            if not content:
                logger.info(f"Fetching content for chapter {chapter_num}...")
                chapter_data = await scraper.get_chapter_content(chapter['url'])
                if not chapter_data or not chapter_data.get('content'):
                    logger.error(f"Failed to fetch content for chapter {chapter_num}")
                    await db.update_audio_status(chapter_num, 'error')
                    conversion_queue.task_done()
                    current_converting = None
                    continue
                content = chapter_data['content']
                await db.update_chapter_content(chapter_num, content, chapter_data.get('word_count', 0))

            # TTS Convert
            audio_filename = f"chapter_{chapter_num:04d}.mp3"
            audio_path = str(AUDIO_DIR / audio_filename)

            title = chapter.get('title', f'Chương {chapter_num}')
            success = await tts_converter.convert_chapter_to_audio(
                content, audio_path, voice=voice, title=title
            )

            if success and os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                await db.update_audio_status(chapter_num, 'done', f"audio/{audio_filename}", voice)
                logger.info(f"✓ Chapter {chapter_num} converted successfully ({os.path.getsize(audio_path)//1024}KB)")
            else:
                await db.update_audio_status(chapter_num, 'error')
                logger.error(f"✗ Chapter {chapter_num} conversion failed")

            conversion_queue.task_done()
            current_converting = None

            # Rate limit - tránh spam edge-tts
            await asyncio.sleep(1)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
            if current_converting:
                await db.update_audio_status(current_converting, 'error')
            current_converting = None
            try:
                conversion_queue.task_done()
            except Exception:
                pass

    is_converter_running = False
    logger.info("Conversion worker stopped")

# ─── App Lifespan ─────────────────────────────────────────────────────────────
worker_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global worker_task
    # Startup
    await db.init_db()
    logger.info("Database initialized")

    # Start background worker
    worker_task = asyncio.create_task(conversion_worker())
    logger.info("🚀 Truyen Audio Server started!")
    logger.info(f"   Static: {STATIC_DIR}")
    logger.info(f"   Audio:  {AUDIO_DIR}")

    yield

    # Shutdown
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    await scraper.close()
    logger.info("Server stopped")

# ─── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Truyen Audio Server",
    description="Server phát truyện audio Tu Tiên: Khai Cục Từ Dược Đồng Bắt Đầu",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Static Files ─────────────────────────────────────────────────────────────
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ─── Models ───────────────────────────────────────────────────────────────────
class ConvertRequest(BaseModel):
    voice: str = "vi-VN-HoaiMyNeural"

class ConvertRangeRequest(BaseModel):
    start: int
    end: int
    voice: str = "vi-VN-HoaiMyNeural"

class PlaybackStateRequest(BaseModel):
    chapter_num: int
    seek_seconds: float = 0.0
    duration: float = 0.0
    playback_rate: float = 1.0

# ─── API Routes ───────────────────────────────────────────────────────────────
@app.get("/")
async def serve_index():
    return FileResponse(str(STATIC_DIR / "index.html"))

@app.get("/api/status")
async def get_server_status():
    stats = await db.get_stats()
    return {
        "status": "running",
        "stats": stats,
        "queue_size": conversion_queue.qsize(),
        "currently_converting": current_converting,
        "novel": {
            "title": "Tu Tiên: Khai Cục Từ Dược Đồng Bắt Đầu",
            "url": scraper.NOVEL_URL,
        }
    }

@app.get("/api/remote-info")
async def get_remote_info():
    """Thông tin kết nối 4G từ xa và mạng LAN."""
    public_url = ""
    pub_file = BASE_DIR / "public_url.txt"
    if pub_file.exists():
        try:
            public_url = pub_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    import socket
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "127.0.0.1"
    return {
        "status": "online",
        "public_url": public_url,
        "local_url": f"http://{local_ip}:8899",
        "local_ip": local_ip,
        "port": 8899
    }

@app.get("/api/playback-state")
async def get_playback_state():
    """Lấy state vị trí chương và thời gian nghe gần nhất."""
    state = await db.get_playback_state()
    return {"status": "ok", "state": state}

@app.post("/api/playback-state")
async def save_playback_state(req: PlaybackStateRequest):
    """Lưu state vị trí chương và thời gian nghe (tự động mỗi 15p hoặc khi dừng)."""
    await db.save_playback_state(
        chapter_num=req.chapter_num,
        seek_seconds=req.seek_seconds,
        duration=req.duration,
        playback_rate=req.playback_rate
    )
    return {"status": "ok", "saved": req.model_dump() if hasattr(req, "model_dump") else req.dict()}

@app.get("/api/chapters")
async def list_chapters(limit: int = 100, offset: int = 0):
    chapters = await db.get_all_chapters(limit=limit, offset=offset)
    total = (await db.get_stats())['total']
    return {
        "chapters": chapters,
        "total": total,
        "limit": limit,
        "offset": offset
    }

@app.get("/api/chapter/{num}")
async def get_chapter(num: int):
    chapter = await db.get_chapter(num)
    if not chapter:
        raise HTTPException(status_code=404, detail=f"Chapter {num} not found")
    # Don't return full content in API (can be large)
    chapter_summary = {k: v for k, v in chapter.items() if k != 'content'}
    return chapter_summary

@app.get("/api/chapter/{num}/content")
async def get_chapter_content(num: int):
    chapter = await db.get_chapter(num)
    if not chapter:
        raise HTTPException(status_code=404, detail=f"Chapter {num} not found")
    return {
        "num": chapter['num'],
        "title": chapter['title'],
        "content": chapter.get('content', ''),
        "word_count": chapter.get('word_count', 0),
    }

@app.post("/api/sync-chapters")
async def sync_chapters():
    """Đồng bộ danh sách chương từ website."""
    logger.info("Syncing chapter list...")
    chapters = await scraper.get_chapter_list()
    if not chapters:
        raise HTTPException(status_code=503, detail="Không thể lấy danh sách chương từ website")

    await db.upsert_chapters_bulk(chapters)
    return {"synced": len(chapters), "message": f"Đã đồng bộ {len(chapters)} chương"}

@app.post("/api/convert/{num}")
async def convert_chapter(num: int, req: ConvertRequest):
    """Queue một chương để convert TTS."""
    chapter = await db.get_chapter(num)
    if not chapter:
        raise HTTPException(status_code=404, detail=f"Chapter {num} not found. Hãy sync trước.")

    # Check if already done
    if chapter.get('audio_status') == 'done':
        return {"message": f"Chương {num} đã có audio", "status": "done"}

    # Check if already queued
    if chapter.get('audio_status') in ('queued', 'converting'):
        return {"message": f"Chương {num} đang trong hàng đợi", "status": chapter['audio_status']}

    # Queue it
    await db.update_audio_status(num, 'queued')
    await conversion_queue.put({'num': num, 'voice': req.voice})

    return {
        "message": f"Chương {num} đã được thêm vào hàng đợi",
        "status": "queued",
        "queue_size": conversion_queue.qsize()
    }

@app.post("/api/convert-range")
async def convert_range(req: ConvertRangeRequest):
    """Queue nhiều chương liên tiếp để convert TTS."""
    if req.end < req.start or req.end - req.start > 50:
        raise HTTPException(status_code=400, detail="Tối đa 50 chương mỗi lần, start phải <= end")

    queued_nums = []
    skipped = []

    for num in range(req.start, req.end + 1):
        chapter = await db.get_chapter(num)
        if not chapter:
            skipped.append(num)
            continue
        if chapter.get('audio_status') in ('done', 'queued', 'converting'):
            skipped.append(num)
            continue
        await db.update_audio_status(num, 'queued')
        await conversion_queue.put({'num': num, 'voice': req.voice})
        queued_nums.append(num)

    return {
        "queued": queued_nums,
        "skipped": skipped,
        "queue_size": conversion_queue.qsize()
    }

@app.delete("/api/audio/{num}")
async def delete_audio(num: int):
    """Xóa file audio của một chương (để convert lại)."""
    chapter = await db.get_chapter(num)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    audio_path = chapter.get('audio_path')
    if audio_path:
        full_path = BASE_DIR / audio_path
        if full_path.exists():
            full_path.unlink()

    await db.update_audio_status(num, 'none', '', None)
    return {"message": f"Đã xóa audio chương {num}"}

@app.get("/api/voices")
async def get_voices():
    voices = await tts_converter.get_available_voices()
    return {"voices": voices, "presets": tts_converter.VOICES}

@app.get("/api/queue")
async def get_queue_status():
    queued = await db.get_chapters_by_status('queued')
    converting = await db.get_chapters_by_status('converting')
    return {
        "queue_size": conversion_queue.qsize(),
        "currently_converting": current_converting,
        "queued_chapters": [c['num'] for c in queued],
        "converting_chapters": [c['num'] for c in converting],
    }

if __name__ == "__main__":
    import uvicorn
    import socket

    # Get local IP
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    print("=" * 60)
    print("🎧 TRUYEN AUDIO SERVER")
    print("=" * 60)
    print(f"   Local:   http://localhost:8899")
    print(f"   Network: http://{local_ip}:8899")
    print(f"   (Dùng ngrok / Cloudflare Tunnel để truy cập từ xa)")
    print("=" * 60)
    
    port = int(os.getenv("PORT", 8899))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
