#!/bin/bash
# KP占星術計算ツール 起動スクリプト
cd "$(dirname "$0")"
pip3 install -q pyswisseph tabulate streamlit 2>/dev/null
echo "ブラウザで開いています..."
streamlit run app.py
