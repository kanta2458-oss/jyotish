# インド占星術 知識データベース

このディレクトリは、占星術解釈を構造化した JSON 形式の参照データベースです。
既存の markdown 学習教材（`00_introduction/` 〜 `04_kp-system/`）を補完し、
プログラムから利用できる形で占星術知識を体系化しています。

## ファイル一覧

| ファイル | 件数 | 内容 |
|---------|------|------|
| `nakshatras.json` | 27 | ナクシャトラ（月の宿）の詳細プロファイル |
| `planet_in_house.json` | 108 | 9 惑星 × 12 ハウスの解釈 |
| `planet_in_sign.json` | 108 | 9 惑星 × 12 星座の解釈 |
| `yogas.json` | 60+ | 古典ヨーガ（惑星の特殊配置）の辞典 |

## 惑星・星座の略号

### 惑星（9 Grahas）
| 略号 | Sanskrit | 日本語 |
|------|----------|--------|
| Su | Surya | 太陽 |
| Mo | Chandra | 月 |
| Ma | Mangala | 火星 |
| Me | Budha | 水星 |
| Ju | Guru | 木星 |
| Ve | Shukra | 金星 |
| Sa | Shani | 土星 |
| Ra | Rahu | ラーフ（北ノード） |
| Ke | Ketu | ケートゥ（南ノード） |

### 星座（12 Rashis）
| 略号 | Sanskrit | 日本語 |
|------|----------|--------|
| Ar | Mesha | 牡羊 |
| Ta | Vrishabha | 牡牛 |
| Ge | Mithuna | 双子 |
| Ca | Karka | 蟹 |
| Le | Simha | 獅子 |
| Vi | Kanya | 乙女 |
| Li | Tula | 天秤 |
| Sc | Vrishchika | 蠍 |
| Sg | Dhanu | 射手 |
| Cp | Makara | 山羊 |
| Aq | Kumbha | 水瓶 |
| Pi | Meena | 魚 |

## スキーマ

### nakshatras.json
各エントリ：
- `index` (1-27)
- `name_sa` / `name_ja` — ナクシャトラ名
- `lord` — 支配惑星（略号）
- `sign_range` — 黄経範囲（例 "Aries 0°00' - 13°20'"）
- `deity` / `deity_ja` — 守護神
- `symbol` — 象徴
- `gana` — 神族/人間族/羅刹族（deva/manushya/rakshasa）
- `caste` — ヴァルナ（brahmin/kshatriya/vaishya/shudra）
- `nature_ja` — 基本性質
- `body_part` — 身体対応部位
- `direction` — 方位
- `keywords` — 英語キーワード配列
- `personality_ja` — 性格傾向
- `career_ja` — 職業傾向
- `relationships_ja` — 人間関係
- `pada` — 4パダ（各 3°20'）の詳細

### planet_in_house.json
`(planet, house)` で一意。各エントリ：
- `planet` / `planet_ja` — 惑星
- `house` (1-12) — ハウス番号
- `keywords` — 英語キーワード配列
- `general_ja` — 総合的影響
- `career_ja` — 仕事・社会
- `relationships_ja` — 人間関係・家族
- `health_ja` — 健康・体質
- `shadow_ja` — 影の側面・課題
- `kp_note_ja` — KP 視点の補足（該当時のみ）

### planet_in_sign.json
`(planet, sign)` で一意。各エントリ：
- `planet` / `planet_ja` — 惑星
- `sign` / `sign_ja` — 星座
- `dignity` — 品位区分（exalted/moolatrikona/own/friendly/neutral/enemy/debilitated）
- `dignity_ja` — 品位日本語
- `general_ja` — 一般的表現
- `strengths_ja` — 強み
- `challenges_ja` — 課題

### yogas.json
各エントリ：
- `name` / `name_ja` — ヨーガ名
- `category` — raja / dhana / pancha / chandra / viparita / general / dosha / special
- `category_ja` — 日本語カテゴリ
- `source` — 出典古典
- `condition_ja` — 成立条件（日本語）
- `condition_technical` — 技術的条件（英語）
- `effect_ja` — 効果・意味
- `strength` — 1-10 の相対強度
- `planets_involved` — 関与惑星の略号配列
- `cancellation_ja` — キャンセル条件
- `in_calculator` — `tools/kp_calculator.py:calc_yogas()` に実装済みか

## 使い方

### Python
```python
import json
from pathlib import Path

DATA = Path(__file__).parent / "data"
nakshatras = json.loads((DATA / "nakshatras.json").read_text(encoding="utf-8"))

# 月のナクシャトラ情報を取得
moon_nak = next(n for n in nakshatras if n["name_sa"] == "Bharani")
print(moon_nak["personality_ja"])
```

### 検索例
```python
# 「太陽が10室」の解釈を取得
pih = json.loads((DATA / "planet_in_house.json").read_text(encoding="utf-8"))
sun_10 = next(x for x in pih if x["planet"] == "Su" and x["house"] == 10)
```

## 出典・参考

- **Brihat Parashara Hora Shastra (BPHS)** — Jyotish の根本聖典
- **Saravali** by Kalyanavarma
- **Phaladeepika** by Mantreshvara
- **Jataka Parijata** by Vaidyanatha
- **KP Reader 1-6** by K.S. Krishnamurti

## 注意事項

- 解釈文は古典に基づく一般的傾向であり、個別チャートでは
  アスペクト・品位・ナクシャトラ等の文脈で修正される。
- 常に **総合判断** が必要で、単独の配置で結論付けない。
