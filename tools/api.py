#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KP Jyotish — FastAPI backend
Serves the Bloomberg-style single-page frontend and calculation API.
"""

from __future__ import annotations

import datetime
import math
from pathlib import Path
from typing import Any, Optional

import swisseph as swe
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import kp_calculator as kp

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="KP Jyotish", version="2.0")

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

# Serve static assets under /static/
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class BirthData(BaseModel):
    year: int
    month: int
    day: int
    hour: int
    minute: int
    tz: float = 9.0
    lat: float = 34.6617
    lon: float = 133.9350


class TransitRequest(BirthData):
    transit_year: Optional[int] = None
    transit_month: Optional[int] = None
    transit_day: Optional[int] = None
    transit_hour: Optional[int] = None
    transit_minute: Optional[int] = None


class PrashnaRequest(BirthData):
    question: str = ""


class ConditionRequest(BirthData):
    range: str = "today"  # today | week | month | year


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------

def _f(v: float, ndigits: int = 4) -> float:
    """Round float to avoid serialisation noise."""
    return round(float(v), ndigits)


def _safe(obj: Any) -> Any:
    """Recursively convert numpy/nan/inf scalars to plain Python types."""
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    # numpy int/float
    try:
        return obj.item()  # type: ignore[union-attr]
    except AttributeError:
        pass
    return obj


# ---------------------------------------------------------------------------
# Shared calculation helper
# ---------------------------------------------------------------------------

def _natal_core(bd: BirthData):
    """Run full natal chart computation and return raw components."""
    jd = kp.birth_to_jd(bd.year, bd.month, bd.day, bd.hour, bd.minute, bd.tz)
    sub_table = kp.build_sub_lord_table()
    planets = kp.calc_planet_positions(jd, sub_table)
    cusps = kp.calc_placidus_cusps(jd, bd.lat, bd.lon)
    planets = kp.assign_houses_to_planets(planets, cusps)
    return jd, sub_table, planets, cusps


# ---------------------------------------------------------------------------
# /api/natal — full chart
# ---------------------------------------------------------------------------

def _dasha_to_json(dashas, now_jd):
    result = []
    for md in dashas:
        is_current_md = md['start_jd'] <= now_jd < md['end_jd']
        ads = []
        for ad in md['antardashas']:
            is_current_ad = is_current_md and ad['start_jd'] <= now_jd < ad['end_jd']
            ads.append({
                'planet': ad['planet'],
                'planet_ja': kp.PLANET_JA.get(ad['planet'], ad['planet']),
                'start': kp.jd_to_date_str(ad['start_jd']),
                'end': kp.jd_to_date_str(ad['end_jd']),
                'months': _f(ad['years'] * 12, 1),
                'is_current': is_current_ad,
            })
        result.append({
            'planet': md['planet'],
            'planet_ja': kp.PLANET_JA.get(md['planet'], md['planet']),
            'start': kp.jd_to_date_str(md['start_jd']),
            'end': kp.jd_to_date_str(md['end_jd']),
            'years': _f(md['years'], 1),
            'is_current': is_current_md,
            'antardashas': ads,
        })
    return result


def _planets_to_json(planets, dignities):
    dig_map = {d['abbr']: d for d in dignities}
    result = []
    for p in planets:
        d, m, s = kp.deg_to_dms(p['lon'] % 30)
        dig = dig_map.get(p['abbr'], {})
        result.append({
            'abbr': p['abbr'],
            'name_ja': kp.PLANET_JA.get(p['abbr'], p['abbr']),
            'sign_ja': p['sign_ja'],
            'sign_en': p['sign'],
            'deg': d, 'min': m, 'sec': s,
            'lon': _f(p['lon']),
            'nak': p['nak'],
            'nl': p['nl'],
            'sl': p['sl'],
            'ssl': p['ssl'],
            'house': p['house'],
            'retrograde': p.get('retrograde', False),
            'dignity': dig.get('dignity', ''),
            'dignity_ja': dig.get('dignity_ja', ''),
            'dignity_score': dig.get('dignity_score', 0),
        })
    return result


def _cusps_to_json(cusps, sub_table):
    result = []
    for i, lon in enumerate(cusps):
        house = i + 1
        sign_idx = int(lon // 30) % 12
        d, m, s = kp.deg_to_dms(lon % 30)
        nl, sl, ssl = kp.get_sub_lords(lon, sub_table)
        result.append({
            'house': house,
            'lon': _f(lon),
            'sign_ja': kp.SIGNS_JA[sign_idx],
            'sign_en': kp.SIGNS_EN[sign_idx],
            'deg': d, 'min': m, 'sec': s,
            'nl': nl, 'sl': sl, 'ssl': ssl,
        })
    return result


def _sig_to_json(sig):
    out = {}
    for house, data in sig.items():
        out[str(house)] = {
            'sign_ja': data['sign_ja'],
            'A': data.get('A', []),
            'B': data.get('B', []),
            'C': data.get('C', []),
            'D': data.get('D', ''),
        }
    return out


def _ruling_to_json(rp):
    rp_set = sorted({
        rp['day_lord'], rp['moon_sign_lord'], rp['moon_star_lord'],
        rp['lagna_sign_lord'], rp['lagna_star_lord'], rp['lagna_sub_lord'],
    })
    return {
        'weekday': rp['weekday'],
        'day_lord': rp['day_lord'],
        'moon_sign_ja': rp['moon_sign_ja'],
        'moon_sign_lord': rp['moon_sign_lord'],
        'moon_star_lord': rp['moon_star_lord'],
        'lagna_sign_ja': rp['asc_sign_ja'],
        'lagna_sign_lord': rp['lagna_sign_lord'],
        'lagna_star_lord': rp['lagna_star_lord'],
        'lagna_sub_lord': rp['lagna_sub_lord'],
        'rp_set': rp_set,
    }


def _aspects_to_json(aspects):
    return [
        {
            'p1': a['planet1'],
            'p2': a['planet2'],
            'type': a['aspect_ja'],
            'deviation': _f(a['deviation'], 2),
            'nature': a['nature'],
            'strength': _f(a['strength'], 1),
            'is_vedic_special': a.get('is_vedic_special', False),
            'applying': a.get('applying', False),
        }
        for a in aspects
    ]


def _yogas_to_json(yogas):
    return [
        {
            'name': y['name'],
            'name_ja': y['name_ja'],
            'category': y['category'],
            'category_ja': y['category_ja'],
            'desc': y['description'],
            'planets': y['planets_involved'],
            'strength': y['strength'],
        }
        for y in yogas
    ]


def _vargas_to_json(vargas):
    out = {}
    for div, rows in vargas.items():
        out[str(div)] = [
            {
                'abbr': r['abbr'],
                'name_ja': kp.PLANET_JA.get(r['abbr'], r['abbr']),
                'natal_sign_ja': r['natal_sign_ja'],
                'varga_sign_ja': r['varga_sign_ja'],
                'varga_lord': r['varga_lord'],
                'vargottama': r['natal_sign_ja'] == r['varga_sign_ja'],
            }
            for r in rows
        ]
    return out


def _wheel_to_json(wheel):
    return {
        'asc_lon': _f(wheel['asc_lon']),
        'planets': [
            {
                'abbr': p['abbr'],
                'lon': _f(p['lon']),
                'display_angle': _f(p['display_angle']),
                'house': p['house'],
                'glyph': p.get('glyph', p['abbr']),
                'retrograde': p.get('retrograde', False),
            }
            for p in wheel['planets']
        ],
        'cusps': [
            {
                'house': c['house'],
                'lon': _f(c['lon']),
                'sign_ja': c['sign_ja'],
                'display_angle': _f(c.get('display_angle', c['lon'])),
            }
            for c in wheel['cusps']
        ],
        'signs': wheel.get('sign_boundaries', []),
    }


@app.post("/api/natal")
def natal(bd: BirthData):
    try:
        jd, sub_table, planets, cusps = _natal_core(bd)
        now_jd = kp.birth_to_jd(
            *_today_parts(), tz=bd.tz
        )

        # Moon longitude for dasha
        moon = next(p for p in planets if p['abbr'] == 'Mo')
        dashas, _nl, _rem = kp.calc_vimshottari_dasha(moon['lon'], jd)

        dignities = kp.calc_planet_dignity(planets)
        sig = kp.calc_significators(planets, cusps)
        rp = kp.calc_ruling_planets(now_jd, bd.lat, bd.lon, sub_table)
        aspects = kp.calc_aspects(planets)
        yogas = kp.calc_yogas(planets, cusps, dignities)
        vargas = kp.calc_all_vargas(planets)
        wheel = kp.prepare_wheel_data(planets, cusps)

        # Ayanamsa
        swe.set_sid_mode(swe.SIDM_KRISHNAMURTI)
        aya = swe.get_ayanamsa_ut(jd)

        # Ascendant sign
        asc_sign_idx = int(cusps[0] // 30) % 12

        response = {
            'birth': {
                'year': bd.year, 'month': bd.month, 'day': bd.day,
                'hour': bd.hour, 'minute': bd.minute, 'tz': bd.tz,
                'lat': bd.lat, 'lon': bd.lon,
                'jd': _f(jd),
                'asc_lon': _f(cusps[0]),
                'asc_sign_ja': kp.SIGNS_JA[asc_sign_idx],
                'asc_sign_en': kp.SIGNS_EN[asc_sign_idx],
                'aya': _f(aya, 3),
            },
            'planets': _planets_to_json(planets, dignities),
            'cusps': _cusps_to_json(cusps, sub_table),
            'dashas': _dasha_to_json(dashas, now_jd),
            'sig': _sig_to_json(sig),
            'ruling': _ruling_to_json(rp),
            'aspects': _aspects_to_json(aspects),
            'yogas': _yogas_to_json(yogas),
            'vargas': _vargas_to_json(vargas),
            'wheel': _wheel_to_json(wheel),
            'sub_table': [
                {
                    'nak': r['nak_name'],
                    'nl': r['nak_lord'],
                    'sl': r['sub_lord'],
                    'ssl': r['ssl_lord'],
                    'start': _f(r['start_lon']),
                    'end': _f(r['end_lon']),
                }
                for r in sub_table
            ],
        }
        return JSONResponse(_safe(response))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _today_parts():
    today = datetime.date.today()
    return today.year, today.month, today.day, 12, 0


# ---------------------------------------------------------------------------
# /api/transit
# ---------------------------------------------------------------------------

@app.post("/api/transit")
def transit(req: TransitRequest):
    try:
        jd, sub_table, planets, cusps = _natal_core(req)

        # Transit time — default to now
        if req.transit_year:
            tr_jd = kp.birth_to_jd(
                req.transit_year,
                req.transit_month or 1,
                req.transit_day or 1,
                req.transit_hour or 12,
                req.transit_minute or 0,
                req.tz,
            )
        else:
            y, m, d, h = swe.revjul(kp.birth_to_jd(
                *_today_parts(), tz=req.tz
            ), swe.GREG_CAL)
            tr_jd = kp.birth_to_jd(int(y), int(m), int(d), 12, 0, req.tz)

        summary = kp.calc_transit_summary(tr_jd, jd, req.lat, req.lon)

        # Convert JD-keyed items to strings
        def tr_planet(p):
            d_, m_, s_ = kp.deg_to_dms(p['lon'] % 30)
            return {
                'abbr': p['abbr'],
                'name_ja': kp.PLANET_JA.get(p['abbr'], p['abbr']),
                'sign_ja': p.get('sign_ja', ''),
                'deg': d_, 'min': m_, 'sec': s_,
                'lon': _f(p['lon']),
                'house': p.get('house', 0),
                'nak': p.get('nak', ''),
                'nl': p.get('nl', ''),
                'sl': p.get('sl', ''),
                'ssl': p.get('ssl', ''),
            }

        response = {
            'transit_date': kp.jd_to_date_str(tr_jd),
            'transit_planets': [tr_planet(p) for p in summary.get('transit_planets', [])],
            'natal_planets': [tr_planet(p) for p in summary.get('natal_planets', [])],
            'transit_to_natal': [
                {
                    'transit': a['transit'],
                    'natal': a['natal'],
                    'aspect': a.get('aspect_ja', a.get('aspect', '')),
                    'deviation': _f(a.get('deviation', 0), 2),
                    'strength': _f(a.get('strength', 0), 1),
                    'nature': a.get('nature', ''),
                }
                for a in summary.get('transit_to_natal', [])
            ],
            'house_activations': summary.get('house_activations', {}),
            'current_md': summary.get('current_md', ''),
            'current_ad': summary.get('current_ad', ''),
        }
        return JSONResponse(_safe(response))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# /api/prashna
# ---------------------------------------------------------------------------

@app.post("/api/prashna")
def prashna(req: PrashnaRequest):
    try:
        now_jd = kp.birth_to_jd(*_today_parts(), tz=req.tz)
        result = kp.calc_prashna_chart(now_jd, req.lat, req.lon, req.question)

        def fmt_planet(p):
            d_, m_, s_ = kp.deg_to_dms(p['lon'] % 30)
            return {
                'abbr': p['abbr'],
                'name_ja': kp.PLANET_JA.get(p['abbr'], p['abbr']),
                'sign_ja': p.get('sign_ja', ''),
                'deg': d_, 'min': m_, 'sec': s_,
                'house': p.get('house', 0),
                'nl': p.get('nl', ''),
                'sl': p.get('sl', ''),
                'ssl': p.get('ssl', ''),
                'retrograde': p.get('retrograde', False),
            }

        cusps_p = result.get('cusps', [])
        asc_sign_idx = int(cusps_p[0] // 30) % 12 if cusps_p else 0
        raw_dashas = result.get('dashas', [])
        response = {
            'question': req.question,
            'chart_time': kp.jd_to_date_str(now_jd),
            'planets': [fmt_planet(p) for p in result.get('planets', [])],
            'asc_sub_lord': result.get('asc_sub_lord', ''),
            'asc_ssl': result.get('asc_ssl', ''),
            'asc_sign_ja': kp.SIGNS_JA[asc_sign_idx],
            'ruling_planets': _ruling_to_json(result['ruling_planets']),
            'dashas': _dasha_to_json(raw_dashas, now_jd)[:5],
        }
        return JSONResponse(_safe(response))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# /api/condition
# ---------------------------------------------------------------------------

@app.post("/api/condition")
def condition(req: ConditionRequest):
    try:
        birth_jd = kp.birth_to_jd(
            req.year, req.month, req.day, req.hour, req.minute, req.tz
        )

        today = datetime.date.today()
        start = datetime.datetime(today.year, today.month, today.day, 0, 0)

        range_map = {
            'today':  (start, start + datetime.timedelta(days=1),   60),
            'week':   (start, start + datetime.timedelta(days=7),   240),
            'month':  (start, start + datetime.timedelta(days=31),  480),
            'year':   (start, start + datetime.timedelta(days=365), 1440),
        }
        t_start, t_end, interval_min = range_map.get(req.range, range_map['today'])

        # Convert to JD
        def dt_to_jd(dt: datetime.datetime) -> float:
            return kp.birth_to_jd(dt.year, dt.month, dt.day, dt.hour, dt.minute, req.tz)

        df = kp.calc_condition_timeline(
            birth_jd, req.lat, req.lon,
            dt_to_jd(t_start), dt_to_jd(t_end),
            interval_minutes=interval_min,
            tz_offset_hours=req.tz,
        )

        rows = []
        for _, row in df.iterrows():
            rows.append({
                'dt': row['dt_local'].isoformat(),
                'overall': float(row['overall']),
                'career': float(row['career']),
                'health': float(row['health']),
                'fortune': float(row['fortune']),
                'moon_house': int(row['moon_house']),
                'moon_sign_ja': row['moon_sign_ja'],
            })
        return JSONResponse({'range': req.range, 'data': rows})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# /api/report
# ---------------------------------------------------------------------------

@app.post("/api/report")
def report(bd: BirthData):
    try:
        text = kp.generate_report(
            bd.year, bd.month, bd.day, bd.hour, bd.minute, bd.tz, bd.lat, bd.lon
        )
        return JSONResponse({'text': text})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
