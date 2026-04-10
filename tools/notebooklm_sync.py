#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KP Jyotish → NotebookLM 連携スクリプト

使い方:
    # 1. 初回ログイン（ブラウザが開くのでGoogleアカウントでログイン）
    python notebooklm_sync.py login

    # 2. 自分のチャートをNotebookLMに送る
    python notebooklm_sync.py sync

    # 3. 誕生データを指定してノートブックを作る
    python notebooklm_sync.py sync --year 2000 --month 5 --day 8 --hour 15 --minute 46 --tz 9

    # 4. 既存ノートブックに追記する（IDを指定）
    python notebooklm_sync.py sync --notebook-id <ID>
"""

from __future__ import annotations
import argparse
import asyncio
import datetime
import subprocess
import sys
import urllib.request
import json
from pathlib import Path

# ───────────────────────────────────────────
# デフォルト出生データ（幹太）
# ───────────────────────────────────────────
DEFAULT = dict(year=2000, month=5, day=8, hour=15, minute=46,
               tz=9.0, lat=34.6617, lon=133.9350)

# Render にデプロイ済みのAPIサーバー
API_BASE = "https://jyotish-hawn.onrender.com"

REPO_ROOT = Path(__file__).parent.parent
KNOWLEDGE_FILES = sorted([
    *REPO_ROOT.glob("00_introduction/*.md"),
    *REPO_ROOT.glob("01_foundations/*.md"),
    *REPO_ROOT.glob("02_chart-basics/*.md"),
    *REPO_ROOT.glob("03_intermediate/*.md"),
    *REPO_ROOT.glob("04_kp-system/*.md"),
    REPO_ROOT / "glossary.md",
])


# ───────────────────────────────────────────
# login コマンド
# ───────────────────────────────────────────
def cmd_login():
    """ブラウザでGoogleログインして認証情報を保存"""
    print("ブラウザが開きます。Googleアカウントでログインしてください...")
    result = subprocess.run(
        [sys.executable, "-m", "notebooklm", "login"],
        check=False
    )
    if result.returncode == 0:
        print("ログイン成功。notebooklm_sync.py sync を実行できます。")
    else:
        print("ログインに失敗しました。")
        sys.exit(1)


# ───────────────────────────────────────────
# sync コマンド
# ───────────────────────────────────────────
async def cmd_sync(args):
    try:
        import notebooklm
    except ImportError:
        print("notebooklm-py をインストールしてください: pip install notebooklm-py")
        sys.exit(1)

    # ── KPレポートをAPIから取得 ──────────────
    bd = dict(
        year=args.year, month=args.month, day=args.day,
        hour=args.hour, minute=args.minute, tz=args.tz,
        lat=args.lat, lon=args.lon
    )
    print(f"KPレポート取得中: {bd['year']}-{bd['month']:02d}-{bd['day']:02d} "
          f"{bd['hour']:02d}:{bd['minute']:02d} UTC+{bd['tz']}")
    print(f"  APIサーバー: {API_BASE}")
    print("  (初回は起動に30秒かかる場合があります...)")

    payload = json.dumps(bd).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/api/report",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        report_text = data["text"]
    except Exception as e:
        print(f"APIエラー: {e}")
        print("Renderサーバーが停止している可能性があります。")
        print(f"{API_BASE}/ をブラウザで開いてサーバーを起動してから再実行してください。")
        sys.exit(1)
    print(f"レポート取得完了 ({len(report_text)} 文字)")

    # ── NotebookLM 接続 ─────────────────────
    print("NotebookLMに接続中...")
    try:
        auth = await notebooklm.AuthTokens.from_storage()
    except Exception as e:
        print(f"認証エラー: {e}")
        print("先に: python3 notebooklm_sync.py login を実行してください")
        sys.exit(1)

    async with notebooklm.NotebookLMClient(auth) as client:

        # ── ノートブック作成 or 取得 ─────────
        if args.notebook_id:
            notebooks = await client.notebooks.list()
            nb = next((n for n in notebooks if args.notebook_id in n.id), None)
            if not nb:
                print(f"ノートブックID '{args.notebook_id}' が見つかりません")
                sys.exit(1)
            print(f"既存ノートブックを使用: {nb.title}")
        else:
            date_str = f"{bd['year']}-{bd['month']:02d}-{bd['day']:02d}"
            nb_title = f"KP チャート {date_str} {bd['hour']:02d}:{bd['minute']:02d}"
            print(f"ノートブック作成中: '{nb_title}'")
            nb = await client.notebooks.create(nb_title)
            print(f"作成完了 (ID: {nb.id})")

        # ── KPレポートをソースとして追加 ────
        print("KPレポートを追加中...")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        source_text = (
            f"# KP占星術チャート分析レポート\n"
            f"生成日時: {now_str}\n\n"
            f"{report_text}"
        )
        await client.sources.add_text(
            nb.id,
            text=source_text,
            title=f"KPレポート {date_str}",
        )
        print("KPレポート追加完了")

        # ── KP知識ベースを追加 ──────────────
        if not args.no_knowledge and KNOWLEDGE_FILES:
            print(f"KP知識ベース ({len(KNOWLEDGE_FILES)} ファイル) を追加中...")
            # 全ファイルを1つのテキストに結合（ソース数節約）
            combined = []
            for f in KNOWLEDGE_FILES:
                content = f.read_text(encoding="utf-8")
                combined.append(f"# {f.stem}\n\n{content}")
            knowledge_text = "\n\n---\n\n".join(combined)
            await client.sources.add_text(
                nb.id,
                text=knowledge_text,
                title="KP占星術 知識ベース",
            )
            print("知識ベース追加完了")

        # ── 完了メッセージ ───────────────────
        print()
        print("=" * 50)
        print("NotebookLM 連携完了")
        print(f"ノートブック: {nb.title}")
        print(f"ID: {nb.id}")
        print()
        print("NotebookLMを開いてチャートについて質問できます。")
        print("例: 「このチャートの8室に惑星が集中している意味は？」")
        print("    「現在のSa/SuダシャーはどんなテーマをもたらしますかX」")
        print("=" * 50)


# ───────────────────────────────────────────
# CLI
# ───────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="KP Jyotish → NotebookLM 連携",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    # login
    sub.add_parser("login", help="Googleアカウントでログイン（初回のみ）")

    # sync
    sp = sub.add_parser("sync", help="チャートをNotebookLMに送る")
    sp.add_argument("--year",   type=int,   default=DEFAULT["year"])
    sp.add_argument("--month",  type=int,   default=DEFAULT["month"])
    sp.add_argument("--day",    type=int,   default=DEFAULT["day"])
    sp.add_argument("--hour",   type=int,   default=DEFAULT["hour"])
    sp.add_argument("--minute", type=int,   default=DEFAULT["minute"])
    sp.add_argument("--tz",     type=float, default=DEFAULT["tz"])
    sp.add_argument("--lat",    type=float, default=DEFAULT["lat"])
    sp.add_argument("--lon",    type=float, default=DEFAULT["lon"])
    sp.add_argument("--notebook-id", default=None, help="既存ノートブックIDを指定")
    sp.add_argument("--no-knowledge", action="store_true",
                    help="KP知識ベースを追加しない")

    args = parser.parse_args()

    if args.command == "login":
        cmd_login()
    elif args.command == "sync":
        asyncio.run(cmd_sync(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
