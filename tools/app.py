#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KP (Krishnamurti Paddhati) Jyotish Astrology - Streamlit Web App
KP (クリシュナムルティ・パッダティ) ジョーティシュ占星術 Web アプリ

Imports core calculation functions from kp_calculator.py
"""

import sys
import os
import datetime

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Path setup - import from kp_calculator.py in the same directory
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import swisseph as swe

from kp_calculator import (
    # Constants
    PLANET_ORDER, PLANET_JA, SIGNS_JA, SIGNS_EN, SIGN_LORD,
    NAKSHATRAS, NAK_LORD_ORDER, DASHA_YEARS, WEEKDAY_JA, WEEKDAY_LORD,
    # Helper functions
    deg_to_dms, deg_to_sign, get_nakshatra_info, get_sub_lords,
    # Core calculation functions
    build_sub_lord_table,
    birth_to_jd,
    calc_planet_positions,
    calc_placidus_cusps,
    assign_houses_to_planets,
    calc_vimshottari_dasha,
    calc_significators,
    calc_ruling_planets,
    jd_to_date_str,
    planet_display,
    calc_condition_timeline,
)

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="KP占星術計算",
    page_icon="🪐",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Planet color palette (for styling)
# ---------------------------------------------------------------------------
PLANET_COLORS = {
    'Su': '#FFD700',   # Sun - gold/yellow
    'Mo': '#C0C0C0',   # Moon - silver
    'Ma': '#FF4444',   # Mars - red
    'Me': '#00CC66',   # Mercury - green
    'Ju': '#FF8C00',   # Jupiter - orange
    'Ve': '#FF69B4',   # Venus - pink
    'Sa': '#6B8E9F',   # Saturn - blue-grey
    'Ra': '#9370DB',   # Rahu - purple
    'Ke': '#8B4513',   # Ketu - brown
}

PLANET_TEXT_COLORS = {
    'Su': '#000000',
    'Mo': '#000000',
    'Ma': '#FFFFFF',
    'Me': '#000000',
    'Ju': '#000000',
    'Ve': '#000000',
    'Sa': '#FFFFFF',
    'Ra': '#FFFFFF',
    'Ke': '#FFFFFF',
}

# ---------------------------------------------------------------------------
# Helper: format DMS string
# ---------------------------------------------------------------------------
def fmt_dms(d: int, m: int, s: int) -> str:
    return f"{d:02d}°{m:02d}′{s:02d}″"


def fmt_planet_label(abbr: str) -> str:
    return f"{abbr}（{PLANET_JA[abbr]}）"


# ---------------------------------------------------------------------------
# Sidebar – birth data input form
# ---------------------------------------------------------------------------
def sidebar_inputs():
    st.sidebar.header("🪐 出生データ入力")
    st.sidebar.markdown("---")

    year = st.sidebar.number_input(
        "生年（西暦）",
        min_value=1800, max_value=2100, value=1990, step=1,
        help="西暦で入力してください（例: 1990）"
    )

    month = st.sidebar.slider("生月（1-12）", min_value=1, max_value=12, value=1)
    day   = st.sidebar.slider("生日（1-31）", min_value=1, max_value=31, value=1)

    st.sidebar.markdown("---")

    hour   = st.sidebar.slider("生時（時）",  min_value=0, max_value=23, value=12)
    minute = st.sidebar.slider("生時（分）",  min_value=0, max_value=59, value=0)
    tz     = st.sidebar.slider(
        "タイムゾーン（時間）",
        min_value=-12.0, max_value=14.0, value=9.0, step=0.5,
        help="JST = +9.0"
    )

    st.sidebar.markdown("---")

    lat = st.sidebar.number_input(
        "緯度（北+）",
        min_value=-90.0, max_value=90.0, value=35.6762, step=0.0001,
        format="%.4f",
        help="東京 = 35.6762"
    )
    lon_geo = st.sidebar.number_input(
        "経度（東+）",
        min_value=-180.0, max_value=180.0, value=139.6503, step=0.0001,
        format="%.4f",
        help="東京 = 139.6503"
    )

    st.sidebar.markdown("---")
    calc_button = st.sidebar.button("🔮 計算する", type="primary", use_container_width=True)

    return dict(
        year=int(year), month=month, day=day,
        hour=hour, minute=minute, tz=tz,
        lat=lat, lon_geo=lon_geo,
        calc=calc_button,
    )


# ---------------------------------------------------------------------------
# Tab 1: 惑星位置
# ---------------------------------------------------------------------------
def render_planet_tab(planets: list[dict]):
    st.subheader("🌟 惑星位置（Sidereal / KP アヤナムシャ）")

    rows = []
    for p in planets:
        retro = "R" if (p['retrograde'] or p['abbr'] in ('Ra', 'Ke')) else ""
        rows.append({
            "惑星": fmt_planet_label(p['abbr']),
            "星座":  f"{p['sign_ja']}（{p['sign_en']}）",
            "度分秒": fmt_dms(p['deg'], p['min'], p['sec']),
            "ナクシャトラ": p['nak_name'],
            "NL（星主）": p['nl'],
            "SL（サブ）": p['sl'],
            "SSL（サブサブ）": p['ssl'],
            "ハウス": p['house'],
            "逆行": retro,
            "_abbr": p['abbr'],   # hidden for styling
        })

    df = pd.DataFrame(rows)

    def style_row(row):
        abbr = row["_abbr"]
        bg   = PLANET_COLORS.get(abbr, "#FFFFFF")
        fg   = PLANET_TEXT_COLORS.get(abbr, "#000000")
        return [f"background-color: {bg}; color: {fg}; font-weight: bold;"
                if col != "_abbr" else "" for col in row.index]

    display_cols = [c for c in df.columns if c != "_abbr"]
    styled = (
        df.style
        .apply(style_row, axis=1)
        .hide(axis="index")
    )
    # Only show display columns (drop _abbr)
    styled = df[display_cols].style.apply(
        lambda row: [
            f"background-color: {PLANET_COLORS.get(df.at[row.name, '_abbr'], '#FFF')}; "
            f"color: {PLANET_TEXT_COLORS.get(df.at[row.name, '_abbr'], '#000')}; "
            f"font-weight: bold;"
            for _ in row.index
        ],
        axis=1,
    ).hide(axis="index")

    st.dataframe(styled, use_container_width=True, height=390)


# ---------------------------------------------------------------------------
# Tab 2: カスプ表
# ---------------------------------------------------------------------------
def render_cusp_tab(cusps: list[float], sub_table: list[dict]):
    st.subheader("🏠 カスプ表（プラシダス / KP サイデリアル）")

    rows = []
    for i, lon in enumerate(cusps):
        sign_idx, _ = deg_to_sign(lon)
        d, m, s     = deg_to_dms(lon)
        nl, sl, ssl = get_sub_lords(lon, sub_table)
        rows.append({
            "ハウス":        f"第{i+1}ハウス（H{i+1}）",
            "星座":          f"{SIGNS_JA[sign_idx]}（{SIGNS_EN[sign_idx]}）",
            "度分秒":        fmt_dms(d, m, s),
            "NL（星主）":    nl,
            "SL（サブ）":    sl,
            "SSL（サブサブ）": ssl,
        })

    df = pd.DataFrame(rows)

    # Alternate row shading
    def alt_rows(row):
        color = "#F0F4FA" if row.name % 2 == 0 else "#FFFFFF"
        return [f"background-color: {color};" for _ in row]

    styled = df.style.apply(alt_rows, axis=1).hide(axis="index")
    st.dataframe(styled, use_container_width=True, height=460)


# ---------------------------------------------------------------------------
# Tab 3: ダシャー表
# ---------------------------------------------------------------------------
def render_dasha_tab(dashas: list[dict], dasha_start_planet: str, remaining_years: float):
    st.subheader("⏳ ダシャー表（ヴィムショッタリ・ダシャー）")

    st.info(
        f"**出生時ダシャー**: {fmt_planet_label(dasha_start_planet)}  ／  "
        f"**残余年数**: {remaining_years:.4f} 年"
    )

    for dasha in dashas:
        maha = dasha['planet']
        bg   = PLANET_COLORS.get(maha, "#EEE")
        fg   = PLANET_TEXT_COLORS.get(maha, "#000")
        label = (
            f"{fmt_planet_label(maha)}　"
            f"{jd_to_date_str(dasha['start_jd'])} → {jd_to_date_str(dasha['end_jd'])}　"
            f"（{dasha['years']:.4f} 年）"
        )

        with st.expander(label, expanded=False):
            antar_rows = []
            for a in dasha['antardashas']:
                months = a['years'] * 12
                antar_rows.append({
                    "アンタルダシャー": fmt_planet_label(a['planet']),
                    "開始日":           jd_to_date_str(a['start_jd']),
                    "終了日":           jd_to_date_str(a['end_jd']),
                    "期間（月）":       f"{months:.1f} ヶ月",
                    "_abbr":            a['planet'],
                })

            adf = pd.DataFrame(antar_rows)
            display_cols = [c for c in adf.columns if c != "_abbr"]

            styled = adf[display_cols].style.apply(
                lambda row: [
                    f"background-color: {PLANET_COLORS.get(adf.at[row.name, '_abbr'], '#FFF')}; "
                    f"color: {PLANET_TEXT_COLORS.get(adf.at[row.name, '_abbr'], '#000')};"
                    for _ in row.index
                ],
                axis=1,
            ).hide(axis="index")
            st.dataframe(styled, use_container_width=True)


# ---------------------------------------------------------------------------
# Tab 4: シグニフィケーター
# ---------------------------------------------------------------------------
def render_significator_tab(sig: dict):
    st.subheader("🔍 シグニフィケーター（4グループ / 12ハウス）")

    st.markdown("""
| グループ | 意味 |
|---------|------|
| **A** | そのハウスにある惑星のナクシャトラに位置する惑星 |
| **B** | そのハウスにある惑星（在住惑星） |
| **C** | そのハウスのカスプ星座支配星のナクシャトラに位置する惑星 |
| **D** | そのハウスのカスプ星座の支配星 |
    """)

    def fmt_planets(lst):
        if not lst:
            return "―"
        return "、".join(fmt_planet_label(p) for p in lst)

    rows = []
    for h in range(1, 13):
        s = sig[h]
        rows.append({
            "ハウス":     f"H{h}",
            "星座":       f"{s['sign_ja']}（{s['sign']}）",
            "A（占星NL）": fmt_planets(s['A']),
            "B（在住）":   fmt_planets(s['B']),
            "C（支配NL）": fmt_planets(s['C']),
            "D（支配星）": fmt_planet_label(s['D']),
        })

    df = pd.DataFrame(rows)

    def alt_rows(row):
        color = "#F0F4FA" if row.name % 2 == 0 else "#FFFFFF"
        return [f"background-color: {color};" for _ in row]

    styled = df.style.apply(alt_rows, axis=1).hide(axis="index")
    st.dataframe(styled, use_container_width=True)

    st.markdown("---")
    st.markdown("#### 惑星別シグニフィケーター（Planet-centric View）")

    rows2 = []
    for abbr in PLANET_ORDER:
        a_houses = [str(h) for h in range(1, 13) if abbr in sig[h]['A']]
        b_houses = [str(h) for h in range(1, 13) if abbr in sig[h]['B']]
        c_houses = [str(h) for h in range(1, 13) if abbr in sig[h]['C']]
        d_houses = [str(h) for h in range(1, 13) if sig[h]['D'] == abbr]
        rows2.append({
            "惑星":        fmt_planet_label(abbr),
            "A（担当）":   "、".join(a_houses) or "―",
            "B（在住）":   "、".join(b_houses) or "―",
            "C（担当）":   "、".join(c_houses) or "―",
            "D（支配）":   "、".join(d_houses) or "―",
            "_abbr":       abbr,
        })

    df2 = pd.DataFrame(rows2)
    display_cols2 = [c for c in df2.columns if c != "_abbr"]

    styled2 = df2[display_cols2].style.apply(
        lambda row: [
            f"background-color: {PLANET_COLORS.get(df2.at[row.name, '_abbr'], '#FFF')}; "
            f"color: {PLANET_TEXT_COLORS.get(df2.at[row.name, '_abbr'], '#000')}; "
            f"font-weight: bold;"
            for _ in row.index
        ],
        axis=1,
    ).hide(axis="index")
    st.dataframe(styled2, use_container_width=True)


# ---------------------------------------------------------------------------
# Tab 5: ルーリング惑星
# ---------------------------------------------------------------------------
def render_ruling_tab(rp: dict):
    st.subheader("👑 ルーリング惑星（現在時刻基準）")

    y, mo, d, h = swe.revjul(rp['now_jd'], swe.GREG_CAL)
    now_str = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}  UTC"
    st.caption(f"現在時刻 (UTC): {now_str}")

    m_d, m_m, m_s = deg_to_dms(rp['moon_lon'])
    a_d, a_m, a_s = deg_to_dms(rp['asc_lon'])

    rows = [
        {"項目": "曜日",                           "値": rp['weekday']},
        {"項目": "曜日支配星（Day Lord）",          "値": fmt_planet_label(rp['day_lord'])},
        {"項目": "（区切り）",                      "値": ""},
        {"項目": "現在月（Current Moon）",          "値": f"{rp['moon_sign_ja']}（{rp['moon_sign']}）  {fmt_dms(m_d, m_m, m_s)}"},
        {"項目": "月星座支配星（Moon Sign Lord）",  "値": fmt_planet_label(rp['moon_sign_lord'])},
        {"項目": "月ナクシャトラ支配星（Moon Star Lord）", "値": fmt_planet_label(rp['moon_star_lord'])},
        {"項目": "（区切り）",                      "値": ""},
        {"項目": "現在ラグナ（Current ASC）",       "値": f"{rp['asc_sign_ja']}（{rp['asc_sign']}）  {fmt_dms(a_d, a_m, a_s)}"},
        {"項目": "ラグナ星座支配星（Lagna Sign Lord）",  "値": fmt_planet_label(rp['lagna_sign_lord'])},
        {"項目": "ラグナ星主（Lagna Star Lord）",   "値": fmt_planet_label(rp['lagna_star_lord'])},
        {"項目": "ラグナサブ主（Lagna Sub Lord）",  "値": fmt_planet_label(rp['lagna_sub_lord'])},
    ]

    df = pd.DataFrame(rows)

    def style_ruling(row):
        if row["項目"] == "（区切り）":
            return ["border-top: 2px solid #aaa; font-size: 0px;"] * len(row)
        return [""] * len(row)

    styled = df.style.apply(style_ruling, axis=1).hide(axis="index")
    st.dataframe(styled, use_container_width=True)

    # Summary
    rp_set = sorted({
        rp['day_lord'], rp['moon_sign_lord'], rp['moon_star_lord'],
        rp['lagna_sign_lord'], rp['lagna_star_lord'], rp['lagna_sub_lord']
    })
    st.markdown("**ルーリング惑星セット:**")
    cols = st.columns(len(rp_set))
    for col, abbr in zip(cols, rp_set):
        bg = PLANET_COLORS.get(abbr, "#EEE")
        fg = PLANET_TEXT_COLORS.get(abbr, "#000")
        col.markdown(
            f"<div style='background:{bg};color:{fg};text-align:center;"
            f"padding:6px 4px;border-radius:6px;font-weight:bold;'>"
            f"{abbr}<br><small>{PLANET_JA[abbr]}</small></div>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Tab 6: サブロード表（243行）
# ---------------------------------------------------------------------------
def render_sub_lord_tab(sub_table: list[dict]):
    st.subheader("📋 サブロード参照表（KP 243分割）")
    st.caption("全天をヴィムショッタリ・ダシャーの比率で243分割した KP サブロード表")

    rows = []
    for i, entry in enumerate(sub_table):
        start  = entry['start_lon']
        end    = entry['end_lon']
        sign_idx, deg_in = deg_to_sign(start)
        sign_start = f"{SIGNS_EN[sign_idx]} {deg_in:.4f}°"
        rows.append({
            "#":            i + 1,
            "ナクシャトラ": entry['nak_name'],
            "NL（星主）":   entry['nak_lord'],
            "SL（サブ）":   entry['sub_lord'],
            "開始（°）":   f"{start:.4f}",
            "終了（°）":   f"{end:.4f}",
            "開始（Sign°）": sign_start,
        })

    df = pd.DataFrame(rows)

    # Color the NL and SL columns by planet color
    def style_sub(row):
        nl_abbr = row["NL（星主）"]
        sl_abbr = row["SL（サブ）"]
        result = []
        for col in row.index:
            if col == "NL（星主）":
                bg = PLANET_COLORS.get(nl_abbr, "#FFF")
                fg = PLANET_TEXT_COLORS.get(nl_abbr, "#000")
                result.append(f"background-color: {bg}; color: {fg}; font-weight: bold;")
            elif col == "SL（サブ）":
                bg = PLANET_COLORS.get(sl_abbr, "#FFF")
                fg = PLANET_TEXT_COLORS.get(sl_abbr, "#000")
                result.append(f"background-color: {bg}; color: {fg}; font-weight: bold;")
            elif row.name % 2 == 0:
                result.append("background-color: #F8F8F8;")
            else:
                result.append("")
        return result

    styled = df.style.apply(style_sub, axis=1).hide(axis="index")
    st.dataframe(styled, use_container_width=True, height=500)


# ---------------------------------------------------------------------------
# Welcome / instructions screen
# ---------------------------------------------------------------------------
def render_welcome():
    st.markdown("""
## 🪐 KP占星術計算ツールへようこそ

**KP (Krishnamurti Paddhati) ジョーティシュ** は、インド占星術の近代的手法で、
ナクシャトラ（星宿）のサブロード体系による精密な占断が特徴です。

### 使い方
1. **左のサイドバー**に出生データを入力してください
2. **「計算する」ボタン**をクリック
3. 各タブで計算結果を確認できます

### 計算内容（6タブ）

| タブ | 内容 |
|-----|------|
| 🌟 **惑星位置** | 9惑星の星座・度数・ナクシャトラ・NL/SL/SSL・ハウス |
| 🏠 **カスプ表** | プラシダス12ハウスのカスプ位置と NL/SL/SSL |
| ⏳ **ダシャー表** | ヴィムショッタリ・マハーダシャーとアンタルダシャー |
| 🔍 **シグニフィケーター** | 各ハウスの A/B/C/D 4グループ分析 |
| 👑 **ルーリング惑星** | 現在時刻の6ルーリング惑星 |
| 📋 **サブロード表** | KP 243分割サブロード参照表 |

### デフォルト値
- 場所: **東京**（緯度 35.6762°、経度 139.6503°）
- タイムゾーン: **JST（+9.0時間）**
- アヤナムシャ: **KP (Krishnamurti)**

---
*計算エンジン: Swiss Ephemeris (pyswisseph) + KP アヤナムシャ*
    """)


# ---------------------------------------------------------------------------
# Condition Chart tab (調子チャート)
# ---------------------------------------------------------------------------

# Score label helper
def _score_label(score: float) -> str:
    if score >= 70:
        return "絶好調 🌟"
    elif score >= 40:
        return "好調 ↑"
    elif score >= 10:
        return "やや好調"
    elif score >= -10:
        return "平常"
    elif score >= -40:
        return "やや低調"
    elif score >= -70:
        return "低調 ↓"
    else:
        return "要注意 ⚠"


# House meaning labels
_HOUSE_MEANING = {
    1: "自己・活力", 2: "財・家族", 3: "努力・勇気", 4: "安心・家庭",
    5: "喜び・創造", 6: "病・障害", 7: "パートナー", 8: "変容・危機",
    9: "幸運・拡大", 10: "仕事・地位", 11: "利益・成就", 12: "孤立・損失",
}


def render_condition_tab(birth_jd: float, lat: float, lon_geo: float,
                         sub_table: list, tz_offset: float = 9.0):
    st.header("📈 調子チャート")
    st.caption("KPシステムに基づく個人コンディション可視化 — 月トランジット・ルーリング惑星・ダシャーの複合スコア")

    # ── Range selector ──────────────────────────────────────────
    range_cols = st.columns(4)
    range_labels = ["今日", "今週", "今月", "今年"]
    if 'condition_range' not in st.session_state:
        st.session_state['condition_range'] = "今日"

    for i, label in enumerate(range_labels):
        with range_cols[i]:
            if st.button(label, key=f"range_{label}",
                         type="primary" if st.session_state['condition_range'] == label else "secondary",
                         use_container_width=True):
                st.session_state['condition_range'] = label

    selected = st.session_state['condition_range']

    # ── Time range & interval ────────────────────────────────────
    now_utc = datetime.datetime.utcnow()
    now_jd = swe.julday(
        now_utc.year, now_utc.month, now_utc.day,
        now_utc.hour + now_utc.minute / 60.0 + now_utc.second / 3600.0,
        swe.GREG_CAL,
    )

    range_config = {
        "今日":  {"days": 1,   "interval": 30},
        "今週":  {"days": 7,   "interval": 120},
        "今月":  {"days": 30,  "interval": 360},
        "今年":  {"days": 365, "interval": 2880},
    }
    cfg = range_config[selected]
    start_jd = now_jd - cfg["days"] / 2
    end_jd   = now_jd + cfg["days"] / 2

    # ── Calculate with spinner ───────────────────────────────────
    cache_key = f"condition_df_{selected}_{birth_jd:.2f}_{lat:.4f}_{lon_geo:.4f}"
    if cache_key not in st.session_state:
        with st.spinner(f"{selected}のスコアを計算中..."):
            try:
                import swisseph as swe_inner
                swe_inner.set_sid_mode(swe_inner.SIDM_KRISHNAMURTI)
                df = calc_condition_timeline(
                    birth_jd=birth_jd,
                    lat=lat,
                    lon_geo=lon_geo,
                    start_jd=start_jd,
                    end_jd=end_jd,
                    interval_minutes=cfg["interval"],
                    tz_offset_hours=tz_offset,
                )
                st.session_state[cache_key] = df
            except Exception as e:
                st.error(f"スコア計算エラー: {e}")
                st.exception(e)
                return
    df = st.session_state[cache_key]

    if df.empty:
        st.warning("データがありません")
        return

    # ── Current score display ────────────────────────────────────
    # Find row closest to now
    now_local = now_utc + datetime.timedelta(hours=tz_offset)
    df['_dt_diff'] = (df['dt_local'] - now_local).abs()
    closest_idx = df['_dt_diff'].idxmin()
    current_row = df.loc[closest_idx]

    score_val = current_row['overall']
    moon_h    = int(current_row['moon_house'])
    moon_sign = current_row['moon_sign_ja']

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("総合スコア", f"{score_val:+.0f}", _score_label(score_val))
    with c2:
        st.metric("仕事", f"{current_row['career']:+.0f}")
    with c3:
        st.metric("健康", f"{current_row['health']:+.0f}")
    with c4:
        st.metric("運勢", f"{current_row['fortune']:+.0f}")

    house_meaning = _HOUSE_MEANING.get(moon_h, "")
    st.info(
        f"**現在の月:** {moon_sign}座  第{moon_h}室 — {house_meaning}  ／  "
        f"現地時刻: {now_local.strftime('%Y-%m-%d %H:%M')}"
    )

    # ── Plotly chart ─────────────────────────────────────────────
    fig = go.Figure()

    line_styles = {
        'overall': {'color': '#FFFFFF', 'width': 2.5, 'name': '総合'},
        'career':  {'color': '#00BFFF', 'width': 1.5, 'name': '仕事'},
        'health':  {'color': '#00FF88', 'width': 1.5, 'name': '健康'},
        'fortune': {'color': '#FFD700', 'width': 1.5, 'name': '運勢'},
    }

    for col, style in line_styles.items():
        hover_texts = [
            f"<b>{row['dt_local'].strftime('%m/%d %H:%M')}</b><br>"
            f"スコア: {row[col]:+.0f}<br>"
            f"月: {row['moon_sign_ja']}座 第{int(row['moon_house'])}室 ({_HOUSE_MEANING.get(int(row['moon_house']),'')})"
            for _, row in df.iterrows()
        ]
        fig.add_trace(go.Scatter(
            x=df['dt_local'],
            y=df[col],
            mode='lines',
            name=style['name'],
            line=dict(color=style['color'], width=style['width']),
            hovertext=hover_texts,
            hoverinfo='text',
        ))

    # Zero line and band annotations
    fig.add_hline(y=0,   line_dash='dot', line_color='gray', line_width=1)
    fig.add_hline(y=50,  line_dash='dot', line_color='rgba(0,200,80,0.3)',  line_width=1)
    fig.add_hline(y=-50, line_dash='dot', line_color='rgba(200,50,50,0.3)', line_width=1)

    # Background bands
    fig.add_hrect(y0=50,  y1=100, fillcolor='rgba(0,200,80,0.05)',  line_width=0)
    fig.add_hrect(y0=-100, y1=-50, fillcolor='rgba(200,50,50,0.05)', line_width=0)

    # Now vertical line
    fig.add_vline(
        x=now_local,
        line_dash='dash', line_color='rgba(255,80,80,0.7)', line_width=1.5,
        annotation_text="現在", annotation_position="top right",
        annotation_font_color='rgba(255,80,80,0.9)',
    )

    fig.update_layout(
        paper_bgcolor='#1a1a2e',
        plot_bgcolor='#16213e',
        font=dict(color='#e0e0e0', family='sans-serif'),
        xaxis=dict(
            showgrid=True, gridcolor='rgba(255,255,255,0.08)',
            tickfont=dict(size=11),
        ),
        yaxis=dict(
            range=[-105, 105],
            showgrid=True, gridcolor='rgba(255,255,255,0.08)',
            tickvals=[-100, -50, 0, 50, 100],
            ticktext=['-100', '-50', '0', '+50', '+100'],
        ),
        legend=dict(
            orientation='h', yanchor='bottom', y=1.02,
            xanchor='right', x=1,
            bgcolor='rgba(0,0,0,0)',
        ),
        hovermode='x unified',
        margin=dict(l=40, r=20, t=40, b=40),
        height=420,
    )

    st.plotly_chart(fig, use_container_width=True)

    # ── Interpretation text ──────────────────────────────────────
    with st.expander("この期間の解説"):
        period_avg = df['overall'].mean()
        best_row   = df.loc[df['overall'].idxmax()]
        worst_row  = df.loc[df['overall'].idxmin()]

        st.markdown(f"""
**期間平均スコア:** {period_avg:+.1f}  （{_score_label(period_avg)}）

**ベストタイミング:** {best_row['dt_local'].strftime('%m/%d %H:%M')}  スコア {best_row['overall']:+.0f}
→ 月: {best_row['moon_sign_ja']}座 第{int(best_row['moon_house'])}室 （{_HOUSE_MEANING.get(int(best_row['moon_house']),'')}）

**注意タイミング:** {worst_row['dt_local'].strftime('%m/%d %H:%M')}  スコア {worst_row['overall']:+.0f}
→ 月: {worst_row['moon_sign_ja']}座 第{int(worst_row['moon_house'])}室 （{_HOUSE_MEANING.get(int(worst_row['moon_house']),'')}）

**スコア構成：** 月トランジット 50% ＋ ルーリング惑星調和 35% ＋ ダシャー基調 15%
        """)

    # Clear cache button
    if st.button("🔄 再計算", key="recalc_condition"):
        if cache_key in st.session_state:
            del st.session_state[cache_key]
        st.rerun()


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
def main():
    # Sidebar inputs
    inputs = sidebar_inputs()

    # Main header
    st.title("🪐 KP占星術計算ツール")
    st.caption("Krishnamurti Paddhati Jyotish Calculator")

    if not inputs['calc']:
        render_welcome()
        return

    # -----------------------------------------------------------------------
    # Run calculations
    # -----------------------------------------------------------------------
    with st.spinner("計算中... (Calculating...)"):
        try:
            swe.set_sid_mode(swe.SIDM_KRISHNAMURTI)

            year, month, day = inputs['year'], inputs['month'], inputs['day']
            hour, minute      = inputs['hour'], inputs['minute']
            tz                = inputs['tz']
            lat               = inputs['lat']
            lon_geo           = inputs['lon_geo']

            jd        = birth_to_jd(year, month, day, hour, minute, tz)
            sub_table = build_sub_lord_table()
            planets   = calc_planet_positions(jd, sub_table)
            cusps     = calc_placidus_cusps(jd, lat, lon_geo)
            planets   = assign_houses_to_planets(planets, cusps)

            moon_lon = next(p['lon'] for p in planets if p['abbr'] == 'Mo')
            dashas, dasha_start_planet, remaining_years = calc_vimshottari_dasha(moon_lon, jd)

            sig = calc_significators(planets, cusps)

            now_utc = datetime.datetime.utcnow()
            now_jd  = swe.julday(
                now_utc.year, now_utc.month, now_utc.day,
                now_utc.hour + now_utc.minute / 60.0 + now_utc.second / 3600.0,
                swe.GREG_CAL,
            )
            ruling = calc_ruling_planets(now_jd, lat, lon_geo, sub_table)

            aya          = swe.get_ayanamsa_ut(jd)
            asc_sign_idx = int(cusps[0] // 30)

        except Exception as exc:
            st.error(f"計算エラー: {exc}")
            st.exception(exc)
            return

    # -----------------------------------------------------------------------
    # Birth summary banner
    # -----------------------------------------------------------------------
    tz_sign = "+" if tz >= 0 else ""
    st.success(
        f"**出生データ**: {year:04d}年{month:02d}月{day:02d}日  "
        f"{hour:02d}:{minute:02d}  TZ={tz_sign}{tz:.1f}h  ／  "
        f"緯度 {lat:+.4f}°  経度 {lon_geo:+.4f}°  ／  "
        f"ラグナ: **{SIGNS_JA[asc_sign_idx]}（{SIGNS_EN[asc_sign_idx]}）**  ／  "
        f"KP アヤナムシャ: {aya:.4f}°"
    )

    # -----------------------------------------------------------------------
    # Tabs
    # -----------------------------------------------------------------------
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "🌟 惑星位置",
        "🏠 カスプ表",
        "⏳ ダシャー表",
        "🔍 シグニフィケーター",
        "👑 ルーリング惑星",
        "📋 サブロード表",
        "📈 調子チャート",
    ])

    with tab1:
        render_planet_tab(planets)

    with tab2:
        render_cusp_tab(cusps, sub_table)

    with tab3:
        render_dasha_tab(dashas, dasha_start_planet, remaining_years)

    with tab4:
        render_significator_tab(sig)

    with tab5:
        render_ruling_tab(ruling)

    with tab6:
        render_sub_lord_tab(sub_table)

    with tab7:
        render_condition_tab(jd, lat, lon_geo, sub_table, tz_offset=inputs['tz'])


if __name__ == "__main__":
    main()
