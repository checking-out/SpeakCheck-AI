FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 시스템 패키지 (필요하면 추가)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스 복사
COPY . .

# 컨테이너에서 열 포트 (FastAPI 기준)
ENV PORT=8000

# 여기서 실제 엔트리포인트 맞춰줘
# 예시 1) main.py 안에 app 이 있는 FastAPI:
# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
#
# 예시 2) app/main.py 구조라면:
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
