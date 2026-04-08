#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KP (Krishnamurti Paddhati) Jyotish Astrology Calculator
KP (クリシュナムルティ・パッダティ) ジョーティシュ占星術計算ツール

Replicates the Google Spreadsheet KP tool with the following sections:
1. 入力・ホロスコープ  - Birth data + planet positions (Star Lord / Sub Lord / SSL / House)
2. カスプ表            - Placidus house cusp table (12 cusps, sidereal)
3. サブロード表        - Sub-lord reference table (243 divisions)
4. ダシャー表          - Vimshottari Dasha table (Mahadasha + Antardasha)
5. シグニフィケーター  - Significator analysis (Groups A/B/C/D per house)
6. ルーリング惑星      - Ruling Planets (for current moment)

Dependencies: pyswisseph, tabulate
Usage:
    python kp_calculator.py --year 1990 --month 1 --day 1 \
        --hour 12 --minute 0 --tz 9 --lat 35.6762 --lon 139.6503
    python kp_calculator.py   # interactive prompt
"""

import argparse
import datetime
import sys
from math import floor

import swisseph as swe
from tabulate import tabulate

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Vimshottari dasha years per planet
DASHA_YEARS = {
    'Ke': 7, 'Ve': 20, 'Su': 6, 'Mo': 10, 'Ma': 7,
    'Ra': 18, 'Ju': 16, 'Sa': 19, 'Me': 17
}
DASHA_TOTAL = 120  # sum of all dasha years

# Nakshatra lord order (repeating cycle of 9, starting from Ashwini=Ke)
NAK_LORD_ORDER = ['Ke', 'Ve', 'Su', 'Mo', 'Ma', 'Ra', 'Ju', 'Sa', 'Me']

# 27 nakshatras
NAKSHATRAS = [
    'Ashwini', 'Bharani', 'Krittika', 'Rohini', 'Mrigashira', 'Ardra',
    'Punarvasu', 'Pushya', 'Ashlesha', 'Magha', 'Purva Phalguni',
    'Uttara Phalguni', 'Hasta', 'Chitra', 'Swati', 'Vishakha', 'Anuradha',
    'Jyeshtha', 'Mula', 'Purva Ashadha', 'Uttara Ashadha', 'Shravana',
    'Dhanishtha', 'Shatabhisha', 'Purva Bhadrapada', 'Uttara Bhadrapada',
    'Revati'
]

NAK_SPAN = 360.0 / 27  # 13°20' = 13.3333...°

# Zodiac signs (index 0=Aries ... 11=Pisces)
SIGNS_EN = ['Ar', 'Ta', 'Ge', 'Ca', 'Le', 'Vi', 'Li', 'Sc', 'Sg', 'Cp', 'Aq', 'Pi']
SIGNS_JA = ['牡羊', '牡牛', '双子', '蟹', '獅子', '乙女', '天秤', '蠍', '射手', '山羊', '水瓶', '魚']

# Sign lords
SIGN_LORD = {
    'Ar': 'Ma', 'Ta': 'Ve', 'Ge': 'Me', 'Ca': 'Mo', 'Le': 'Su', 'Vi': 'Me',
    'Li': 'Ve', 'Sc': 'Ma', 'Sg': 'Ju', 'Cp': 'Sa', 'Aq': 'Sa', 'Pi': 'Ju'
}

# Planet display names
PLANET_JA = {
    'Su': '太陽', 'Mo': '月', 'Ma': '火星', 'Me': '水星',
    'Ju': '木星', 'Ve': '金星', 'Sa': '土星', 'Ra': 'ラーフ', 'Ke': 'ケートゥ'
}

# swisseph planet IDs
SWE_PLANET_IDS = {
    'Su': swe.SUN, 'Mo': swe.MOON, 'Ma': swe.MARS, 'Me': swe.MERCURY,
    'Ju': swe.JUPITER, 'Ve': swe.VENUS, 'Sa': swe.SATURN, 'Ra': swe.MEAN_NODE
    # Ke is computed as Ra + 180
}

# Planet order for output tables
PLANET_ORDER = ['Su', 'Mo', 'Ma', 'Me', 'Ju', 'Ve', 'Sa', 'Ra', 'Ke']

# Weekday lords (Monday=0 ... Sunday=6 per datetime.weekday())
WEEKDAY_LORD = {0: 'Mo', 1: 'Ma', 2: 'Me', 3: 'Ju', 4: 'Ve', 5: 'Sa', 6: 'Su'}
WEEKDAY_JA   = {0: '月曜', 1: '火曜', 2: '水曜', 3: '木曜', 4: '金曜', 5: '土曜', 6: '日曜'}


# ---------------------------------------------------------------------------
# Core helper functions
# ---------------------------------------------------------------------------

def deg_to_dms(deg: float) -> tuple[int, int, int]:
    """Convert decimal degrees to (degrees, minutes, seconds) within a sign (0-29)."""
    total_sec = round(deg * 3600)
    d = (total_sec // 3600) % 30
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return int(d), int(m), int(s)


def deg_to_sign(deg: float) -> tuple[int, float]:
    """Return (sign_index 0-11, degrees_within_sign 0-30)."""
    deg = deg % 360
    sign_idx = int(deg // 30)
    deg_in_sign = deg % 30
    return sign_idx, deg_in_sign


def get_nakshatra_info(lon: float) -> tuple[int, str, str, float, float]:
    """
    Given sidereal longitude (0-360), return:
    (nak_index 0-26, nak_name, nak_lord_abbr, position_in_nak, fraction_elapsed)
    """
    lon = lon % 360
    nak_idx = int(lon / NAK_SPAN)
    nak_idx = min(nak_idx, 26)
    pos_in_nak = lon - nak_idx * NAK_SPAN  # 0 .. NAK_SPAN
    fraction = pos_in_nak / NAK_SPAN        # 0.0 .. 1.0
    lord = NAK_LORD_ORDER[nak_idx % 9]
    return nak_idx, NAKSHATRAS[nak_idx], lord, pos_in_nak, fraction


def build_sub_lord_table() -> list[dict]:
    """
    Build the complete KP sub-lord table (243 entries).

    Each entry:
        start_lon  : start longitude of this sub division (sidereal, 0-360)
        end_lon    : end longitude
        nak_idx    : nakshatra index (0-26)
        nak_name   : nakshatra name
        nak_lord   : star lord abbreviation
        sub_lord   : sub lord abbreviation
        ssl_lord   : sub-sub lord abbreviation  (first SSL, for reference table)
    """
    table = []
    current_lon = 0.0

    for nak_idx in range(27):
        nak_lord = NAK_LORD_ORDER[nak_idx % 9]
        # Find starting position in the 9-lord cycle for this nakshatra
        start_pos = NAK_LORD_ORDER.index(nak_lord)

        for sub_offset in range(9):
            sub_lord = NAK_LORD_ORDER[(start_pos + sub_offset) % 9]
            sub_span = NAK_SPAN * DASHA_YEARS[sub_lord] / DASHA_TOTAL

            # Sub-sub lord: same logic within the sub
            ssl_start_pos = NAK_LORD_ORDER.index(sub_lord)
            ssl_lon = current_lon
            ssl_entries = []
            for ssl_offset in range(9):
                ssl_lord = NAK_LORD_ORDER[(ssl_start_pos + ssl_offset) % 9]
                ssl_span = sub_span * DASHA_YEARS[ssl_lord] / DASHA_TOTAL
                ssl_entries.append({
                    'start': ssl_lon,
                    'end': ssl_lon + ssl_span,
                    'ssl': ssl_lord
                })
                ssl_lon += ssl_span

            table.append({
                'start_lon': current_lon,
                'end_lon': current_lon + sub_span,
                'nak_idx': nak_idx,
                'nak_name': NAKSHATRAS[nak_idx],
                'nak_lord': nak_lord,
                'sub_lord': sub_lord,
                'ssl_entries': ssl_entries,
                'ssl_lord': ssl_entries[0]['ssl']  # first SSL for reference
            })
            current_lon += sub_span

    return table


def get_ssl_for_longitude(lon: float, sub_table: list[dict]) -> str:
    """Return the Sub-Sub Lord for a given longitude."""
    lon = lon % 360
    for entry in sub_table:
        for ssl_e in entry['ssl_entries']:
            if ssl_e['start'] <= lon < ssl_e['end']:
                return ssl_e['ssl']
    return '?'


def get_sub_lords(lon: float, sub_table: list[dict]) -> tuple[str, str, str]:
    """
    Return (nak_lord, sub_lord, sub_sub_lord) for a given sidereal longitude.
    """
    lon = lon % 360
    for entry in sub_table:
        if entry['start_lon'] <= lon < entry['end_lon']:
            nl = entry['nak_lord']
            sl = entry['sub_lord']
            ssl = get_ssl_for_longitude(lon, sub_table)
            return nl, sl, ssl
    # Edge case: exactly 360
    return get_sub_lords(0.0, sub_table)


# ---------------------------------------------------------------------------
# Julian Day calculation
# ---------------------------------------------------------------------------

def birth_to_jd(year: int, month: int, day: int,
                hour: int, minute: int, tz_offset: float) -> float:
    """Convert local birth date/time to Julian Day (UT)."""
    # Convert local time to UT
    ut_hour = hour + minute / 60.0 - tz_offset
    # Handle day rollover
    ut_day = day
    ut_month = month
    ut_year = year
    if ut_hour < 0:
        ut_hour += 24
        ut_day -= 1
        if ut_day < 1:
            ut_month -= 1
            if ut_month < 1:
                ut_month = 12
                ut_year -= 1
            # last day of previous month
            import calendar
            ut_day = calendar.monthrange(ut_year, ut_month)[1]
    elif ut_hour >= 24:
        ut_hour -= 24
        ut_day += 1
        import calendar
        days_in_month = calendar.monthrange(ut_year, ut_month)[1]
        if ut_day > days_in_month:
            ut_day = 1
            ut_month += 1
            if ut_month > 12:
                ut_month = 1
                ut_year += 1

    jd = swe.julday(ut_year, ut_month, ut_day, ut_hour, swe.GREG_CAL)
    return jd


# ---------------------------------------------------------------------------
# Planet position calculation
# ---------------------------------------------------------------------------

def calc_planet_positions(jd: float, sub_table: list[dict]) -> list[dict]:
    """
    Calculate sidereal positions of all 9 KP planets.
    Returns list of dicts with full positional data.
    """
    planets = []
    for abbr in PLANET_ORDER:
        if abbr == 'Ke':
            # Ketu = Rahu + 180
            ra_data = next(p for p in planets if p['abbr'] == 'Ra')
            lon = (ra_data['lon'] + 180.0) % 360
            speed = -ra_data['speed']  # retrograde mirror
        else:
            pid = SWE_PLANET_IDS[abbr]
            result, flag = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL | swe.FLG_SPEED)
            lon = result[0] % 360
            speed = result[3]  # deg/day

        sign_idx, deg_in_sign = deg_to_sign(lon)
        d, m, s = deg_to_dms(lon)  # sign-relative degrees
        nak_idx, nak_name, nl, pos_in_nak, frac = get_nakshatra_info(lon)
        nl2, sl, ssl = get_sub_lords(lon, sub_table)

        planets.append({
            'abbr': abbr,
            'name_ja': PLANET_JA[abbr],
            'lon': lon,
            'sign_idx': sign_idx,
            'sign_en': SIGNS_EN[sign_idx],
            'sign_ja': SIGNS_JA[sign_idx],
            'deg': d,
            'min': m,
            'sec': s,
            'nak_idx': nak_idx,
            'nak_name': nak_name,
            'nl': nl,
            'sl': sl,
            'ssl': ssl,
            'speed': speed,
            'retrograde': speed < 0,
            'house': None   # filled after house calculation
        })
    return planets


# ---------------------------------------------------------------------------
# House (cusp) calculation - Placidus
# ---------------------------------------------------------------------------

def calc_placidus_cusps(jd: float, lat: float, lon_geo: float) -> list[float]:
    """
    Calculate 12 sidereal Placidus house cusps.
    Returns list of 12 longitudes [cusp1..cusp12] in sidereal degrees.
    """
    # swe.houses returns tropical cusps; houses[0] has indices 0..11 = cusp1..cusp12
    # (index 0 is cusp1 = Ascendant)
    houses, ascmc = swe.houses(jd, lat, lon_geo, b'P')
    aya = swe.get_ayanamsa_ut(jd)
    sid_cusps = [(c - aya) % 360 for c in houses]
    return sid_cusps  # 12 cusps (index 0 = cusp1 = ASC)


def assign_houses_to_planets(planets: list[dict], cusps: list[float]) -> list[dict]:
    """
    Assign house number (1-12) to each planet based on Placidus cusps.
    A planet is in house N if its longitude falls between cusp N and cusp N+1.
    """
    for p in planets:
        lon = p['lon']
        house_num = 1
        for i in range(12):
            cusp_start = cusps[i]
            cusp_end = cusps[(i + 1) % 12]
            # Handle wrap-around at 360/0
            if cusp_start <= cusp_end:
                if cusp_start <= lon < cusp_end:
                    house_num = i + 1
                    break
            else:
                # Wrap case
                if lon >= cusp_start or lon < cusp_end:
                    house_num = i + 1
                    break
        p['house'] = house_num
    return planets


# ---------------------------------------------------------------------------
# Vimshottari Dasha calculation
# ---------------------------------------------------------------------------

def calc_vimshottari_dasha(
    moon_lon: float, birth_jd: float
) -> list[dict]:
    """
    Calculate Vimshottari Dasha periods starting from birth.

    Returns a list of Mahadasha periods (with nested Antardashas),
    covering approximately 120 years from birth.

    Each Mahadasha entry:
        {planet, start_jd, end_jd, years,
         antardashas: [{planet, start_jd, end_jd, years}, ...]}
    """
    # Moon's nakshatra lord = first Mahadasha planet
    nak_idx, nak_name, nl, pos_in_nak, frac_elapsed = get_nakshatra_info(moon_lon)
    remaining_frac = 1.0 - frac_elapsed
    remaining_years = remaining_frac * DASHA_YEARS[nl]

    # Build sequence of 9 maha lords starting from nl
    start_pos = NAK_LORD_ORDER.index(nl)
    maha_lords = [NAK_LORD_ORDER[(start_pos + i) % 9] for i in range(9)]

    dashas = []
    current_jd = birth_jd

    for i, maha in enumerate(maha_lords):
        if i == 0:
            maha_years = remaining_years
        else:
            maha_years = DASHA_YEARS[maha]

        maha_end_jd = current_jd + maha_years * 365.25

        # Antardasha: starts from the same Mahadasha lord, cycles through 9
        antars = []
        antar_start_jd = current_jd
        sub_start_pos = NAK_LORD_ORDER.index(maha)
        for j in range(9):
            antar = NAK_LORD_ORDER[(sub_start_pos + j) % 9]
            if i == 0:
                # First Mahadasha: proportional remaining
                antar_years = remaining_frac * DASHA_YEARS[maha] * DASHA_YEARS[antar] / DASHA_TOTAL
                # Recalculate: antar portion of maha_years
                antar_years = maha_years * DASHA_YEARS[antar] / DASHA_TOTAL
            else:
                antar_years = maha_years * DASHA_YEARS[antar] / DASHA_TOTAL

            antar_end_jd = antar_start_jd + antar_years * 365.25
            antars.append({
                'planet': antar,
                'start_jd': antar_start_jd,
                'end_jd': antar_end_jd,
                'years': antar_years
            })
            antar_start_jd = antar_end_jd

        dashas.append({
            'planet': maha,
            'start_jd': current_jd,
            'end_jd': maha_end_jd,
            'years': maha_years,
            'antardashas': antars
        })
        current_jd = maha_end_jd

    return dashas, nl, remaining_years


def jd_to_date_str(jd: float) -> str:
    """Convert Julian Day to YYYY-MM-DD string."""
    y, m, d, h = swe.revjul(jd, swe.GREG_CAL)
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


# ---------------------------------------------------------------------------
# Significator analysis
# ---------------------------------------------------------------------------

def calc_significators(planets: list[dict], cusps: list[float]) -> dict:
    """
    Calculate significators for each house (1-12) in 4 groups:

    Group A: Planets occupying the nakshatra of planets IN that house
             (i.e., for each planet X in house H, find all planets whose
              nakshatra lord is X)
    Group B: Planets physically IN that house
    Group C: Planets occupying the nakshatra of the sign lord of that house
             (i.e., find sign lord L of house H's cusp sign,
              then find all planets whose nakshatra lord is L)
    Group D: Sign lord of that house (lord of the sign on the cusp of house H)

    Returns dict: house_num -> {A: [...], B: [...], C: [...], D: str}
    """
    # Map planet abbr -> nakshatra lord (NL)
    planet_nl = {p['abbr']: p['nl'] for p in planets}
    # Map planet abbr -> house number
    planet_house = {p['abbr']: p['house'] for p in planets}
    # Map house number -> list of planets in it
    house_occupants = {h: [] for h in range(1, 13)}
    for p in planets:
        if p['house']:
            house_occupants[p['house']].append(p['abbr'])

    result = {}
    for h in range(1, 13):
        cusp_lon = cusps[h - 1]  # 0-indexed
        sign_idx, _ = deg_to_sign(cusp_lon)
        sign_en = SIGNS_EN[sign_idx]
        house_lord = SIGN_LORD[sign_en]  # D

        # Group B: planets in this house
        group_b = house_occupants[h][:]

        # Group A: planets whose NL is any planet in group B
        group_a = []
        for p in planets:
            if p['nl'] in group_b and p['abbr'] not in group_a:
                group_a.append(p['abbr'])

        # Group D: sign lord of this house cusp
        group_d = house_lord

        # Group C: planets whose NL is the sign lord (group D)
        group_c = []
        for p in planets:
            if p['nl'] == house_lord and p['abbr'] not in group_c:
                group_c.append(p['abbr'])

        result[h] = {
            'A': sorted(group_a),
            'B': sorted(group_b),
            'C': sorted(group_c),
            'D': group_d,
            'sign': sign_en,
            'sign_ja': SIGNS_JA[sign_idx],
            'house_lord': house_lord
        }

    return result


# ---------------------------------------------------------------------------
# Ruling Planets (for current moment)
# ---------------------------------------------------------------------------

def calc_ruling_planets(now_jd: float, lat: float, lon_geo: float,
                        sub_table: list[dict]) -> dict:
    """
    Calculate the 6 Ruling Planets for the current moment.

    Returns dict with keys:
        day_lord, moon_sign_lord, moon_star_lord,
        lagna_sign_lord, lagna_star_lord, lagna_sub_lord
    """
    # Convert JD to datetime for weekday
    y, m, d, h = swe.revjul(now_jd, swe.GREG_CAL)
    dt = datetime.datetime(int(y), int(m), int(d))
    weekday = dt.weekday()  # 0=Mon ... 6=Sun
    day_lord = WEEKDAY_LORD[weekday]

    # Current Moon position (sidereal)
    swe.set_sid_mode(swe.SIDM_KRISHNAMURTI)
    moon_result, _ = swe.calc_ut(now_jd, swe.MOON, swe.FLG_SIDEREAL)
    moon_lon = moon_result[0] % 360
    moon_sign_idx, _ = deg_to_sign(moon_lon)
    moon_sign_lord = SIGN_LORD[SIGNS_EN[moon_sign_idx]]
    _, _, moon_star_lord, _, _ = get_nakshatra_info(moon_lon)

    # Current Ascendant (sidereal)
    houses, ascmc = swe.houses(now_jd, lat, lon_geo, b'P')
    aya = swe.get_ayanamsa_ut(now_jd)
    asc_tropical = ascmc[0]
    asc_sid = (asc_tropical - aya) % 360
    asc_sign_idx, _ = deg_to_sign(asc_sid)
    lagna_sign_lord = SIGN_LORD[SIGNS_EN[asc_sign_idx]]
    _, _, lagna_star_lord, _, _ = get_nakshatra_info(asc_sid)
    _, lagna_sub_lord, _ = get_sub_lords(asc_sid, sub_table)

    return {
        'day_lord': day_lord,
        'weekday': WEEKDAY_JA[weekday],
        'moon_lon': moon_lon,
        'moon_sign': SIGNS_EN[moon_sign_idx],
        'moon_sign_ja': SIGNS_JA[moon_sign_idx],
        'moon_sign_lord': moon_sign_lord,
        'moon_star_lord': moon_star_lord,
        'asc_lon': asc_sid,
        'asc_sign': SIGNS_EN[asc_sign_idx],
        'asc_sign_ja': SIGNS_JA[asc_sign_idx],
        'lagna_sign_lord': lagna_sign_lord,
        'lagna_star_lord': lagna_star_lord,
        'lagna_sub_lord': lagna_sub_lord,
        'now_jd': now_jd
    }


# ---------------------------------------------------------------------------
# Output / display functions
# ---------------------------------------------------------------------------

SEP = "=" * 72


def planet_display(abbr: str) -> str:
    """Return 'Su(太陽)' style display string."""
    return f"{abbr}({PLANET_JA[abbr]})"


def print_section_header(num: int, title_ja: str, title_en: str = ""):
    print()
    print(SEP)
    en = f"  [{title_en}]" if title_en else ""
    print(f"  {num}. {title_ja}{en}")
    print(SEP)


def print_birth_and_horoscope(
    year, month, day, hour, minute, tz,
    lat, lon_geo, jd,
    planets: list[dict], cusps: list[float]
):
    """Sheet 1: 入力・ホロスコープ"""
    print_section_header(1, "入力・ホロスコープ", "Birth Data & Horoscope")

    # Birth data block
    y, mo, d, h_ut = swe.revjul(jd, swe.GREG_CAL)
    aya = swe.get_ayanamsa_ut(jd)
    asc_sign_idx, asc_deg = deg_to_sign(cusps[0])

    print(f"\n  生年月日 (Birth Date)    : {year:04d}-{month:02d}-{day:02d}")
    print(f"  生時 (Birth Time)       : {hour:02d}:{minute:02d}  TZ={tz:+.1f}h")
    print(f"  緯度 (Latitude)         : {lat:+.4f}°")
    print(f"  経度 (Longitude)        : {lon_geo:+.4f}°")
    print(f"  Julian Day (UT)         : {jd:.6f}")
    print(f"  KP アヤナムシャ          : {aya:.6f}°")
    print(f"  ラグナ (Ascendant)      : {SIGNS_JA[asc_sign_idx]}({SIGNS_EN[asc_sign_idx]})  "
          f"{asc_deg:.4f}°")

    # Planet table
    print()
    headers = ['惑星', '星座(Sign)', '度', '分', '秒',
               'ナクシャトラ', '星主NL', 'サブSL', 'サブサブSSL', 'ハウス', 'R']
    rows = []
    for p in planets:
        retro = 'R' if p['retrograde'] and p['abbr'] not in ('Ra', 'Ke') else ''
        # Ra and Ke are always retrograde by definition; mark separately
        if p['abbr'] in ('Ra', 'Ke'):
            retro = 'R'
        rows.append([
            f"{p['abbr']}({p['name_ja']})",
            f"{p['sign_ja']}({p['sign_en']})",
            p['deg'],
            p['min'],
            p['sec'],
            p['nak_name'],
            p['nl'],
            p['sl'],
            p['ssl'],
            p['house'],
            retro
        ])
    print(tabulate(rows, headers=headers, tablefmt='grid'))


def print_cusp_table(cusps: list[float], sub_table: list[dict]):
    """Sheet 2: カスプ表 - Placidus house cusps with NL/SL/SSL"""
    print_section_header(2, "カスプ表", "House Cusps (Placidus, Sidereal)")

    headers = ['ハウス', '星座(Sign)', '度', '分', '秒', '星主NL', 'サブSL', 'サブサブSSL']
    rows = []
    for i, lon in enumerate(cusps):
        sign_idx, deg_in_sign = deg_to_sign(lon)
        d, m, s = deg_to_dms(lon)
        nl, sl, ssl = get_sub_lords(lon, sub_table)
        rows.append([
            f"第{i+1}ハウス (H{i+1})",
            f"{SIGNS_JA[sign_idx]}({SIGNS_EN[sign_idx]})",
            d, m, s,
            nl, sl, ssl
        ])
    print()
    print(tabulate(rows, headers=headers, tablefmt='grid'))


def print_sub_lord_table(sub_table: list[dict]):
    """Sheet 3: サブロード表 - 243 KP sub-lord divisions"""
    print_section_header(3, "サブロード表", "KP Sub-Lord Reference Table (243 Divisions)")

    headers = ['#', 'ナクシャトラ', 'NL(星主)', 'SL(サブ)', '開始(°)', '終了(°)', '開始(Sign°)']
    rows = []
    for i, entry in enumerate(sub_table):
        start = entry['start_lon']
        end = entry['end_lon']
        sign_idx, deg_in = deg_to_sign(start)
        sign_start = f"{SIGNS_EN[sign_idx]} {deg_in:.4f}°"
        rows.append([
            i + 1,
            entry['nak_name'],
            entry['nak_lord'],
            entry['sub_lord'],
            f"{start:.4f}",
            f"{end:.4f}",
            sign_start
        ])
    print()
    # Print in chunks to keep readable
    print(tabulate(rows, headers=headers, tablefmt='grid'))


def print_dasha_table(dashas: list[dict], start_planet: str, remaining_years: float,
                      birth_year: int, birth_month: int, birth_day: int):
    """Sheet 4: ダシャー表 - Vimshottari Dasha + Antardasha"""
    print_section_header(4, "ダシャー表", "Vimshottari Dasha Table")

    print(f"\n  出生時ダシャー (Birth Dasha) : {start_planet}({PLANET_JA[start_planet]})")
    print(f"  残余年数 (Remaining years)  : {remaining_years:.4f} 年")
    print()

    maha_headers = ['マハーダシャー(MD)', '開始日', '終了日', '年数']
    antar_headers = ['  アンタルダシャー(AD)', '開始日', '終了日', '年数(月)']

    for d in dashas:
        maha_label = f"{d['planet']}({PLANET_JA[d['planet']]})"
        maha_row = [[
            maha_label,
            jd_to_date_str(d['start_jd']),
            jd_to_date_str(d['end_jd']),
            f"{d['years']:.4f}"
        ]]
        print(tabulate(maha_row, headers=maha_headers, tablefmt='simple'))

        antar_rows = []
        for a in d['antardashas']:
            months = a['years'] * 12
            antar_rows.append([
                f"  {a['planet']}({PLANET_JA[a['planet']]})",
                jd_to_date_str(a['start_jd']),
                jd_to_date_str(a['end_jd']),
                f"{months:.1f}ヶ月"
            ])
        print(tabulate(antar_rows, headers=antar_headers, tablefmt='simple'))
        print()


def print_significators(sig: dict, planets: list[dict]):
    """Sheet 5: シグニフィケーター - Significator analysis"""
    print_section_header(5, "シグニフィケーター", "Significators (4 Groups per House)")

    print("""
  各ハウスのシグニフィケーター (4グループ):
    グループA: そのハウスにある惑星のナクシャトラに位置する惑星
    グループB: そのハウスにある惑星
    グループC: そのハウスのカスプ星座支配星のナクシャトラに位置する惑星
    グループD: そのハウスのカスプ星座の支配星
""")

    def fmt_planets(lst):
        if not lst:
            return '―'
        return ', '.join(f"{p}({PLANET_JA[p]})" for p in lst)

    headers = ['ハウス', '星座', 'A(占星NL)',
               'B(在住)', 'C(支配NL)', 'D(支配星)']
    rows = []
    for h in range(1, 13):
        s = sig[h]
        rows.append([
            f"H{h}",
            f"{s['sign_ja']}({s['sign']})",
            fmt_planets(s['A']),
            fmt_planets(s['B']),
            fmt_planets(s['C']),
            f"{s['D']}({PLANET_JA[s['D']]})"
        ])
    print(tabulate(rows, headers=headers, tablefmt='grid'))

    # Also print a planet-centric view: for each planet, which houses does it signify?
    print("\n  --- 惑星別シグニフィケーター (Planet-centric view) ---\n")
    headers2 = ['惑星', 'A担当ハウス', 'B担当ハウス', 'C担当ハウス', 'D担当ハウス']
    rows2 = []
    for abbr in PLANET_ORDER:
        a_houses = [str(h) for h in range(1, 13) if abbr in sig[h]['A']]
        b_houses = [str(h) for h in range(1, 13) if abbr in sig[h]['B']]
        c_houses = [str(h) for h in range(1, 13) if abbr in sig[h]['C']]
        d_houses = [str(h) for h in range(1, 13) if sig[h]['D'] == abbr]
        rows2.append([
            f"{abbr}({PLANET_JA[abbr]})",
            ', '.join(a_houses) or '―',
            ', '.join(b_houses) or '―',
            ', '.join(c_houses) or '―',
            ', '.join(d_houses) or '―',
        ])
    print(tabulate(rows2, headers=headers2, tablefmt='grid'))


def print_ruling_planets(rp: dict, now_dt: datetime.datetime):
    """Sheet 6: ルーリング惑星 - Ruling Planets (current moment)"""
    print_section_header(6, "ルーリング惑星", "Ruling Planets (Current Moment)")

    now_str = now_dt.strftime('%Y-%m-%d %H:%M:%S')
    y, mo, d, h = swe.revjul(rp['now_jd'], swe.GREG_CAL)
    print(f"\n  現在時刻 (Now): {now_str} UTC")
    print()

    # Moon info
    m_sign_idx, m_deg = deg_to_sign(rp['moon_lon'])
    m_d, m_m, m_s = deg_to_dms(rp['moon_lon'])

    # Asc info
    a_sign_idx, a_deg = deg_to_sign(rp['asc_lon'])
    a_d, a_m, a_s = deg_to_dms(rp['asc_lon'])

    headers = ['項目', '値']
    rows = [
        ['曜日 (Weekday)', f"{rp['weekday']}"],
        ['曜日支配星 (Day Lord)',
         f"{rp['day_lord']}({PLANET_JA[rp['day_lord']]})"],
        ['', ''],
        ['現在月 (Current Moon)',
         f"{rp['moon_sign_ja']}({rp['moon_sign']})  {m_d}°{m_m}′{m_s}″"],
        ['月星座支配星 (Moon Sign Lord)',
         f"{rp['moon_sign_lord']}({PLANET_JA[rp['moon_sign_lord']]})"],
        ['月ナクシャトラ支配星 (Moon Star Lord)',
         f"{rp['moon_star_lord']}({PLANET_JA[rp['moon_star_lord']]})"],
        ['', ''],
        ['現在ラグナ (Current Lagna/ASC)',
         f"{rp['asc_sign_ja']}({rp['asc_sign']})  {a_d}°{a_m}′{a_s}″"],
        ['ラグナ星座支配星 (Lagna Sign Lord)',
         f"{rp['lagna_sign_lord']}({PLANET_JA[rp['lagna_sign_lord']]})"],
        ['ラグナ星主 (Lagna Star Lord)',
         f"{rp['lagna_star_lord']}({PLANET_JA[rp['lagna_star_lord']]})"],
        ['ラグナサブ主 (Lagna Sub Lord)',
         f"{rp['lagna_sub_lord']}({PLANET_JA[rp['lagna_sub_lord']]})"],
    ]
    print(tabulate(rows, headers=headers, tablefmt='grid'))

    # Summary line
    rp_set = sorted({
        rp['day_lord'], rp['moon_sign_lord'], rp['moon_star_lord'],
        rp['lagna_sign_lord'], rp['lagna_star_lord'], rp['lagna_sub_lord']
    })
    print(f"\n  ルーリング惑星セット: {', '.join(planet_display(p) for p in rp_set)}")


# ---------------------------------------------------------------------------
# CLI / Main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description='KP Jyotish Calculator / KP ジョーティシュ計算ツール',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples / 使用例:
  python kp_calculator.py --year 1990 --month 1 --day 1 --hour 12 --minute 0 \\
      --tz 9 --lat 35.6762 --lon 139.6503

  python kp_calculator.py  # interactive prompt / インタラクティブ入力
        """
    )
    parser.add_argument('--year',   type=int, help='生年（西暦）Birth year')
    parser.add_argument('--month',  type=int, help='生月（1-12）Birth month')
    parser.add_argument('--day',    type=int, help='生日 Birth day')
    parser.add_argument('--hour',   type=int, help='生時（時）Birth hour (0-23)')
    parser.add_argument('--minute', type=int, help='生時（分）Birth minute (0-59)')
    parser.add_argument('--tz',     type=float, default=9.0,
                        help='タイムゾーン（時間）Timezone offset (default=9 for JST)')
    parser.add_argument('--lat',    type=float,
                        help='緯度（北+）Latitude (e.g. 35.6762 for Tokyo)')
    parser.add_argument('--lon',    type=float,
                        help='経度（東+）Longitude (e.g. 139.6503 for Tokyo)')
    parser.add_argument('--sections', type=str, default='all',
                        help=('Sections to show (comma-separated: 1,2,3,4,5,6 or "all"). '
                              'e.g. --sections 1,4,6'))
    parser.add_argument('--no-sub-table', action='store_true',
                        help='Skip printing the 243-row sub-lord table (section 3)')
    return parser.parse_args()


def interactive_input() -> dict:
    """Prompt user for birth data interactively."""
    print("\n  KP ジョーティシュ計算ツール - 出生データを入力してください")
    print("  (KP Jyotish Calculator - Enter birth data)\n")

    def get_int(prompt, default=None, min_val=None, max_val=None):
        while True:
            suffix = f" [{default}]" if default is not None else ""
            val = input(f"  {prompt}{suffix}: ").strip()
            if val == '' and default is not None:
                return default
            try:
                v = int(val)
                if min_val is not None and v < min_val:
                    print(f"    ※ {min_val}以上の値を入力してください")
                    continue
                if max_val is not None and v > max_val:
                    print(f"    ※ {max_val}以下の値を入力してください")
                    continue
                return v
            except ValueError:
                print("    ※ 整数を入力してください")

    def get_float(prompt, default=None):
        while True:
            suffix = f" [{default}]" if default is not None else ""
            val = input(f"  {prompt}{suffix}: ").strip()
            if val == '' and default is not None:
                return default
            try:
                return float(val)
            except ValueError:
                print("    ※ 数値を入力してください")

    year   = get_int("生年（西暦）Birth year", min_val=1800, max_val=2100)
    month  = get_int("生月（1-12）Birth month", min_val=1, max_val=12)
    day    = get_int("生日 Birth day", min_val=1, max_val=31)
    hour   = get_int("生時（時）Birth hour 0-23", min_val=0, max_val=23)
    minute = get_int("生時（分）Birth minute 0-59", min_val=0, max_val=59)
    tz     = get_float("タイムゾーン（時間）Timezone offset", default=9.0)
    lat    = get_float("緯度（北+）Latitude (e.g. 35.6762)")
    lon    = get_float("経度（東+）Longitude (e.g. 139.6503)")

    return dict(year=year, month=month, day=day,
                hour=hour, minute=minute, tz=tz, lat=lat, lon=lon)


def main():
    args = parse_args()

    # Determine which sections to print
    if args.sections.lower() == 'all':
        show_sections = set(range(1, 7))
    else:
        try:
            show_sections = set(int(s.strip()) for s in args.sections.split(','))
        except ValueError:
            print("Error: --sections must be comma-separated integers or 'all'")
            sys.exit(1)

    # Gather birth data
    all_args = [args.year, args.month, args.day, args.hour, args.minute, args.lat, args.lon]
    if any(a is None for a in all_args):
        data = interactive_input()
    else:
        data = dict(
            year=args.year, month=args.month, day=args.day,
            hour=args.hour, minute=args.minute,
            tz=args.tz, lat=args.lat, lon=args.lon
        )

    year, month, day = data['year'], data['month'], data['day']
    hour, minute     = data['hour'], data['minute']
    tz               = data['tz']
    lat              = data['lat']
    lon_geo          = data['lon']

    # -----------------------------------------------------------------------
    # Set up Swiss Ephemeris
    # -----------------------------------------------------------------------
    swe.set_sid_mode(swe.SIDM_KRISHNAMURTI)

    # -----------------------------------------------------------------------
    # Core calculations
    # -----------------------------------------------------------------------
    print("\n  計算中... (Calculating...)")

    # Julian Day for birth moment (UT)
    jd = birth_to_jd(year, month, day, hour, minute, tz)

    # Build sub-lord table (243 entries)
    sub_table = build_sub_lord_table()

    # Planet positions (sidereal, KP ayanamsha)
    planets = calc_planet_positions(jd, sub_table)

    # Placidus cusps (sidereal)
    cusps = calc_placidus_cusps(jd, lat, lon_geo)

    # Assign houses to planets
    planets = assign_houses_to_planets(planets, cusps)

    # Vimshottari Dasha
    moon_lon = next(p['lon'] for p in planets if p['abbr'] == 'Mo')
    dashas, dasha_start_planet, remaining_years = calc_vimshottari_dasha(moon_lon, jd)

    # Significators
    sig = calc_significators(planets, cusps)

    # Ruling Planets (current moment in UTC)
    now_utc = datetime.datetime.utcnow()
    now_jd = swe.julday(now_utc.year, now_utc.month, now_utc.day,
                        now_utc.hour + now_utc.minute / 60.0 + now_utc.second / 3600.0,
                        swe.GREG_CAL)
    ruling = calc_ruling_planets(now_jd, lat, lon_geo, sub_table)

    # -----------------------------------------------------------------------
    # Output
    # -----------------------------------------------------------------------
    print(f"\n{'=' * 72}")
    print(f"  KP ジョーティシュ計算結果 (KP Jyotish Calculation Results)")
    print(f"  出生: {year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d} "
          f"TZ={tz:+.1f}  Lat={lat:+.4f}  Lon={lon_geo:+.4f}")
    print(f"{'=' * 72}")

    if 1 in show_sections:
        print_birth_and_horoscope(year, month, day, hour, minute, tz,
                                  lat, lon_geo, jd, planets, cusps)

    if 2 in show_sections:
        print_cusp_table(cusps, sub_table)

    if 3 in show_sections and not args.no_sub_table:
        print_sub_lord_table(sub_table)
    elif 3 in show_sections and args.no_sub_table:
        print_section_header(3, "サブロード表", "Sub-Lord Table")
        print("  (--no-sub-table フラグにより省略)")

    if 4 in show_sections:
        print_dasha_table(dashas, dasha_start_planet, remaining_years,
                          year, month, day)

    if 5 in show_sections:
        print_significators(sig, planets)

    if 6 in show_sections:
        print_ruling_planets(ruling, now_utc)

    print(f"\n{'=' * 72}")
    print("  計算完了 (Calculation complete)")
    print(f"{'=' * 72}\n")


# ---------------------------------------------------------------------------
# Planetary Dignity (惑星の品位) calculation
# ---------------------------------------------------------------------------

# Exaltation: (sign_index, exact_degree) — classic Vedic exaltation points
EXALTATION = {
    'Su': (0, 10.0),   # Aries 10°
    'Mo': (1, 3.0),    # Taurus 3°
    'Ma': (9, 28.0),   # Capricorn 28°
    'Me': (5, 15.0),   # Virgo 15°
    'Ju': (3, 5.0),    # Cancer 5°
    'Ve': (11, 27.0),  # Pisces 27°
    'Sa': (6, 20.0),   # Libra 20°
    'Ra': (1, 20.0),   # Taurus 20° (most accepted)
    'Ke': (7, 20.0),   # Scorpio 20°
}

# Debilitation: exactly opposite sign of exaltation
DEBILITATION = {
    'Su': (6, 10.0),   # Libra
    'Mo': (7, 3.0),    # Scorpio
    'Ma': (3, 28.0),   # Cancer
    'Me': (11, 15.0),  # Pisces
    'Ju': (9, 5.0),    # Capricorn
    'Ve': (5, 27.0),   # Virgo
    'Sa': (0, 20.0),   # Aries
    'Ra': (7, 20.0),   # Scorpio
    'Ke': (1, 20.0),   # Taurus
}

# Own sign(s) — signs ruled by each planet
OWN_SIGNS = {
    'Su': [4],           # Leo
    'Mo': [3],           # Cancer
    'Ma': [0, 7],        # Aries, Scorpio
    'Me': [2, 5],        # Gemini, Virgo
    'Ju': [8, 11],       # Sagittarius, Pisces
    'Ve': [1, 6],        # Taurus, Libra
    'Sa': [9, 10],       # Capricorn, Aquarius
    'Ra': [10],          # Aquarius (co-ruler)
    'Ke': [7],           # Scorpio (co-ruler)
}

# Moolatrikona sign and degree range — (sign_index, start_deg, end_deg)
MOOLATRIKONA = {
    'Su': (4, 0.0, 20.0),    # Leo 0-20°
    'Mo': (1, 3.0, 30.0),    # Taurus 3-30°
    'Ma': (0, 0.0, 12.0),    # Aries 0-12°
    'Me': (5, 15.0, 20.0),   # Virgo 15-20°
    'Ju': (8, 0.0, 10.0),    # Sagittarius 0-10°
    'Ve': (6, 0.0, 15.0),    # Libra 0-15°
    'Sa': (10, 0.0, 20.0),   # Aquarius 0-20°
}

# Friendly / Neutral / Enemy relationships (natural)
# permanent relationships between planets
_FRIENDS = {
    'Su': {'Mo', 'Ma', 'Ju'},
    'Mo': {'Su', 'Me'},
    'Ma': {'Su', 'Mo', 'Ju'},
    'Me': {'Su', 'Ve'},
    'Ju': {'Su', 'Mo', 'Ma'},
    'Ve': {'Me', 'Sa'},
    'Sa': {'Me', 'Ve'},
    'Ra': {'Me', 'Ve', 'Sa'},
    'Ke': {'Ma', 'Ju'},
}
_ENEMIES = {
    'Su': {'Ve', 'Sa'},
    'Mo': set(),
    'Ma': {'Me'},
    'Me': {'Mo'},
    'Ju': {'Me', 'Ve'},
    'Ve': {'Su', 'Mo'},
    'Sa': {'Su', 'Mo', 'Ma'},
    'Ra': {'Su', 'Mo', 'Ma'},
    'Ke': {'Ve', 'Sa'},
}


def calc_planet_dignity(planets: list[dict]) -> list[dict]:
    """
    Calculate dignity status for each planet.

    Returns list of dicts:
        {abbr, dignity, dignity_ja, dignity_score, detail}

    Dignity hierarchy (strongest to weakest):
        Exaltation (高揚) > Moolatrikona (ムーラトリコーナ) > Own Sign (自室)
        > Friendly (友好) > Neutral (中立) > Enemy (敵対) > Debilitation (減弱)
    """
    results = []
    for p in planets:
        abbr = p['abbr']
        sign_idx = p['sign_idx']
        deg_in_sign = p['lon'] % 30

        dignity = 'neutral'
        dignity_ja = '中立'
        dignity_score = 0  # -3 to +3

        # Check exaltation (exact sign match; orb tolerance ±5° for "near-exact")
        ex_sign, ex_deg = EXALTATION[abbr]
        if sign_idx == ex_sign:
            dist = abs(deg_in_sign - ex_deg)
            if dist <= 5:
                dignity, dignity_ja, dignity_score = 'exalted', '高揚(深)', 3
            else:
                dignity, dignity_ja, dignity_score = 'exalted', '高揚', 3

        # Check debilitation
        deb_sign, deb_deg = DEBILITATION[abbr]
        if sign_idx == deb_sign:
            dist = abs(deg_in_sign - deb_deg)
            if dist <= 5:
                dignity, dignity_ja, dignity_score = 'debilitated', '減弱(深)', -3
            else:
                dignity, dignity_ja, dignity_score = 'debilitated', '減弱', -3

        # Check moolatrikona (overrides own sign but not exaltation/debilitation)
        if dignity == 'neutral' and abbr in MOOLATRIKONA:
            mt_sign, mt_start, mt_end = MOOLATRIKONA[abbr]
            if sign_idx == mt_sign and mt_start <= deg_in_sign < mt_end:
                dignity, dignity_ja, dignity_score = 'moolatrikona', 'ムーラトリコーナ', 2

        # Check own sign
        if dignity == 'neutral' and sign_idx in OWN_SIGNS.get(abbr, []):
            dignity, dignity_ja, dignity_score = 'own', '自室', 2

        # Check friendly / enemy by sign lord
        if dignity == 'neutral':
            host_lord = SIGN_LORD[SIGNS_EN[sign_idx]]
            if host_lord != abbr:
                if host_lord in _FRIENDS.get(abbr, set()):
                    dignity, dignity_ja, dignity_score = 'friendly', '友好', 1
                elif host_lord in _ENEMIES.get(abbr, set()):
                    dignity, dignity_ja, dignity_score = 'enemy', '敵対', -1
                else:
                    dignity, dignity_ja, dignity_score = 'neutral', '中立', 0

        # Retrograde modifier
        retro_note = ''
        if p['retrograde'] and abbr not in ('Ra', 'Ke'):
            retro_note = '（逆行中）'

        results.append({
            'abbr': abbr,
            'name_ja': PLANET_JA[abbr],
            'sign_ja': p['sign_ja'],
            'sign_en': p['sign_en'],
            'house': p['house'],
            'dignity': dignity,
            'dignity_ja': dignity_ja + retro_note,
            'dignity_score': dignity_score,
            'retrograde': p['retrograde'] and abbr not in ('Ra', 'Ke'),
        })
    return results


# ---------------------------------------------------------------------------
# Planetary Aspects (惑星アスペクト) calculation
# ---------------------------------------------------------------------------

# Aspect definitions: (name_en, name_ja, angle, orb, nature, strength)
ASPECT_DEFS = [
    ('Conjunction', '会合(0°)',     0.0,   8.0,  'variable', 10),
    ('Opposition',  '対向(180°)', 180.0,   8.0,  'hard',      8),
    ('Trine',       '三分(120°)', 120.0,   7.0,  'soft',      7),
    ('Square',      '四分(90°)',   90.0,   7.0,  'hard',      6),
    ('Sextile',     '六分(60°)',   60.0,   5.0,  'soft',      4),
]

# Vedic special aspects (Graha Drishti): full-strength aspects unique to each planet
# Mars: 4th & 8th aspects;  Jupiter: 5th & 9th;  Saturn: 3rd & 10th;  Rahu/Ketu: 5th & 9th
VEDIC_SPECIAL_ASPECTS = {
    'Ma': [90.0, 210.0],           # 4th (90°) and 8th (210°) from Mars
    'Ju': [120.0, 240.0],          # 5th (120°) and 9th (240°) from Jupiter
    'Sa': [60.0, 270.0],           # 3rd (60°) and 10th (270°) from Saturn
    'Ra': [120.0, 240.0],          # same as Jupiter
    'Ke': [120.0, 240.0],          # same as Jupiter
}


def calc_aspects(planets: list[dict], orb_factor: float = 1.0) -> list[dict]:
    """
    Calculate all aspects between planet pairs.

    Args:
        planets:    list of planet dicts from calc_planet_positions()
        orb_factor: multiplier for orb tolerance (1.0 = standard, 0.5 = tight)

    Returns list of dicts:
        {planet1, planet2, aspect_name, aspect_ja, angle, exact_angle,
         orb_used, nature, strength, is_vedic_special, applying}
    """
    aspects = []
    n = len(planets)

    for i in range(n):
        for j in range(i + 1, n):
            p1, p2 = planets[i], planets[j]
            diff = (p2['lon'] - p1['lon']) % 360.0
            # Check both directions
            for name_en, name_ja, target_angle, max_orb, nature, strength in ASPECT_DEFS:
                orb = max_orb * orb_factor
                # Forward difference
                deviation_fwd = abs(diff - target_angle)
                # Reverse difference
                deviation_rev = abs((360.0 - diff) - target_angle) if target_angle > 0 else 999
                deviation = min(deviation_fwd, deviation_rev)

                if deviation <= orb:
                    # Determine if applying or separating
                    speed1 = p1.get('speed', 0)
                    speed2 = p2.get('speed', 0)
                    relative_speed = speed2 - speed1
                    if target_angle == 0:
                        applying = abs(diff) > 0 and relative_speed * (1 if diff > 180 else -1) < 0
                    else:
                        applying = deviation > 0 and relative_speed != 0

                    # Check if this is a Vedic special aspect
                    is_vedic = False
                    if p1['abbr'] in VEDIC_SPECIAL_ASPECTS:
                        for va in VEDIC_SPECIAL_ASPECTS[p1['abbr']]:
                            if abs(diff - va) <= orb:
                                is_vedic = True
                                break
                    if p2['abbr'] in VEDIC_SPECIAL_ASPECTS:
                        for va in VEDIC_SPECIAL_ASPECTS[p2['abbr']]:
                            rev_diff = (360.0 - diff) % 360.0
                            if abs(rev_diff - va) <= orb:
                                is_vedic = True
                                break

                    # Tighter orb = stronger
                    closeness_bonus = max(0, (orb - deviation) / orb * 3)

                    aspects.append({
                        'planet1': p1['abbr'],
                        'planet2': p2['abbr'],
                        'aspect_name': name_en,
                        'aspect_ja': name_ja,
                        'angle': round(diff, 2),
                        'exact_angle': target_angle,
                        'deviation': round(deviation, 2),
                        'orb_used': round(orb, 1),
                        'nature': nature,
                        'nature_ja': {'soft': '調和', 'hard': '緊張', 'variable': '可変'}[nature],
                        'strength': round(strength + closeness_bonus, 1),
                        'is_vedic_special': is_vedic,
                        'applying': applying,
                    })

    # Sort by strength descending
    aspects.sort(key=lambda x: x['strength'], reverse=True)
    return aspects


# ---------------------------------------------------------------------------
# Transit Analysis (トランジット解析) — planetary transits over natal chart
# ---------------------------------------------------------------------------

def calc_transit_positions(transit_jd: float, sub_table: list[dict],
                           natal_cusps: list[float]) -> list[dict]:
    """
    Calculate transit planet positions and map them to natal houses.

    Returns list of dicts with full transit positional data
    plus natal house assignment.
    """
    swe.set_sid_mode(swe.SIDM_KRISHNAMURTI)
    transit_planets = calc_planet_positions(transit_jd, sub_table)
    # Assign to NATAL houses (not transit houses)
    transit_planets = assign_houses_to_planets(transit_planets, natal_cusps)
    return transit_planets


def calc_transit_aspects_to_natal(transit_planets: list[dict],
                                  natal_planets: list[dict],
                                  orb_factor: float = 0.8) -> list[dict]:
    """
    Calculate aspects between transit planets and natal planets.

    Args:
        transit_planets: current planet positions
        natal_planets:   birth chart planet positions
        orb_factor:      tighter orbs for transit (default 0.8)

    Returns list of dicts similar to calc_aspects() but with
    transit_planet and natal_planet keys.
    """
    aspects = []
    for tp in transit_planets:
        for np_ in natal_planets:
            diff = (tp['lon'] - np_['lon']) % 360.0

            for name_en, name_ja, target_angle, max_orb, nature, strength in ASPECT_DEFS:
                orb = max_orb * orb_factor
                deviation_fwd = abs(diff - target_angle)
                deviation_rev = abs((360.0 - diff) - target_angle) if target_angle > 0 else 999
                deviation = min(deviation_fwd, deviation_rev)

                if deviation <= orb:
                    closeness_bonus = max(0, (orb - deviation) / orb * 3)
                    # Slow planets (Ju/Sa/Ra/Ke) get importance bonus
                    slow_bonus = 2.0 if tp['abbr'] in ('Ju', 'Sa', 'Ra', 'Ke') else 0.0

                    aspects.append({
                        'transit_planet': tp['abbr'],
                        'natal_planet':   np_['abbr'],
                        'aspect_name':    name_en,
                        'aspect_ja':      name_ja,
                        'angle':          round(diff, 2),
                        'exact_angle':    target_angle,
                        'deviation':      round(deviation, 2),
                        'nature':         nature,
                        'nature_ja':      {'soft': '調和', 'hard': '緊張', 'variable': '可変'}[nature],
                        'strength':       round(strength + closeness_bonus + slow_bonus, 1),
                        'transit_house':  tp['house'],
                        'natal_house':    np_['house'],
                    })

    aspects.sort(key=lambda x: x['strength'], reverse=True)
    return aspects


def calc_transit_summary(transit_jd: float, birth_jd: float,
                         lat: float, lon_geo: float) -> dict:
    """
    Comprehensive transit analysis for a given moment.

    Returns dict with:
        transit_planets, natal_planets, transit_to_natal_aspects,
        transit_inter_aspects, house_activations, dasha_info
    """
    swe.set_sid_mode(swe.SIDM_KRISHNAMURTI)
    sub_table = build_sub_lord_table()

    # Natal chart
    natal_planets = calc_planet_positions(birth_jd, sub_table)
    natal_cusps   = calc_placidus_cusps(birth_jd, lat, lon_geo)
    natal_planets = assign_houses_to_planets(natal_planets, natal_cusps)
    natal_sig     = calc_significators(natal_planets, natal_cusps)

    # Transit chart
    transit_planets = calc_transit_positions(transit_jd, sub_table, natal_cusps)

    # Aspects: transit-to-natal
    t2n_aspects = calc_transit_aspects_to_natal(transit_planets, natal_planets)

    # Aspects: transit-to-transit
    t2t_aspects = calc_aspects(transit_planets)

    # House activation summary: which houses are activated by transit planets
    house_activations = {}
    for h in range(1, 13):
        transiting = [tp['abbr'] for tp in transit_planets if tp['house'] == h]
        house_activations[h] = {
            'transiting_planets': transiting,
            'natal_sign_ja': natal_sig[h]['sign_ja'],
            'natal_lord': natal_sig[h]['D'],
        }

    # Current dasha info
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    moon_data, _ = swe.calc_ut(birth_jd, swe.MOON, flags)
    moon_lon_birth = moon_data[0] % 360.0
    dashas, _, _ = calc_vimshottari_dasha(moon_lon_birth, birth_jd)

    current_md = current_ad = None
    for d in dashas:
        if d['start_jd'] <= transit_jd <= d['end_jd']:
            current_md = d
            for a in d['antardashas']:
                if a['start_jd'] <= transit_jd <= a['end_jd']:
                    current_ad = a
                    break
            break

    return {
        'transit_planets': transit_planets,
        'natal_planets': natal_planets,
        'natal_cusps': natal_cusps,
        'natal_sig': natal_sig,
        'transit_to_natal': t2n_aspects,
        'transit_inter': t2t_aspects,
        'house_activations': house_activations,
        'current_md': current_md,
        'current_ad': current_ad,
        'sub_table': sub_table,
    }


# ---------------------------------------------------------------------------
# Prashna (ホラリー / 問日占) — Horary chart for current moment
# ---------------------------------------------------------------------------

def calc_prashna_chart(query_jd: float, lat: float, lon_geo: float,
                       question: str = '') -> dict:
    """
    Generate a Prashna (horary) chart for the query moment.

    In KP Prashna, the chart erected for the moment of query
    is treated as a natal chart for that question.

    Args:
        query_jd:  Julian Day of the question moment
        lat:       Latitude of the querent
        lon_geo:   Longitude of the querent
        question:  Optional question text for record

    Returns dict with:
        planets, cusps, sig, ruling_planets, dasha (from Moon),
        question_text, query_jd, query_datetime
    """
    swe.set_sid_mode(swe.SIDM_KRISHNAMURTI)
    sub_table = build_sub_lord_table()

    planets = calc_planet_positions(query_jd, sub_table)
    cusps   = calc_placidus_cusps(query_jd, lat, lon_geo)
    planets = assign_houses_to_planets(planets, cusps)

    moon_lon = next(p['lon'] for p in planets if p['abbr'] == 'Mo')
    dashas, start_planet, remaining = calc_vimshottari_dasha(moon_lon, query_jd)

    sig = calc_significators(planets, cusps)
    rp  = calc_ruling_planets(query_jd, lat, lon_geo, sub_table)

    # Dignity
    dignities = calc_planet_dignity(planets)

    # Aspects
    aspects = calc_aspects(planets)

    y, m, d, h = swe.revjul(query_jd, swe.GREG_CAL)

    # KP Prashna analysis: ascendant sub-lord determines YES/NO
    asc_lon = cusps[0]
    _, asc_sl, asc_ssl = get_sub_lords(asc_lon, sub_table)

    return {
        'planets': planets,
        'cusps': cusps,
        'sig': sig,
        'ruling_planets': rp,
        'dashas': dashas,
        'dasha_start_planet': start_planet,
        'dasha_remaining': remaining,
        'aspects': aspects,
        'dignities': dignities,
        'question': question,
        'query_jd': query_jd,
        'query_datetime': f"{int(y):04d}-{int(m):02d}-{int(d):02d} {h:.4f} UT",
        'asc_sub_lord': asc_sl,
        'asc_ssl': asc_ssl,
        'sub_table': sub_table,
    }


# ---------------------------------------------------------------------------
# Horoscope Wheel data (ホロスコープ・ホイール用データ)
# ---------------------------------------------------------------------------

def prepare_wheel_data(planets: list[dict], cusps: list[float]) -> dict:
    """
    Prepare data for drawing a horoscope wheel.

    Returns dict with:
        cusps:  list of 12 {house, lon, sign_en, sign_ja, deg, min, sec}
        planets: list of 9 {abbr, lon, house, sign_ja, display_angle}
        sign_boundaries: list of 12 sign start angles
    """
    cusp_data = []
    for i, lon in enumerate(cusps):
        sign_idx, deg_in = deg_to_sign(lon)
        d, m, s = deg_to_dms(lon)
        cusp_data.append({
            'house': i + 1,
            'lon': lon,
            'sign_en': SIGNS_EN[sign_idx],
            'sign_ja': SIGNS_JA[sign_idx],
            'deg': d, 'min': m, 'sec': s,
        })

    planet_data = []
    for p in planets:
        # Angle on wheel: measured from ASC (cusp 1) going counter-clockwise
        display_angle = (p['lon'] - cusps[0]) % 360.0
        planet_data.append({
            'abbr': p['abbr'],
            'name_ja': PLANET_JA[p['abbr']],
            'lon': p['lon'],
            'house': p['house'],
            'sign_ja': p['sign_ja'],
            'display_angle': display_angle,
            'retrograde': p['retrograde'] and p['abbr'] not in ('Ra', 'Ke'),
        })

    # Sign boundaries (0=Aries start at 0°, Taurus at 30°, etc.)
    sign_boundaries = []
    for i in range(12):
        sign_lon = i * 30.0
        display_angle = (sign_lon - cusps[0]) % 360.0
        sign_boundaries.append({
            'sign_idx': i,
            'sign_en': SIGNS_EN[i],
            'sign_ja': SIGNS_JA[i],
            'lon': sign_lon,
            'display_angle': display_angle,
        })

    return {
        'cusps': cusp_data,
        'planets': planet_data,
        'sign_boundaries': sign_boundaries,
        'asc_lon': cusps[0],
    }


# ---------------------------------------------------------------------------
# Divisional Charts (分割チャート / Varga Charts)
# ---------------------------------------------------------------------------

# D9 Navamsha start signs by element of natal sign
# Fire(0,4,8)→Aries, Earth(1,5,9)→Capricorn, Air(2,6,10)→Libra, Water(3,7,11)→Cancer
_D9_START = {0: 0, 4: 0, 8: 0,  1: 9, 5: 9, 9: 9,  2: 6, 6: 6, 10: 6,  3: 3, 7: 3, 11: 3}


def calc_divisional_chart(planets: list[dict], division: int) -> list[dict]:
    """
    Calculate a divisional (varga) chart for each planet.

    Args:
        planets:  list from calc_planet_positions()
        division: 2=Hora, 3=Drekkana, 9=Navamsha, 10=Dashamsha, 12=Dwadashamsha

    Returns list of dicts:
        {abbr, name_ja, natal_lon, natal_sign_ja, natal_house,
         varga_sign_idx, varga_sign_en, varga_sign_ja, varga_lord}
    """
    results = []
    for p in planets:
        lon = p['lon']
        sign_idx = p['sign_idx']
        deg_in = lon % 30  # degree within sign (0-30)

        if division == 2:
            # D2 Hora: 0-15° = lord A, 15-30° = lord B
            # Odd signs (0,2,4,...): 0-15→Sun(Leo=4), 15-30→Moon(Cancer=3)
            # Even signs (1,3,5,...): 0-15→Moon(Cancer=3), 15-30→Sun(Leo=4)
            is_odd = (sign_idx % 2 == 0)  # Aries=0=odd sign in Vedic
            if is_odd:
                v_sign = 4 if deg_in < 15 else 3   # Leo or Cancer
            else:
                v_sign = 3 if deg_in < 15 else 4

        elif division == 3:
            # D3 Drekkana: 3 decanates of 10° each
            # 1st(0-10°)=same sign, 2nd(10-20°)=5th from sign, 3rd(20-30°)=9th from sign
            part = int(deg_in // 10)
            offsets = [0, 4, 8]
            v_sign = (sign_idx + offsets[min(part, 2)]) % 12

        elif division == 9:
            # D9 Navamsha: 9 parts of 3°20' each
            part = int(deg_in / (30.0 / 9))
            part = min(part, 8)
            start = _D9_START[sign_idx]
            v_sign = (start + part) % 12

        elif division == 10:
            # D10 Dashamsha: 10 parts of 3° each
            part = int(deg_in / 3)
            part = min(part, 9)
            # Odd signs: start from same sign; Even signs: start from 9th
            if sign_idx % 2 == 0:  # odd sign (Aries=0)
                v_sign = (sign_idx + part) % 12
            else:
                v_sign = (sign_idx + 9 + part) % 12

        elif division == 12:
            # D12 Dwadashamsha: 12 parts of 2°30' each
            part = int(deg_in / 2.5)
            part = min(part, 11)
            v_sign = (sign_idx + part) % 12

        else:
            v_sign = sign_idx  # fallback

        v_lord = SIGN_LORD[SIGNS_EN[v_sign]]

        results.append({
            'abbr': p['abbr'],
            'name_ja': PLANET_JA[p['abbr']],
            'natal_lon': lon,
            'natal_sign_ja': p['sign_ja'],
            'natal_house': p['house'],
            'varga_sign_idx': v_sign,
            'varga_sign_en': SIGNS_EN[v_sign],
            'varga_sign_ja': SIGNS_JA[v_sign],
            'varga_lord': v_lord,
        })

    return results


# Names and descriptions of varga charts
VARGA_INFO = {
    2:  ('D2', 'ホーラ',           'Hora',         '富・財運'),
    3:  ('D3', 'ドレッカナ',       'Drekkana',     '兄弟・勇気'),
    9:  ('D9', 'ナヴァムシャ',     'Navamsha',     '配偶者・法（ダルマ）・内面'),
    10: ('D10', 'ダシャムシャ',    'Dashamsha',    '職業・社会的地位'),
    12: ('D12', 'ドヴァダシャムシャ', 'Dwadashamsha', '両親・前世'),
}


def calc_all_vargas(planets: list[dict]) -> dict:
    """
    Calculate all supported divisional charts.

    Returns dict: division_number -> list of varga results
    """
    return {d: calc_divisional_chart(planets, d) for d in VARGA_INFO}


# ---------------------------------------------------------------------------
# Yoga (ヨーガ / 吉兆組合せ) Detection
# ---------------------------------------------------------------------------

# Kendra houses (angles)
_KENDRA = {1, 4, 7, 10}
# Trikona houses (trines)
_TRIKONA = {1, 5, 9}
# Dusthana houses
_DUSTHANA = {6, 8, 12}
# Upachaya houses
_UPACHAYA = {3, 6, 10, 11}


def _planet_in_houses(planets: list[dict], houses: set) -> list[str]:
    """Return planet abbrs that are in any of the given houses."""
    return [p['abbr'] for p in planets if p['house'] in houses]


def _planet_house(planets: list[dict], abbr: str) -> int:
    """Return the house number for a given planet."""
    for p in planets:
        if p['abbr'] == abbr:
            return p['house']
    return 0


def _planet_sign(planets: list[dict], abbr: str) -> int:
    """Return the sign index for a given planet."""
    for p in planets:
        if p['abbr'] == abbr:
            return p['sign_idx']
    return -1


def _house_diff(h1: int, h2: int) -> int:
    """Return house distance from h1 to h2 (1-12)."""
    return ((h2 - h1) % 12) or 12


def calc_yogas(planets: list[dict], cusps: list[float], dignities: list[dict]) -> list[dict]:
    """
    Detect classical Vedic/KP yogas.

    Returns list of dicts:
        {name, name_ja, category, description, planets_involved, strength}

    Categories: 'raja'(王), 'dhana'(財), 'pancha'(偉人), 'chandra'(月),
                'viparita'(逆転), 'general'(一般), 'dosha'(凶)
    """
    yogas = []
    sig = calc_significators(planets, cusps)

    # Build lookups
    p_house = {p['abbr']: p['house'] for p in planets}
    p_sign = {p['abbr']: p['sign_idx'] for p in planets}
    dig_map = {d['abbr']: d for d in dignities}

    # House lord map: house -> sign lord of cusp
    h_lord = {}
    for h in range(1, 13):
        cusp_sign_idx = int(cusps[h-1] // 30) % 12
        h_lord[h] = SIGN_LORD[SIGNS_EN[cusp_sign_idx]]

    # ── 1. Pancha Mahapurusha Yogas (5 Great Person Yogas) ──
    # Mars/Me/Ju/Ve/Sa in kendra AND in own/exalted sign
    mahapurusha = {
        'Ma': ('ルチャカ', 'Ruchaka', '勇気・武勇・リーダーシップの資質'),
        'Me': ('バドラ',   'Bhadra',  '知性・弁才・学問的成功'),
        'Ju': ('ハンサ',   'Hamsa',   '精神性・道徳・教師的資質'),
        'Ve': ('マーラヴィヤ', 'Malavya', '美的感覚・芸術・物質的豊かさ'),
        'Sa': ('シャシャ',  'Shasha',  '権威・政治力・組織運営の才能'),
    }
    for abbr, (name_ja, name_en, desc) in mahapurusha.items():
        h = p_house.get(abbr, 0)
        d = dig_map.get(abbr, {})
        dignity = d.get('dignity', '')
        if h in _KENDRA and dignity in ('exalted', 'own', 'moolatrikona'):
            yogas.append({
                'name': f'{name_en} Yoga',
                'name_ja': f'{name_ja}・ヨーガ',
                'category': 'pancha',
                'category_ja': '五大偉人ヨーガ',
                'description': desc,
                'planets_involved': [abbr],
                'strength': 9,
            })

    # ── 2. Gajakesari Yoga ──
    # Jupiter in kendra from Moon (1/4/7/10 houses from Moon)
    mo_h = p_house.get('Mo', 0)
    ju_h = p_house.get('Ju', 0)
    if mo_h and ju_h:
        diff = _house_diff(mo_h, ju_h)
        if diff in (1, 4, 7, 10):
            yogas.append({
                'name': 'Gajakesari Yoga',
                'name_ja': 'ガージャケーサリー・ヨーガ',
                'category': 'general',
                'category_ja': '一般吉兆',
                'description': '名声・知恵・富に恵まれる。月からケンドラに木星が在住。',
                'planets_involved': ['Mo', 'Ju'],
                'strength': 8,
            })

    # ── 3. Budhaditya Yoga ──
    # Sun and Mercury in the same sign
    if p_sign.get('Su') == p_sign.get('Me') and p_sign.get('Su') is not None:
        yogas.append({
            'name': 'Budhaditya Yoga',
            'name_ja': 'ブダーディティヤ・ヨーガ',
            'category': 'general',
            'category_ja': '一般吉兆',
            'description': '知性・分析力に優れ、学問的成功を示す。太陽と水星が同星座。',
            'planets_involved': ['Su', 'Me'],
            'strength': 6,
        })

    # ── 4. Chandra-Mangala Yoga ──
    # Moon and Mars in same house or opposition
    if p_house.get('Mo') == p_house.get('Ma'):
        yogas.append({
            'name': 'Chandra-Mangala Yoga',
            'name_ja': 'チャンドラ・マンガラ・ヨーガ',
            'category': 'dhana',
            'category_ja': '財運ヨーガ',
            'description': '財運・行動力に恵まれる。月と火星が合。',
            'planets_involved': ['Mo', 'Ma'],
            'strength': 6,
        })

    # ── 5. Raja Yoga ──
    # Lord of a kendra + lord of a trikona in same house or mutual aspect
    kendra_lords = {h_lord[h] for h in _KENDRA}
    trikona_lords = {h_lord[h] for h in _TRIKONA}
    # Planets that are both kendra and trikona lords
    dual_lords = kendra_lords & trikona_lords
    for dl in dual_lords:
        yogas.append({
            'name': 'Raja Yoga (dual lordship)',
            'name_ja': 'ラージャ・ヨーガ（二重支配）',
            'category': 'raja',
            'category_ja': '王のヨーガ',
            'description': f'{dl}（{PLANET_JA[dl]}）がケンドラとトリコーナの両方を支配。権力・地位。',
            'planets_involved': [dl],
            'strength': 8,
        })

    # Kendra lord conjunct trikona lord (different planets)
    for kl in kendra_lords - dual_lords:
        for tl in trikona_lords - dual_lords:
            if kl != tl and p_house.get(kl) == p_house.get(tl) and p_house.get(kl):
                yogas.append({
                    'name': 'Raja Yoga (conjunction)',
                    'name_ja': 'ラージャ・ヨーガ（会合）',
                    'category': 'raja',
                    'category_ja': '王のヨーガ',
                    'description': f'ケンドラ主{kl}とトリコーナ主{tl}が第{p_house[kl]}室で会合。社会的成功。',
                    'planets_involved': sorted([kl, tl]),
                    'strength': 9,
                })

    # ── 6. Viparita Raja Yoga ──
    # Lords of 6/8/12 placed in 6/8/12
    dusthana_lords = [h_lord[h] for h in (6, 8, 12)]
    for i, h in enumerate((6, 8, 12)):
        lord = dusthana_lords[i]
        lord_house = p_house.get(lord, 0)
        if lord_house in _DUSTHANA and lord_house != h:
            yogas.append({
                'name': 'Viparita Raja Yoga',
                'name_ja': 'ヴィパリータ・ラージャ・ヨーガ',
                'category': 'viparita',
                'category_ja': '逆転ヨーガ',
                'description': f'第{h}室主{lord}（{PLANET_JA[lord]}）が第{lord_house}室（ドゥスターナ）に在住。逆境から立ち上がる力。',
                'planets_involved': [lord],
                'strength': 7,
            })

    # ── 7. Neecha Bhanga Raja Yoga (Cancellation of Debilitation) ──
    for d in dignities:
        if d['dignity'] == 'debilitated':
            abbr = d['abbr']
            # Check if the lord of the debilitation sign is in kendra from lagna or Moon
            deb_sign = d['sign_en'] if 'sign_en' in d else SIGNS_EN[p_sign[abbr]]
            deb_lord = SIGN_LORD[deb_sign]
            deb_lord_h = p_house.get(deb_lord, 0)
            if deb_lord_h in _KENDRA:
                yogas.append({
                    'name': 'Neecha Bhanga Raja Yoga',
                    'name_ja': 'ニーチャ・バンガ・ラージャ・ヨーガ',
                    'category': 'raja',
                    'category_ja': '王のヨーガ',
                    'description': f'{abbr}（{PLANET_JA[abbr]}）の減弱がキャンセル。'
                                   f'{deb_lord}（{PLANET_JA[deb_lord]}）がケンドラ第{deb_lord_h}室。困難からの大成功。',
                    'planets_involved': [abbr, deb_lord],
                    'strength': 8,
                })

    # ── 8. Dhana Yoga (Wealth) ──
    # Lords of 2 and 11 in conjunction or mutual kendra
    lord_2 = h_lord[2]
    lord_11 = h_lord[11]
    if lord_2 != lord_11 and p_house.get(lord_2) == p_house.get(lord_11):
        yogas.append({
            'name': 'Dhana Yoga',
            'name_ja': 'ダナ・ヨーガ',
            'category': 'dhana',
            'category_ja': '財運ヨーガ',
            'description': f'第2室主{lord_2}と第11室主{lord_11}が会合。財の蓄積・利益。',
            'planets_involved': sorted([lord_2, lord_11]),
            'strength': 7,
        })

    # ── 9. Kemadruma Yoga (Dosha — Moon isolation) ──
    # No planets in 2nd or 12th from Moon (excluding Ra/Ke/Su)
    relevant = [p for p in planets if p['abbr'] not in ('Ra', 'Ke', 'Su')]
    moon_h = p_house.get('Mo', 0)
    if moon_h:
        h_2nd = ((moon_h - 1 + 1) % 12) + 1
        h_12th = ((moon_h - 1 - 1) % 12) + 1
        flanking = [p for p in relevant if p['house'] in (h_2nd, h_12th) and p['abbr'] != 'Mo']
        if not flanking:
            yogas.append({
                'name': 'Kemadruma Yoga',
                'name_ja': 'ケーマドルマ・ヨーガ',
                'category': 'dosha',
                'category_ja': '凶兆ドーシャ',
                'description': '月の前後に惑星がなく、孤独感・精神的不安定の傾向。ただしケンドラの惑星で緩和。',
                'planets_involved': ['Mo'],
                'strength': 5,
            })

    # ── 10. Amala Yoga ──
    # Benefic (Ju/Ve/Me) in 10th from lagna or Moon
    benefics = {'Ju', 'Ve', 'Me'}
    for p in planets:
        if p['abbr'] in benefics and p['house'] == 10:
            yogas.append({
                'name': 'Amala Yoga',
                'name_ja': 'アマラ・ヨーガ',
                'category': 'general',
                'category_ja': '一般吉兆',
                'description': f'{p["abbr"]}（{PLANET_JA[p["abbr"]]}）が第10室に在住。善行・名声・社会的評価。',
                'planets_involved': [p['abbr']],
                'strength': 6,
            })

    # Sort by strength descending
    yogas.sort(key=lambda y: y['strength'], reverse=True)
    return yogas


# ---------------------------------------------------------------------------
# Report Generation (鑑定レポート生成)
# ---------------------------------------------------------------------------

def generate_report(
    year: int, month: int, day: int, hour: int, minute: int,
    tz: float, lat: float, lon_geo: float
) -> str:
    """
    Generate a comprehensive KP astrology report as formatted text.

    Returns a multi-section text report.
    """
    swe.set_sid_mode(swe.SIDM_KRISHNAMURTI)

    jd = birth_to_jd(year, month, day, hour, minute, tz)
    sub_table = build_sub_lord_table()
    planets = calc_planet_positions(jd, sub_table)
    cusps = calc_placidus_cusps(jd, lat, lon_geo)
    planets = assign_houses_to_planets(planets, cusps)
    moon_lon = next(p['lon'] for p in planets if p['abbr'] == 'Mo')
    dashas, start_planet, remaining = calc_vimshottari_dasha(moon_lon, jd)
    sig = calc_significators(planets, cusps)
    dignities = calc_planet_dignity(planets)
    aspects = calc_aspects(planets)
    yogas = calc_yogas(planets, cusps, dignities)
    vargas = calc_all_vargas(planets)

    aya = swe.get_ayanamsa_ut(jd)
    asc_sign_idx = int(cusps[0] // 30)

    lines = []
    sep = '=' * 60

    # Header
    lines.append(sep)
    lines.append('  KP (クリシュナムルティ・パッダティ) 占星術鑑定レポート')
    lines.append(sep)
    lines.append(f'  生年月日: {year:04d}年{month:02d}月{day:02d}日 {hour:02d}:{minute:02d}')
    lines.append(f'  TZ: {tz:+.1f}h  緯度: {lat:+.4f}°  経度: {lon_geo:+.4f}°')
    lines.append(f'  KP アヤナムシャ: {aya:.4f}°')
    lines.append(f'  ラグナ: {SIGNS_JA[asc_sign_idx]}（{SIGNS_EN[asc_sign_idx]}）')
    lines.append(sep)
    lines.append('')

    # Section 1: Planet positions
    lines.append('【1. 惑星位置】')
    lines.append(f'{"惑星":<12}{"星座":<10}{"度分秒":<12}{"ナクシャトラ":<16}{"NL":<4}{"SL":<4}{"SSL":<4}{"H":<3}{"R":<2}')
    lines.append('-' * 72)
    for p in planets:
        retro = 'R' if (p['retrograde'] or p['abbr'] in ('Ra', 'Ke')) else ''
        d, m, s = p['deg'], p['min'], p['sec']
        lines.append(
            f'{p["abbr"]}({PLANET_JA[p["abbr"]]}){"":<4}'
            f'{p["sign_ja"]:<8}'
            f'{d:02d}°{m:02d}′{s:02d}″{"":<4}'
            f'{p["nak_name"]:<16}'
            f'{p["nl"]:<4}{p["sl"]:<4}{p["ssl"]:<4}'
            f'H{p["house"]:<2}{retro}'
        )
    lines.append('')

    # Section 2: Cusps
    lines.append('【2. カスプ表（プラシダス）】')
    lines.append(f'{"ハウス":<10}{"星座":<10}{"度分秒":<12}{"NL":<4}{"SL":<4}{"SSL":<4}')
    lines.append('-' * 48)
    for i, lon in enumerate(cusps):
        si, _ = deg_to_sign(lon)
        d, m, s = deg_to_dms(lon)
        nl, sl, ssl = get_sub_lords(lon, sub_table)
        lines.append(f'H{i+1:<8}{SIGNS_JA[si]:<8}{d:02d}°{m:02d}′{s:02d}″{"":<4}{nl:<4}{sl:<4}{ssl:<4}')
    lines.append('')

    # Section 3: Dignity
    lines.append('【3. 惑星の品位】')
    for d in dignities:
        lines.append(f'  {d["abbr"]}({d["name_ja"]}) in {d["sign_ja"]}: {d["dignity_ja"]} (スコア {d["dignity_score"]:+d})')
    lines.append('')

    # Section 4: Aspects
    lines.append('【4. アスペクト】')
    for a in aspects:
        vedic = ' [ヴェーダ特殊]' if a['is_vedic_special'] else ''
        lines.append(
            f'  {a["planet1"]}-{a["planet2"]}: {a["aspect_ja"]} '
            f'偏差{a["deviation"]:.1f}° 性質={a["nature_ja"]} 強度={a["strength"]}{vedic}'
        )
    lines.append('')

    # Section 5: Yogas
    lines.append('【5. ヨーガ（吉兆・凶兆組合せ）】')
    if yogas:
        for y in yogas:
            p_str = ','.join(y['planets_involved'])
            lines.append(f'  ★ {y["name_ja"]}（{y["name"]}）')
            lines.append(f'    分類: {y["category_ja"]}  関連惑星: {p_str}  強度: {y["strength"]}/10')
            lines.append(f'    {y["description"]}')
            lines.append('')
    else:
        lines.append('  主要なヨーガは検出されませんでした')
    lines.append('')

    # Section 6: Dasha
    lines.append('【6. ダシャー表（抜粋）】')
    lines.append(f'  出生時ダシャー: {start_planet}({PLANET_JA[start_planet]})  残余: {remaining:.4f}年')
    for d in dashas:
        lines.append(f'  {d["planet"]}({PLANET_JA[d["planet"]]}) '
                     f'{jd_to_date_str(d["start_jd"])} → {jd_to_date_str(d["end_jd"])} '
                     f'({d["years"]:.2f}年)')
    lines.append('')

    # Section 7: Navamsha
    lines.append('【7. ナヴァムシャ（D9）】')
    d9 = vargas.get(9, [])
    for v in d9:
        lines.append(f'  {v["abbr"]}({v["name_ja"]}): {v["natal_sign_ja"]} → D9: {v["varga_sign_ja"]} (主={v["varga_lord"]})')
    lines.append('')

    # Section 8: Significators
    lines.append('【8. シグニフィケーター】')
    for h in range(1, 13):
        s = sig[h]
        a_str = ','.join(s['A']) or '―'
        b_str = ','.join(s['B']) or '―'
        c_str = ','.join(s['C']) or '―'
        lines.append(f'  H{h} {s["sign_ja"]}: A={a_str}  B={b_str}  C={c_str}  D={s["D"]}')
    lines.append('')

    lines.append(sep)
    lines.append('  レポート生成: KP占星術計算ツール (jyotish)')
    lines.append('  計算エンジン: Swiss Ephemeris + KP アヤナムシャ')
    lines.append(sep)

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# KP Condition Score (調子スコア) functions
# ---------------------------------------------------------------------------

# House score baseline for Moon transit (natal house from lagna)
HOUSE_VIBE = {
    1: 80, 2: 60, 3: 10, 4: 30, 5: 90,
    6: -50, 7: 40, 8: -70, 9: 90, 10: 80, 11: 90, 12: -40
}

# Focus weights: (house, multiplier) overrides
FOCUS_WEIGHTS = {
    'overall': {},
    'career':  {10: 2.0, 11: 2.0},
    'health':  {1: 2.0, 6: 3.0, 8: 3.0},
    'fortune': {9: 2.0, 11: 2.0},
}

# House penalties for health (reversed from positive to negative)
_HEALTH_PENALTY_HOUSES = {6, 8}


def _moon_transit_score(transit_jd: float, natal_lagna_lon: float,
                        lat: float, lon_geo: float, sub_table: list,
                        focus: str = 'overall') -> float:
    """
    Compute Moon-transit component score for a given Julian Day.
    Returns value roughly in -100 to +100.
    """
    # Current Moon position
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    moon_data, _ = swe.calc_ut(transit_jd, swe.MOON, flags)
    moon_lon = moon_data[0] % 360.0

    # Current transit cusps to find which house Moon occupies
    transit_cusps = calc_placidus_cusps(transit_jd, lat, lon_geo)

    # Determine Moon's house number (1-12) based on natal lagna as house 1 cusp
    # We compare Moon lon relative to natal lagna
    moon_house = 1
    for h in range(11, 0, -1):
        # Cusp longitude relative to lagna
        cusp_offset = (transit_cusps[h - 1] - natal_lagna_lon) % 360.0
        moon_offset = (moon_lon - natal_lagna_lon) % 360.0
        if moon_offset >= cusp_offset:
            moon_house = h + 1 if h < 12 else 1
            break

    # Simpler approach: use natal-based house numbering
    # House 1 starts at natal lagna; each subsequent house ~30° later
    moon_offset = (moon_lon - natal_lagna_lon) % 360.0
    moon_house = int(moon_offset // 30) + 1  # 1-12

    base_score = HOUSE_VIBE.get(moon_house, 0)

    # Apply focus weight
    weights = FOCUS_WEIGHTS.get(focus, {})
    mult = weights.get(moon_house, 1.0)

    # For health, houses 6/8 penalty is 3x (already negative, so multiply)
    if focus == 'health' and moon_house in _HEALTH_PENALTY_HOUSES:
        score = base_score * mult  # base is negative, mult=3 → larger negative
    else:
        score = base_score * mult

    return max(-100.0, min(100.0, float(score)))


def _rp_harmony_score(transit_jd: float, natal_sig: dict,
                      lat: float, lon_geo: float,
                      sub_table: list, focus: str = 'overall') -> float:
    """
    Compute Ruling-Planet harmony score vs natal significators.
    Returns value in -100 to +100.
    """
    rp = calc_ruling_planets(transit_jd, lat, lon_geo, sub_table)
    rp_set = {
        rp['day_lord'], rp['moon_sign_lord'], rp['moon_star_lord'],
        rp['lagna_sign_lord'], rp['lagna_star_lord'], rp['lagna_sub_lord']
    }

    good_houses = {1, 2, 5, 9, 10, 11}
    bad_houses  = {6, 8, 12}

    weights = FOCUS_WEIGHTS.get(focus, {})

    total = 0.0
    for planet in rp_set:
        # Find houses this planet signifies (D group = sign lord)
        d_houses = [h for h in range(1, 13) if natal_sig[h]['D'] == planet]
        # Also include B group (planet resides in house)
        b_houses = [h for h in range(1, 13) if planet in natal_sig[h]['B']]
        all_houses = set(d_houses + b_houses)

        for h in all_houses:
            mult = weights.get(h, 1.0)
            if h in good_houses:
                total += 1.0 * mult
            elif h in bad_houses:
                total -= 1.0 * mult

    # Normalize: max raw total ≈ 6 planets × 3 houses × mult → scale to -100..+100
    normalized = total / 6.0 * 100.0
    return max(-100.0, min(100.0, normalized))


def _dasha_base_score(birth_jd: float, transit_jd: float,
                      natal_sig: dict, focus: str = 'overall') -> float:
    """
    Compute Dasha base score (slow-changing component).
    Returns value in -100 to +100.
    """
    moon_lon_birth = None
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    moon_data, _ = swe.calc_ut(birth_jd, swe.MOON, flags)
    moon_lon_birth = moon_data[0] % 360.0

    dashas, _, _ = calc_vimshottari_dasha(moon_lon_birth, birth_jd)

    # Find current MD and AD
    current_md_planet = None
    current_ad_planet = None
    for d in dashas:
        if d['start_jd'] <= transit_jd <= d['end_jd']:
            current_md_planet = d['planet']
            for a in d['antardashas']:
                if a['start_jd'] <= transit_jd <= a['end_jd']:
                    current_ad_planet = a['planet']
                    break
            break

    if not current_md_planet:
        return 0.0

    good_houses = {1, 2, 5, 9, 10, 11}
    bad_houses  = {6, 8, 12}
    weights = FOCUS_WEIGHTS.get(focus, {})

    def planet_score(planet):
        d_houses = [h for h in range(1, 13) if natal_sig[h]['D'] == planet]
        b_houses = [h for h in range(1, 13) if planet in natal_sig[h]['B']]
        all_houses = set(d_houses + b_houses)
        s = 0.0
        for h in all_houses:
            mult = weights.get(h, 1.0)
            if h in good_houses:
                s += 20.0 * mult
            elif h in bad_houses:
                s -= 20.0 * mult
        return s

    md_score = planet_score(current_md_planet)
    ad_score = planet_score(current_ad_planet) if current_ad_planet else md_score
    avg = (md_score + ad_score) / 2.0
    return max(-100.0, min(100.0, avg))


def calc_condition_score(
    transit_jd: float,
    natal_lagna: float,
    natal_sig: dict,
    birth_jd: float,
    lat: float,
    lon_geo: float,
    sub_table: list,
    focus: str = 'overall'
) -> float:
    """
    Compute KP condition score for a single point in time.

    Args:
        transit_jd:   Julian Day for the time point to evaluate
        natal_lagna:  Natal ascendant longitude (degrees, sidereal)
        natal_sig:    Natal significator dict from calc_significators()
        birth_jd:     Julian Day of birth (for dasha calculation)
        lat:          Geographic latitude
        lon_geo:      Geographic longitude
        sub_table:    KP sub-lord table from build_sub_lord_table()
        focus:        'overall' | 'career' | 'health' | 'fortune'

    Returns:
        Score in range -100.0 to +100.0
    """
    moon_score  = _moon_transit_score(transit_jd, natal_lagna, lat, lon_geo, sub_table, focus)
    rp_score    = _rp_harmony_score(transit_jd, natal_sig, lat, lon_geo, sub_table, focus)
    dasha_score = _dasha_base_score(birth_jd, transit_jd, natal_sig, focus)

    score = moon_score * 0.50 + rp_score * 0.35 + dasha_score * 0.15
    return round(max(-100.0, min(100.0, score)), 1)


def calc_condition_timeline(
    birth_jd: float,
    lat: float,
    lon_geo: float,
    start_jd: float,
    end_jd: float,
    interval_minutes: int = 30,
    tz_offset_hours: float = 9.0
) -> 'pd.DataFrame':
    """
    Compute KP condition score time series.

    Returns:
        DataFrame with columns:
        ['jd', 'dt_local', 'overall', 'career', 'health', 'fortune',
         'moon_house', 'moon_sign_ja']
    """
    import pandas as pd

    swe.set_sid_mode(swe.SIDM_KRISHNAMURTI)

    # Natal chart calculations (done once)
    sub_table    = build_sub_lord_table()
    natal_planets = calc_planet_positions(birth_jd, sub_table)
    natal_cusps   = calc_placidus_cusps(birth_jd, lat, lon_geo)
    natal_planets = assign_houses_to_planets(natal_planets, natal_cusps)
    natal_sig     = calc_significators(natal_planets, natal_cusps)
    natal_lagna   = natal_cusps[0]  # 1st cusp = ascendant

    interval_days = interval_minutes / 1440.0

    rows = []
    jd = start_jd
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL

    while jd <= end_jd + interval_days * 0.01:
        # Moon position for metadata
        moon_data, _ = swe.calc_ut(jd, swe.MOON, flags)
        moon_lon = moon_data[0] % 360.0
        moon_sign_idx = int(moon_lon // 30)
        moon_offset = (moon_lon - natal_lagna) % 360.0
        moon_house = int(moon_offset // 30) + 1

        # Local datetime
        y_r, mo_r, d_r, h_r = swe.revjul(jd, swe.GREG_CAL)
        local_h = h_r + tz_offset_hours
        dt_local = datetime.datetime(
            int(y_r), int(mo_r), int(d_r), 0, 0
        ) + datetime.timedelta(hours=local_h)

        # Scores for each focus
        scores = {}
        for focus in ('overall', 'career', 'health', 'fortune'):
            scores[focus] = calc_condition_score(
                jd, natal_lagna, natal_sig, birth_jd, lat, lon_geo, sub_table, focus
            )

        rows.append({
            'jd':           jd,
            'dt_local':     dt_local,
            'overall':      scores['overall'],
            'career':       scores['career'],
            'health':       scores['health'],
            'fortune':      scores['fortune'],
            'moon_house':   moon_house,
            'moon_sign_ja': SIGNS_JA[moon_sign_idx],
        })

        jd += interval_days

    return pd.DataFrame(rows)


if __name__ == '__main__':
    main()
