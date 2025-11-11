# ===== BASE =====
FROM python:3.11-slim

# 시스템 기본 세팅
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 복사
COPY . .

# 실행 명령 (예: FastAPI uvicorn 기준)
CMD ["python", "main.py"]
