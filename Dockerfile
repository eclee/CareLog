FROM python:3.12-slim

# 台灣時區：排程報表與提醒的時間判斷依此時區
ENV TZ=Asia/Taipei \
    PYTHONUNBUFFERED=1 \
    CARELOG_DATA=/data

# tzdata：slim 基底不保證內建，缺少時 TZ 會退回 UTC，排程將在錯誤時間觸發
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先裝依賴（利用 Docker layer cache，改程式碼不必重裝套件）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製程式碼
COPY . .

# 資料 volume：SQLite 資料庫 + 上傳照片
VOLUME ["/data"]

EXPOSE 8501

# Container Manager 會據此顯示「健康狀態」，服務掛掉時一目瞭然
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8501/login', timeout=4)"

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]
