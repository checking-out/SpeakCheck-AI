from pathlib import Path
from PIL import Image
import pytesseract

for name in ("image 9.png", "image 10.png"):
    path = Path(name)  # 현재 디렉터리 기준
    if not path.exists():
        print(f"{path} 파일이 없습니다.")
        continue
    text = pytesseract.image_to_string(Image.open(path), lang="kor+eng")
    print(f"=== {name} ===")
    print(text.strip(), "\n")
