"""
Module quan ly dong bo va stream audio tu Cloud Storage (Hugging Face Dataset CDN).
Mien phi 50GB storage, CDN toan cau, ho tro HTTP 206 Partial Content (Range request) cho phep tua audio tren mobile.
"""
import os
import logging
from pathlib import Path
from typing import Optional, List
import aiohttp
from huggingface_hub import HfApi, CommitOperationAdd

logger = logging.getLogger(__name__)

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
CDN_BASE_URL = f"https://huggingface.co/datasets/{REPO_ID}/resolve/main/audio"

def get_cloud_audio_url(filename: str) -> str:
    """Tra ve URL public truc tiep de stream audio tu CDN."""
    return f"{CDN_BASE_URL}/{filename}"

async def download_cloud_audio(filename: str, target_path: Path) -> bool:
    """Tải file audio từ Cloud Storage về cache cục bộ của server."""
    cloud_url = get_cloud_audio_url(filename)
    tmp_path = target_path.with_suffix(".tmp")
    try:
        timeout = aiohttp.ClientTimeout(total=45)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(cloud_url) as resp:
                if resp.status != 200:
                    logger.warning(f"Cloud Storage trả về status {resp.status} cho {filename}")
                    return False
                
                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                
                if tmp_path.exists() and tmp_path.stat().st_size > 1000:
                    tmp_path.replace(target_path)
                    logger.info(f"✓ Đã tải {filename} từ Cloud về cache server ({target_path.stat().st_size // 1024} KB)")
                    return True
                return False
    except Exception as e:
        logger.error(f"Lỗi tải audio {filename} từ Cloud: {e}")
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        return False

def upload_single_audio(local_file_path: Path, filename: Optional[str] = None) -> bool:
    """Upload mot file mp3 don le len cloud storage."""
    if not local_file_path.exists():
        logger.error(f"File khong ton tai: {local_file_path}")
        return False
    
    fname = filename or local_file_path.name
    try:
        api = HfApi(token=HF_TOKEN)
        api.upload_file(
            path_or_fileobj=str(local_file_path),
            path_in_repo=f"audio/{fname}",
            repo_id=REPO_ID,
            repo_type="dataset",
            commit_message=f"Add audio {fname}"
        )
        logger.info(f"✓ Da upload {fname} len Cloud Storage ({CDN_BASE_URL}/{fname})")
        return True
    except Exception as e:
        logger.error(f"✗ Loi upload {fname} len Cloud Storage: {e}")
        return False

def upload_batch_audio(file_paths: List[Path]) -> bool:
    """Upload nhieu file audio cung luc trong 1 commit duy nhat de tiet kiem rate limit."""
    valid_files = [f for f in file_paths if f.exists()]
    if not valid_files:
        return True
    try:
        api = HfApi(token=HF_TOKEN)
        operations = [
            CommitOperationAdd(
                path_in_repo=f"audio/{f.name}",
                path_or_fileobj=str(f)
            )
            for f in valid_files
        ]
        api.create_commit(
            repo_id=REPO_ID,
            repo_type="dataset",
            operations=operations,
            commit_message=f"Batch upload {len(operations)} audio chapters"
        )
        logger.info(f"✓ Da batch upload thanh cong {len(operations)} chuong vao 1 commit duy nhat!")
        return True
    except Exception as e:
        logger.warning(f"Loi batch upload: {e}")
        return False

def sync_all_audio(audio_dir: Path) -> bool:
    """Dong bo toan bo thu muc audio len Cloud Storage bang upload_folder."""
    try:
        api = HfApi(token=HF_TOKEN)
        logger.info(f"Bat dau dong bo toan bo audio tu {audio_dir} len {REPO_ID}...")
        api.upload_folder(
            folder_path=str(audio_dir),
            path_in_repo="audio",
            repo_id=REPO_ID,
            repo_type="dataset",
            allow_patterns=["chapter_*.mp3"],
            commit_message="Sync all chapter MP3s to cloud storage"
        )
        logger.info("✓ Hoan tat dong bo audio len Cloud Storage!")
        return True
    except Exception as e:
        logger.error(f"✗ Loi dong bo folder audio: {e}")
        return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    base_dir = Path(__file__).parent
    audio_path = base_dir / "audio"
    sync_all_audio(audio_path)
