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


if __name__ == '__main__':
    main()
