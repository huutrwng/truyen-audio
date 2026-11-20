"""
Module quan ly dong bo va stream audio tu Cloud Storage (Hugging Face Dataset CDN).
Mien phi 50GB storage, CDN toan cau, ho tro HTTP 206 Partial Content (Range request) cho phep tua audio tren mobile.
"""
import os
import logging
from pathlib import Path
from typing import Optional
from huggingface_hub import HfApi

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
