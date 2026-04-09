FROM python:3.11-slim

# Swiss Ephemeris が必要とするビルドツール
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依存インストール（キャッシュ活用）
COPY tools/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# アプリコードのコピー
COPY tools/ ./tools/

WORKDIR /app/tools

# Swiss Ephemeris の天文暦データ（ネットから取得せず組込みを使用）
# pyswisseph は標準暦データを内包しているため追加設定不要

EXPOSE 8501

# $PORT が設定されている場合（Render/Railway）はそちらを使用、なければ8501
CMD uvicorn api:app --host 0.0.0.0 --port ${PORT:-8501}
