FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e .
ENTRYPOINT ["python", "-m", "bodhan_lesson"]
