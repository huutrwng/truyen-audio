"""
Script tu dong phan tich noi dung va tao tieu de da dang, chuan phong cach tien hiep cho cac chuong 1739 - 2045.
Format: Chuong {num} : {Ve 1}, {Ve 2}!
"""
import sqlite3
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "chapters.db"

THEMES = [
    ("hộ sơn đại trận", "Hộ sơn đại trận"),
    ("đại trận", "Khởi động đại trận"),
    ("luyện hư", "Luyện Hư chi uy"),
    ("hóa thần", "Hóa Thần xuất thế"),
    ("nguyên anh", "Nguyên Anh tụ hội"),
    ("lôi kiếp", "Thiên lôi cuồn cuộn"),
    ("pháp tắc", "Pháp tắc dao động"),
    ("bạch vân môn", "Bạch Vân môn nội"),
    ("tiên minh", "Tiên Minh bố cục"),
    ("ngụy chân quân", "Ngụy chân quân"),
    ("trình trường thanh", "Trình Trường Thanh"),
    ("trình bất tranh", "Trình Bất Tranh"),
    ("mộ dung", "Mộ Dung Oản Oản"),
    ("tĩnh thất", "Tĩnh thất bế quan"),
    ("chúc mừng", "Tới cửa chúc mừng"),
    ("giao dịch", "Giao dịch bí mật"),
    ("linh vật", "Kỳ trân dị bảo"),
    ("kho báu", "Mở ra kho báu"),
    ("truy sát", "Quyết liệt truy sát"),
    ("vẫn lạc", "Cường giả vẫn lạc"),
    ("chém giết", "Quyết chiến sinh tử"),
    ("trấn sát", "Lôi đình trấn sát"),
    ("thôi diễn", "Huyền diệu thôi diễn"),
    ("thần thông", "Thần thông hiển uy"),
    ("thăm dò", "Thăm dò hư thực"),
    ("ngầm", "Âm thầm bố cục"),
    ("rút lui", "Thối lui bảo toàn"),
    ("hiện thân", "Cường giả hiện thân"),
    ("đáy biển", "Thâm hải dị động"),
    ("cấm địa", "Bước vào cấm địa"),
    ("yêu tôn", "Yêu tôn giáng lâm"),
    ("tộc trưởng", "Tộc trưởng đăng vị"),
    ("lánh đời", "Kế hoạch lánh đời"),
    ("thương nghị", "Mật nghị đại sự"),
    ("phản phệ", "Pháp tắc phản phệ"),
    ("hư không", "Hư không chấn động"),
    ("dị tượng", "Trời sinh dị tượng"),
    ("linh đan", "Luyện chế linh đan"),
    ("khí tức", "Khí tức kinh người"),
    ("đạo đồ", "Đạo đồ gian nan"),
    ("huyết mạch", "Huyết mạch thức tỉnh"),
]

SECOND_CLAUSES = [
    "sóng ngầm mãnh liệt",
    "kinh động tứ phương",
    "phong vân biến ảo",
    "các phe giao phong",
    "thật giả khó lường",
    "hung hiểm vạn phần",
    "khí thế ngập trời",
    "tâm tư khó dò",
    "chấn động càn khôn",
    "chờ thời cơ động",
    "nghịch chuyển tình thế",
    "kinh tâm động phách",
    "chấn kinh tứ tọa",
    "bão táp sắp tới",
    "tìm kiếm cơ duyên",
    "sát cơ tiềm tàng",
    "thần uy hiển hách",
    "ung dung ứng đối",
    "toan tính thâm sâu",
    "dị biến liên tục",
    "trời đất đổi màu",
    "quyết định đại cục",
]

def analyze_chapter(content: str, num: int, used_titles: set) -> str:
    # 1. Kiem tra tieu de goc co san
    first_lines = content[:250].split('\n')
    for line in first_lines[:3]:
        line = line.strip(' "“\'')
        m = re.match(r'^(?:chương|hồi)\s+\d+\s*[:\-]\s*(.+)$', line, re.IGNORECASE)
        if m:
            sub = m.group(1).strip()
            if len(sub) > 3 and not sub.isdigit() and "suy sụp" not in sub:
                sub = re.sub(r'^[,\-:\s]+', '', sub)
                t = f"Chương {num} : {sub}"
                if not t.endswith(('!', '?')): t += "!"
                return t

    content_lower = content.lower()
    matches = []
    for kw, label in THEMES:
        count = content_lower.count(kw)
        if count > 0:
            first_idx = content_lower.find(kw)
            matches.append((count, first_idx, label))

    matches.sort(key=lambda x: (-x[0], x[1]))

    v1 = matches[0][2] if matches else "Phong vân biến ảo"
    
    # Chon ve 2 da dang theo chuong de khong bi trung lap lien tiep
    v2_idx = (num * 7 + len(content)) % len(SECOND_CLAUSES)
    v2 = SECOND_CLAUSES[v2_idx]
    
    title = f"Chương {num} : {v1}, {v2}!"
    if title in used_titles:
        v2 = SECOND_CLAUSES[(v2_idx + 1) % len(SECOND_CLAUSES)]
        title = f"Chương {num} : {v1}, {v2}!"

    used_titles.add(title)
    return title

def main():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT num, content FROM chapters WHERE num >= 1739 ORDER BY num")
    rows = c.fetchall()

    used = set()
    updated = []
    for num, content in rows:
        title = analyze_chapter(content, num, used)
        c.execute("UPDATE chapters SET title = ? WHERE num = ?", (title, num))
        updated.append((num, title))

    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn.close()

    print(f"✓ Đã cập nhật tiêu đề phong phú cho {len(updated)} chương:")
    for num, t in updated[:12]:
        print(f"  {t}")
    print("  ...")
    for num, t in updated[-5:]:
        print(f"  {t}")

if __name__ == "__main__":
    main()
