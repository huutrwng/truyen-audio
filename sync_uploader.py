"""
Script dong bo audio len Cloud Storage voi Tien trinh truc quan & uu tien chuong dang nghe.
"""
import os
import sys
import time
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from huggingface_hub import HfApi

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("SyncUploader")

def load_hf_token() -> str:
    token = os.getenv("HF_TOKEN")
    if token:
        return token.strip()
    token_file = Path(__file__).parent / "hf_token.txt"
    if token_file.exists():
        try:
            return token_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return ""

HF_TOKEN = load_hf_token()
REPO_ID = os.getenv("HF_REPO_ID", "huutruong01/truyen-audio-storage")

def get_remote_files(api: HfApi):
    try:
        files = api.list_repo_files(repo_id=REPO_ID, repo_type="dataset")
        return set(f.replace("audio/", "") for f in files if f.startswith("audio/"))
    except Exception as e:
        logger.error(f"Khong the lay danh sach file tu repo: {e}")
        return set()

def upload_worker(api: HfApi, file_path: Path):
    fname = file_path.name
    sz_mb = file_path.stat().st_size / (1024 * 1024)
    t0 = time.time()
    for attempt in range(1, 4):
        try:
            api.upload_file(
                path_or_fileobj=str(file_path),
                path_in_repo=f"audio/{fname}",
                repo_id=REPO_ID,
                repo_type="dataset",
                commit_message=f"Upload {fname}"
            )
            elapsed = time.time() - t0
            return (True, fname, sz_mb, elapsed, "")
        except Exception as e:
            if attempt < 3:
                time.sleep(2 * attempt)
            else:
                return (False, fname, sz_mb, 0, str(e))

def main():
    api = HfApi(token=HF_TOKEN)
    base_dir = Path(__file__).parent
    audio_dir = base_dir / "audio"

    logger.info("Dang kiem tra danh sach file tren Hugging Face...")
    remote_files = get_remote_files(api)
    logger.info(f"Tren Cloud hien co: {len(remote_files)} file")

    local_files = sorted(list(audio_dir.glob("chapter_*.mp3")))
    needed = [f for f in local_files if f.name not in remote_files]
    logger.info(f"Local co {len(local_files)} file. Can upload: {len(needed)} file")

    if not needed:
        logger.info("Tat ca file audio da duoc dong bo day du len Cloud Storage!")
        return

    # Uu tien chuong 940 - 1000 len dau tien
    def sort_key(f: Path):
        num = int(''.join(filter(str.isdigit, f.stem)) or 0)
        # Chuong 940 - 1050 uu tien cao nhat (priority 0)
        if 940 <= num <= 1050:
            return (0, num)
        return (1, num)

    needed.sort(key=sort_key)

    total = len(needed)
    completed = 0
    success_count = 0
    failed_count = 0

    logger.info(f"Bat dau upload {total} file audio voi 3 luong dong thoi...")

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(upload_worker, api, f): f for f in needed}
        for future in as_completed(futures):
            completed += 1
            success, fname, sz_mb, elapsed, err = future.result()
            if success:
                success_count += 1
                logger.info(f"[{completed}/{total}] ✓ Da upload {fname} ({sz_mb:.1f}MB, {elapsed:.1f}s) -> CDN san sang!")
            else:
                failed_count += 1
                logger.error(f"[{completed}/{total}] ✗ Loi upload {fname}: {err}")

    logger.info(f"HOAN TAT DONG BO! Thanh cong: {success_count}/{total}, That bai: {failed_count}")

if __name__ == "__main__":
    main()
