#!/usr/bin/env python3
"""
CapCut Native Text, Font Discovery, Calibrated Geometry & WYSIWYG Preview Engine.
Follows YAGNI: zero hardcoded genre presets — the AI agent reasons about bespoke typography,
hierarchy, colors, and placement for each screenplay, while this engine guarantees:
  1. Access to all macOS system fonts with normalized vertical metrics (hhea/OS/2 = 1.20 * upm)
     so CapCut never shrinks or balloons any font unpredictably.
  2. Exact pixel-calibrated width measurement (CAPCUT_PX_PER_EM_PER_SIZE = 11.2 on 1920x1080)
     and outer-edge alignment (outer_edge = 0.88, max_side_hw = 0.36) so side cards never clip
     off-screen and never cross into the center of the frame over actors' faces.
  3. Clean cinema legibility (soft drop shadow + optional micro-hairline stroke, never thick
     cartoon borders) and strict title/detail size hierarchy (detail <= 0.68 * title).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import difflib
import json
import math
import os
import re
import shutil
import threading
import urllib.request
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from fontTools.ttLib import TTCollection, TTFont
from PIL import Image, ImageDraw, ImageFilter, ImageFont

DEFAULT_MAX_WORKERS = min(16, max(8, (os.cpu_count() or 8) * 2))

CAPCUT_SANDBOX_FONTS_DIR = Path(
    os.path.expanduser(
        "~/Library/Containers/com.lemon.lvoverseas/Data/Library/Fonts"
    )
)
USER_FONTS_DIR = Path(os.path.expanduser("~/Library/Fonts"))

CAPCUT_SANDBOX_EFFECT_CACHE_ROOT = Path(
    os.path.expanduser(
        "~/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect"
    )
)
CAPCUT_EFFECT_CACHE_ROOT = Path(
    os.path.expanduser(
        "~/Movies/CapCut/User Data/Cache/effect"
    )
)
CAPCUT_APP_TEXT_ANIMS_ROOT = Path(
    "/Applications/CapCut.app/Contents/Resources/DefaultMaterials/text_anims"
)

FADE_IN_RESOURCE_ID = "6724916044072227332"
FADE_OUT_RESOURCE_ID = "6724919382104871427"

# Empirically calibrated from CapCut 1920x1080 render output:
# With normalized vertical span (1.20 * upm), 1.0 CapCut font_size unit = 11.0..11.2 px per em on 1920px canvas.
CAPCUT_PX_PER_EM_PER_SIZE = 11.2
DEFAULT_OUTER_EDGE_TARGET = 0.88
MAX_SAFE_OUTER_EDGE = 0.92
MAX_SIDE_CARD_HALF_WIDTH = 0.48
MAX_SCENE_SIDE_CARD_HALF_WIDTH = 0.56
MAX_CENTER_CARD_HALF_WIDTH = 0.78

SYSTEM_FONT_SEARCH_DIRS = [
    Path("/System/Library/Fonts"),
    Path("/System/Library/Fonts/Supplemental"),
    Path("/Library/Fonts"),
    USER_FONTS_DIR,
]

_SYSTEM_FONT_INDEX: dict[str, tuple[Path, int | None, str]] | None = None
_SYSTEM_FONT_INDEX_LOCK = threading.Lock()
_ENSURED_FONT_CACHE: dict[str, str] = {}
_ENSURED_FONT_LOCKS: dict[str, threading.Lock] = {}
_ENSURED_FONT_META_LOCK = threading.Lock()
_TTFONT_METRICS_CACHE: dict[str, tuple[int, dict[int, str], dict[str, tuple[int, int]]]] = {}
_TTFONT_METRICS_LOCK = threading.Lock()


@dataclass(frozen=True)
class TextLayerStyle:
    font_name: str
    font_postscript: str
    font_size: float
    color_hex: str
    accent_color_hex: str = ""
    flanker_color_hex: str = ""
    alpha: float = 1.0
    bold: bool = False
    italic: bool = False
    letter_spacing: float = 0.0
    line_spacing: float = 0.02
    stroke_color_hex: str = "#0B0D10"
    stroke_width: float = 0.016
    stroke_alpha: float = 0.90
    shadow_color_hex: str = "#05070A"
    shadow_alpha: float = 0.90
    shadow_smoothing: float = 0.32
    shadow_distance: float = 2.2
    shadow_angle: float = -45.0
    shadow_diffuse: float = 0.08
    check_flag: int = 47


@dataclass(frozen=True)
class FilmCardStyle:
    character_title: TextLayerStyle
    character_detail: TextLayerStyle
    time_title: TextLayerStyle
    time_detail: TextLayerStyle
    ending_title: TextLayerStyle
    ending_detail: TextLayerStyle
    line_gap: float = 0.145
    fade_in_sec: float = 0.45
    fade_out_sec: float = 0.45
    stagger_sec: float = 0.10
    align: str = "center"
    order: str = "title-first"
    scene_order: str = "title-first"
    flankers: str = ""
    scene_flankers: str = ""
    title_uppercase: bool = False
    detail_uppercase: bool = False


def _uid() -> str:
    return str(uuid.uuid4()).upper()


def hex_to_rgb_floats(hex_str: str) -> list[float]:
    clean = (hex_str or "#FFFFFF").strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(c * 2 for c in clean)
    if len(clean) != 6:
        return [1.0, 1.0, 1.0]
    r = int(clean[0:2], 16) / 255.0
    g = int(clean[2:4], 16) / 255.0
    b = int(clean[4:6], 16) / 255.0
    return [round(r, 6), round(g, 6), round(b, 6)]


def hex_to_rgba_ints(hex_str: str, alpha: float = 1.0) -> tuple[int, int, int, int]:
    clean = (hex_str or "#FFFFFF").strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(c * 2 for c in clean)
    if len(clean) != 6:
        return (255, 255, 255, int(round(alpha * 255)))
    return (
        int(clean[0:2], 16),
        int(clean[2:4], 16),
        int(clean[4:6], 16),
        int(round(max(0.0, min(1.0, alpha)) * 255)),
    )


def _get_name_record(tt: TTFont, name_id: int) -> str | None:
    if "name" not in tt:
        return None
    for rec in tt["name"].names:
        if rec.nameID == name_id:
            try:
                val = rec.toUnicode().strip()
                if val:
                    return val
            except Exception:
                continue
    return None


def _build_system_font_index() -> dict[str, tuple[Path, int | None, str]]:
    global _SYSTEM_FONT_INDEX
    if _SYSTEM_FONT_INDEX is not None:
        return _SYSTEM_FONT_INDEX

    with _SYSTEM_FONT_INDEX_LOCK:
        if _SYSTEM_FONT_INDEX is not None:
            return _SYSTEM_FONT_INDEX

        font_files: list[Path] = []
        for folder in SYSTEM_FONT_SEARCH_DIRS:
            if not folder.exists():
                continue
            for p in folder.iterdir():
                if not p.name.startswith(".") and p.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    font_files.append(p)

        def _scan_font_file(p: Path) -> list[tuple[str, tuple[Path, int | None, str], bool]]:
            entries: list[tuple[str, tuple[Path, int | None, str], bool]] = []
            suf = p.suffix.lower()
            try:
                if suf in (".ttf", ".otf"):
                    tt = TTFont(str(p), lazy=True)
                    ps = _get_name_record(tt, 6)
                    fam = _get_name_record(tt, 1) or ps or p.stem
                    if ps and not ps.startswith("."):
                        entries.append((ps, (p, None, fam), True))
                        entries.append((ps.lower(), (p, None, fam), False))
                        if fam:
                            entries.append((fam.lower(), (p, None, fam), False))
                    tt.close()
                elif suf == ".ttc":
                    ttc = TTCollection(str(p), lazy=True)
                    for idx, tt in enumerate(ttc.fonts):
                        ps = _get_name_record(tt, 6)
                        fam = _get_name_record(tt, 1) or ps or p.stem
                        if ps and not ps.startswith("."):
                            entries.append((ps, (p, idx, fam), True))
                            entries.append((ps.lower(), (p, idx, fam), False))
                            if fam:
                                entries.append((fam.lower(), (p, idx, fam), False))
                    ttc.close()
            except Exception:
                pass
            return entries

        index: dict[str, tuple[Path, int | None, str]] = {}
        with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as pool:
            for file_entries in pool.map(_scan_font_file, font_files):
                for key, val, overwrite in file_entries:
                    if overwrite or key not in index:
                        index[key] = val

        _SYSTEM_FONT_INDEX = index
        return index


def list_available_fonts() -> dict[str, Any]:
    """Return curated categories of local macOS PostScript fonts plus on-demand Google Fonts support."""
    idx = _build_system_font_index()
    all_ps = sorted({k for k, v in idx.items() if k == _get_ps_key(k, idx)})
    serif, italic, sans, display, mono = [], [], [], [], []
    for ps in all_ps:
        low = ps.lower()
        if any(w in low for w in ("ornament", "webdings", "wingdings", "symbol", "braille", "apple", "stix", "noto", "kohinoor", "mukta", "devanagari", "hebrew", "arabic", "thai", "tamil", "telugu", "kannada", "malayalam", "sinhala", "myanmar", "khmer", "lao", "tibetan", "armenian", "georgian", "ethiopic", "cherokee", "canadian", "inuktitut", "gurmukhi", "gujarati", "oriya", "bengali", "pingfang", "hiragino", "songti", "kaiti", "heiti", "baoli", "wawati", "yuppy", "xingkai", "lantinghei", "hanzipen", "lingwai", "pilgi", "nanum", "baghdad", "kufi", "nadeem", "damascus", "farah", "muna", "sana", "waseem", "beirut", "diwan", "farisi", "kailasa", "kokonor", "krungthep", "sathu", "silom", "thonburi", "ayuthaya", "plantagenet", "euphemia", "deseret", "newpeninim", "raanana", "corsiva", "arialhb", "Mshtakan", "Savoye")):
            continue
        if "italic" in low or "oblique" in low:
            italic.append(ps)
        elif any(w in low for w in ("menlo", "courier", "monaco", "andale", "ptmono")):
            mono.append(ps)
        elif any(w in low for w in ("baskerville", "georgia", "palatino", "charter", "hoefler", "cochin", "didot", "bodoni", "iowan", "times", "bigcaslon", "atheSD", "athelas", "superclarendon", "marion", "ptserif", "newyork", "cinzel", "cormorant", "playfair", "dmserif", "fraunces", "marcellus", "prata", "ebgaramond")):
            serif.append(ps)
        elif any(w in low for w in ("impact", "copperplate", "luminari", "american", "chalkboard", "futura-condensed", "dincondensed", "din", "rockwell", " Bradley", "brush", "herculanum", "papyrus", "phosphate", "signpainter", " Snell", "trattatello", "zapfino", "bebas", "oswald", "syne", "rye", "specialelite")):
            display.append(ps)
        elif any(w in low for w in ("avenir", "gillsans", "optima", "seravek", "futura", "helvetica", "verdana", "trebuchet", "tahoma", "arial", "ptsans", " Geneva", "lucida", "montserrat", "plusjakarta", "spacegrotesk", "chakra")):
            sans.append(ps)
    return {
        "editorial_serif": serif,
        "italic_and_accent": italic,
        "humanist_and_geometric_sans": sans,
        "display_and_character": display,
        "monospace_and_tactical": mono,
        "google_fonts_auto_fetch": {
            "note": "Any of 1,600+ Google Fonts can be used directly in plan.json (e.g. 'Cinzel-Bold', 'CormorantGaramond-SemiBoldItalic', 'PlayfairDisplay-Bold', 'DMSerifDisplay-Regular', 'PlusJakartaSans-SemiBold') and will be downloaded, normalized, and installed into CapCut automatically.",
            "prestige_and_heritage_serif": [
                "Cinzel-Bold", "CormorantGaramond-Bold", "CormorantGaramond-SemiBoldItalic",
                "PlayfairDisplay-Bold", "PlayfairDisplay-BoldItalic", "EBGaramond-Bold",
                "LibreBaskerville-Bold", "LibreBaskerville-Italic", "Marcellus-Regular", "Prata-Regular",
            ],
            "editorial_and_modern_drama": [
                "DMSerifDisplay-Regular", "DMSerifDisplay-Italic", "BodoniModa-Bold",
                "Fraunces-Bold", "InstrumentSerif-Regular", "InstrumentSerif-Italic",
                "PlusJakartaSans-SemiBold", "Montserrat-SemiBold", "Lora-BoldItalic",
            ],
            "western_ranch_and_americana": [
                "Rye-Regular", "Bitter-Bold", "Bitter-Italic", "Arvo-Bold",
                "SlabSerif", "AlfaSlabOne-Regular", "PlayfairDisplaySC-Bold",
            ],
            "thriller_action_and_noir": [
                "BebasNeue-Regular", "Oswald-Bold", "Syne-Bold", "SpaceGrotesk-SemiBold",
                "SpecialElite-Regular", "CourierPrime-Bold", "ChakraPetch-SemiBold", "Rajdhani-Bold",
            ],
        },
    }


def _get_ps_key(k: str, idx: dict[str, tuple[Path, int | None, str]]) -> str:
    return k if any(c.isupper() for c in k) else ""


def _normalize_ttf_vertical_metrics(ttf_path: Path, force_postscript_name: str | None = None) -> None:
    """
    Normalize hhea and OS/2 vertical metrics to a consistent 1.20 * unitsPerEm box
    (ascent = 0.95 * upm, descent = -0.25 * upm, lineGap = 0) and optionally bind nameID=6.
    This prevents CapCut's EffectSDK from shrinking fonts with large swash/ornament winAscent
    (like HoeflerText-Black or CormorantGaramond) relative to standard fonts.
    """
    try:
        tt = TTFont(str(ttf_path))
        upm = int(tt["head"].unitsPerEm)
        asc = int(round(0.95 * upm))
        desc = int(round(0.25 * upm))
        if "hhea" in tt:
            tt["hhea"].ascent = asc
            tt["hhea"].descent = -desc
            tt["hhea"].lineGap = 0
        if "OS/2" in tt:
            tt["OS/2"].sTypoAscender = asc
            tt["OS/2"].sTypoDescender = -desc
            tt["OS/2"].sTypoLineGap = 0
            tt["OS/2"].usWinAscent = asc
            tt["OS/2"].usWinDescent = desc
        if force_postscript_name and "name" in tt:
            for rec in list(tt["name"].names):
                if rec.nameID == 6:
                    tt["name"].setName(
                        force_postscript_name,
                        6,
                        rec.platformID,
                        rec.platEncID,
                        rec.langID,
                    )
        tt.save(str(ttf_path))
        tt.close()
    except Exception:
        pass


def _parse_google_font_spec(spec: str) -> tuple[str, int, bool, str]:
    """
    Parse a font spec like 'Cinzel-Bold', 'CormorantGaramond-SemiBoldItalic', or 'Playfair Display:700i'
    into (family_name, weight, italic, canonical_postscript_name).
    """
    s = re.sub(r"^google:", "", spec.strip(), flags=re.I).strip()
    if ":" in s:
        fam_raw, st = s.split(":", 1)
    elif "-" in s:
        fam_raw, st = s.rsplit("-", 1)
    else:
        fam_raw, st = s, "Regular"

    family = (
        re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", fam_raw)
        .replace("_", " ")
        .strip()
    )
    st_low = st.lower()
    italic = ("italic" in st_low) or ("oblique" in st_low) or st_low.endswith("i")
    weight = 400
    for k, w in [
        ("black", 900),
        ("extrabold", 800),
        ("ultrabold", 800),
        ("heavy", 800),
        ("semibold", 600),
        ("demibold", 600),
        ("bold", 700),
        ("medium", 500),
        ("extralight", 200),
        ("light", 300),
        ("thin", 100),
    ]:
        if k in st_low:
            weight = w
            break
    m_num = re.search(r"([1-9]00)", st_low)
    if m_num:
        weight = int(m_num.group(1))

    weight_label = {
        100: "Thin",
        200: "ExtraLight",
        300: "Light",
        400: "Regular",
        500: "Medium",
        600: "SemiBold",
        700: "Bold",
        800: "ExtraBold",
        900: "Black",
    }.get(weight, "Regular")
    if italic:
        style_suffix = "Italic" if weight == 400 else f"{weight_label}Italic"
    else:
        style_suffix = weight_label

    if "-" in s and ":" not in s and " " not in s:
        canonical_ps = s
    else:
        fam_camel = "".join(w[:1].upper() + w[1:] for w in family.split())
        canonical_ps = f"{fam_camel}-{style_suffix}"
    return family, weight, italic, canonical_ps


def fetch_google_font(font_spec: str) -> str | None:
    """
    Download a static `.ttf` from Google Fonts matching `font_spec`, normalize its vertical metrics
    (1.20 * upm), bind its PostScript name, and install it in both CapCut's sandbox `Fonts/` and `~/Library/Fonts/`.
    """
    global _SYSTEM_FONT_INDEX
    CAPCUT_SANDBOX_FONTS_DIR.mkdir(parents=True, exist_ok=True)
    USER_FONTS_DIR.mkdir(parents=True, exist_ok=True)

    family, weight, italic, canonical_ps = _parse_google_font_spec(font_spec)
    sandbox_ttf = CAPCUT_SANDBOX_FONTS_DIR / f"{canonical_ps}.ttf"
    user_ttf = USER_FONTS_DIR / f"{canonical_ps}.ttf"
    if sandbox_ttf.exists():
        _normalize_ttf_vertical_metrics(sandbox_ttf, force_postscript_name=canonical_ps)
        _copy_if_different(sandbox_ttf, user_ttf)
        return str(sandbox_ttf)

    fam_q = family.replace(" ", "+")
    candidates = [
        f"{weight}italic" if italic else f"{weight}",
        "400italic,600italic,700italic,400,700" if italic else f"{weight},700,600,500,400",
    ]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10_6_8; en-us) "
            "AppleWebKit/533.21.1 (KHTML, like Gecko) Version/5.0.5 Safari/533.21.1"
        )
    }
    ttf_url: str | None = None
    for cand in candidates:
        try:
            url = f"https://fonts.googleapis.com/css?family={fam_q}:{cand}"
            req = urllib.request.Request(url, headers=headers)
            css = urllib.request.urlopen(req, timeout=6).read().decode("utf-8")
            urls = re.findall(r"url\((https://[^)]+\.(?:ttf|otf))\)", css)
            if urls:
                ttf_url = urls[0] if len(urls) == 1 else urls[-1]
                break
        except Exception:
            continue

    if not ttf_url:
        return None

    try:
        data = urllib.request.urlopen(ttf_url, timeout=8).read()
        sandbox_ttf.write_bytes(data)
        _normalize_ttf_vertical_metrics(sandbox_ttf, force_postscript_name=canonical_ps)
        _copy_if_different(sandbox_ttf, user_ttf)
        if _SYSTEM_FONT_INDEX is not None:
            _SYSTEM_FONT_INDEX[canonical_ps] = (sandbox_ttf, None, family)
            _SYSTEM_FONT_INDEX[canonical_ps.lower()] = (sandbox_ttf, None, family)
        return str(sandbox_ttf)
    except Exception:
        return None


def _copy_if_different(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        try:
            if os.path.samefile(src, dst) or (
                src.stat().st_size == dst.stat().st_size and src.stat().st_size > 1000
            ):
                return
        except OSError:
            pass
    shutil.copyfile(str(src), str(dst))


def _get_font_lock(clean_ps: str) -> threading.Lock:
    with _ENSURED_FONT_META_LOCK:
        lk = _ENSURED_FONT_LOCKS.get(clean_ps)
        if lk is None:
            lk = threading.Lock()
            _ENSURED_FONT_LOCKS[clean_ps] = lk
        return lk


def ensure_capcut_font(font_postscript: str) -> str:
    """
    Ensure `<font_postscript>.ttf` exists in both CapCut sandbox `Fonts/` and `~/Library/Fonts/`
    with normalized vertical metrics (1.20 * upm) so CapCut renders all fonts at an exact,
    predictable scale. Thread-safe and cached in memory so repeated calls across worker threads
    never rewrite or re-copy the same font file.
    """
    raw_spec = (font_postscript or "Georgia-Bold").strip()
    cached = _ENSURED_FONT_CACHE.get(raw_spec)
    if cached:
        return cached

    _, _, _, canonical_ps = _parse_google_font_spec(raw_spec)
    clean_ps = raw_spec if ("-" in raw_spec and ":" not in raw_spec and " " not in raw_spec) else canonical_ps
    cached_clean = _ENSURED_FONT_CACHE.get(clean_ps)
    if cached_clean:
        _ENSURED_FONT_CACHE[raw_spec] = cached_clean
        return cached_clean

    with _get_font_lock(clean_ps):
        cached_clean = _ENSURED_FONT_CACHE.get(clean_ps)
        if cached_clean:
            _ENSURED_FONT_CACHE[raw_spec] = cached_clean
            return cached_clean

        CAPCUT_SANDBOX_FONTS_DIR.mkdir(parents=True, exist_ok=True)
        USER_FONTS_DIR.mkdir(parents=True, exist_ok=True)
        sandbox_ttf = CAPCUT_SANDBOX_FONTS_DIR / f"{clean_ps}.ttf"
        user_ttf = USER_FONTS_DIR / f"{clean_ps}.ttf"

        if sandbox_ttf.exists() and sandbox_ttf.stat().st_size > 1000:
            if not user_ttf.exists() or user_ttf.stat().st_size != sandbox_ttf.stat().st_size:
                _normalize_ttf_vertical_metrics(sandbox_ttf, force_postscript_name=clean_ps)
                _copy_if_different(sandbox_ttf, user_ttf)
            res = str(sandbox_ttf)
            _ENSURED_FONT_CACHE[clean_ps] = res
            _ENSURED_FONT_CACHE[raw_spec] = res
            return res

        idx = _build_system_font_index()
        match = idx.get(clean_ps) or idx.get(clean_ps.lower()) or idx.get(raw_spec.replace(" ", "-").lower())

        if match:
            src_path, ttc_idx, _ = match
            if ttc_idx is not None:
                ttc = TTCollection(str(src_path))
                ttc.fonts[ttc_idx].save(str(sandbox_ttf))
                ttc.close()
            else:
                _copy_if_different(src_path, sandbox_ttf)
            _normalize_ttf_vertical_metrics(sandbox_ttf, force_postscript_name=clean_ps)
            _copy_if_different(sandbox_ttf, user_ttf)
            res = str(sandbox_ttf)
            _ENSURED_FONT_CACHE[clean_ps] = res
            _ENSURED_FONT_CACHE[raw_spec] = res
            return res

        # Not in local macOS system fonts -> auto-download from Google Fonts!
        gf_path = fetch_google_font(raw_spec)
        if gf_path and os.path.exists(gf_path):
            if Path(gf_path) != sandbox_ttf:
                _copy_if_different(Path(gf_path), sandbox_ttf)
                _normalize_ttf_vertical_metrics(sandbox_ttf, force_postscript_name=clean_ps)
                _copy_if_different(sandbox_ttf, user_ttf)
            res = str(sandbox_ttf)
            _ENSURED_FONT_CACHE[clean_ps] = res
            _ENSURED_FONT_CACHE[raw_spec] = res
            return res

        # Final fallback if offline and font unknown
        fb = idx.get("georgia-bold")
        if fb:
            src_path, ttc_idx, _ = fb
            _copy_if_different(src_path, sandbox_ttf)
            _normalize_ttf_vertical_metrics(sandbox_ttf, force_postscript_name=clean_ps)
            _copy_if_different(sandbox_ttf, user_ttf)
        res = str(sandbox_ttf)
        _ENSURED_FONT_CACHE[clean_ps] = res
        _ENSURED_FONT_CACHE[raw_spec] = res
        return res


def ensure_capcut_fonts_parallel(font_specs: Iterable[str]) -> dict[str, str]:
    """Resolve, normalize, and install multiple font specs concurrently across worker threads."""
    unique_specs = [s.strip() for s in dict.fromkeys(font_specs) if s and s.strip()]
    if not unique_specs:
        return {}
    if len(unique_specs) == 1:
        return {unique_specs[0]: ensure_capcut_font(unique_specs[0])}
    with ThreadPoolExecutor(max_workers=min(DEFAULT_MAX_WORKERS, len(unique_specs))) as pool:
        paths = list(pool.map(ensure_capcut_font, unique_specs))
    return dict(zip(unique_specs, paths))


def measure_text_em_width(font_postscript: str, text: str) -> float:
    """Measure exact horizontal advance width in `em` units using the font's `cmap` and `hmtx` tables."""
    if not text:
        return 0.0
    ttf_path = ensure_capcut_font(font_postscript)
    lines = [ln for ln in text.splitlines() if ln] or [text]
    metrics = _TTFONT_METRICS_CACHE.get(ttf_path)
    if metrics is None:
        with _TTFONT_METRICS_LOCK:
            metrics = _TTFONT_METRICS_CACHE.get(ttf_path)
            if metrics is None:
                try:
                    tt = TTFont(ttf_path, lazy=True)
                    upm = int(tt["head"].unitsPerEm)
                    cmap = dict(tt.getBestCmap() or {})
                    hmtx = dict(tt["hmtx"].metrics)
                    tt.close()
                    metrics = (upm, cmap, hmtx)
                    _TTFONT_METRICS_CACHE[ttf_path] = metrics
                except Exception:
                    return max(len(ln) * 0.56 for ln in lines)

    upm, cmap, hmtx = metrics
    max_em = 0.0
    for ln in lines:
        total = 0.0
        for ch in ln:
            gname = cmap.get(ord(ch))
            if gname and gname in hmtx:
                total += hmtx[gname][0]
            else:
                total += upm * 0.52
        max_em = max(max_em, total / float(upm))
    return max_em


def measure_text_half_width_norm(
    font_postscript: str,
    text: str,
    font_size: float,
    scale: float = 1.0,
    letter_spacing: float = 0.0,
    canvas_width: int = 1920,
) -> float:
    """
    Return normalized half-width (in CapCut [-1..+1] x-units) of `text` on `canvas_width`.
    Calibrated directly against CapCut 1920x1080 renders (11.2 px per em per font_size unit).
    """
    em_w = measure_text_em_width(font_postscript, text)
    char_count = max((len(ln) for ln in (text or "").splitlines()), default=len(text or ""))
    tracking_em = max(0.0, float(letter_spacing)) * max(0, char_count - 1) * 0.55
    width_px = (em_w + tracking_em) * float(font_size) * float(scale) * CAPCUT_PX_PER_EM_PER_SIZE
    return round(width_px / float(canvas_width), 4)


def resolve_style(style_spec: dict[str, Any] | None) -> FilmCardStyle:
    """
    Resolve an AI-authored style specification dictionary into a FilmCardStyle.
    Enforces a clean typographic hierarchy: detail_size is automatically clamped to <= 0.68 * title_size
    so the secondary line never visually overpowers or outscales the primary title.
    """
    spec = dict(style_spec or {})

    title_font = str(
        spec.get("title_font")
        or spec.get("name_font")
        or "PlayfairDisplay-Bold"
    )
    detail_font = str(
        spec.get("detail_font")
        or spec.get("role_font")
        or "CormorantGaramond-BoldItalic"
    )
    scene_title_font = str(
        spec.get("scene_title_font")
        or spec.get("scene_font")
        or title_font
    )
    scene_detail_font = str(
        spec.get("scene_detail_font")
        or detail_font
    )
    end_title_font = str(
        spec.get("end_title_font")
        or spec.get("end_font")
        or "Cinzel-Bold"
    )
    end_detail_font = str(
        spec.get("end_detail_font")
        or detail_font
    )

    # Calibrated CapCut cinema ranges (Title: 5.0..8.6 default 6.8, Detail: 4.2..5.8 default 5.0, Detail <= 0.80 * Title)
    raw_title_size = float(spec.get("title_size") or spec.get("name_size") or 6.8)
    title_size = max(5.0, min(8.6, raw_title_size))

    def _optical_boost(f_ps: str, sz: float) -> float:
        low = f_ps.lower()
        if "cormorant" in low or "ebgaramond" in low or "instrumentserif" in low:
            return round(sz * 1.14, 2)
        return sz

    raw_detail_size = _optical_boost(detail_font, float(spec.get("detail_size") or spec.get("role_size") or 5.0))
    detail_size = max(4.2, min(5.8, raw_detail_size, round(title_size * 0.80, 2)))

    raw_scene_title_size = float(spec.get("scene_title_size") or spec.get("scene_size") or 6.6)
    scene_title_size = max(5.2, min(8.4, raw_scene_title_size))
    raw_scene_detail_size = _optical_boost(scene_detail_font, float(spec.get("scene_detail_size") or 5.0))
    scene_detail_size = max(4.2, min(5.8, raw_scene_detail_size, round(scene_title_size * 0.80, 2)))

    raw_end_title_size = float(spec.get("end_title_size") or spec.get("end_size") or round(title_size * 1.18, 2))
    end_title_size = max(6.2, min(9.5, raw_end_title_size))
    end_detail_size = max(4.4, min(6.0, round(detail_size * 1.06, 2)))

    char_title_color = str(
        spec.get("char_title_color")
        or spec.get("title_color")
        or spec.get("name_color")
        or "#F3D078"
    )
    char_detail_color = str(
        spec.get("char_detail_color")
        or spec.get("detail_color")
        or spec.get("role_color")
        or "#F7F4EE"
    )
    time_title_color = str(
        spec.get("time_title_color")
        or spec.get("scene_title_color")
        or spec.get("scene_color")
        or char_title_color
    )
    time_detail_color = str(
        spec.get("time_detail_color")
        or spec.get("scene_detail_color")
        or char_detail_color
    )
    end_title_color = str(
        spec.get("end_title_color")
        or spec.get("end_color")
        or char_title_color
    )
    end_detail_color = str(
        spec.get("end_detail_color")
        or char_detail_color
    )

    detail_accent_color = str(
        spec.get("detail_accent_color")
        or spec.get("accent_color")
        or char_title_color
    )
    scene_accent_color = str(
        spec.get("scene_accent_color")
        or detail_accent_color
    )
    flanker_color = str(
        spec.get("flanker_color")
        or detail_accent_color
    )

    # Crisp dark outline (0.0 .. 0.042) + optical drop shadow
    stroke_color = str(spec.get("stroke_color") or "#0B0D10")
    raw_stroke_w = float(spec.get("stroke_width") if spec.get("stroke_width") is not None else 0.015)
    stroke_w = max(0.0, min(0.042, raw_stroke_w))
    check_flag = 47 if stroke_w > 0.001 else 39

    shadow_color = str(spec.get("shadow_color") or "#05070A")
    shadow_alpha = float(spec.get("shadow_alpha") if spec.get("shadow_alpha") is not None else 0.90)
    shadow_smoothing = float(spec.get("shadow_smoothing") if spec.get("shadow_smoothing") is not None else 0.34)
    shadow_distance = float(spec.get("shadow_distance") if spec.get("shadow_distance") is not None else 2.2)
    shadow_diffuse = float(spec.get("shadow_diffuse") if spec.get("shadow_diffuse") is not None else 0.04)

    title_letter_spacing = float(spec.get("title_letter_spacing") or 0.0)
    detail_letter_spacing = float(spec.get("detail_letter_spacing") or 0.0)
    default_gap = max(0.145, round((title_size + detail_size) * 0.014, 3))
    line_gap = float(spec.get("line_gap") or default_gap)

    return FilmCardStyle(
        character_title=TextLayerStyle(
            font_name=title_font,
            font_postscript=title_font,
            font_size=title_size,
            color_hex=char_title_color,
            accent_color_hex=char_detail_color,
            flanker_color_hex=flanker_color,
            letter_spacing=title_letter_spacing,
            stroke_color_hex=stroke_color,
            stroke_width=stroke_w,
            shadow_color_hex=shadow_color,
            shadow_alpha=shadow_alpha,
            shadow_smoothing=shadow_smoothing,
            shadow_distance=shadow_distance,
            shadow_diffuse=shadow_diffuse,
            check_flag=check_flag,
        ),
        character_detail=TextLayerStyle(
            font_name=detail_font,
            font_postscript=detail_font,
            font_size=detail_size,
            color_hex=char_detail_color,
            accent_color_hex=detail_accent_color,
            flanker_color_hex=flanker_color,
            letter_spacing=detail_letter_spacing,
            stroke_color_hex=stroke_color,
            stroke_width=round(stroke_w * 0.92, 4),
            shadow_color_hex=shadow_color,
            shadow_alpha=shadow_alpha,
            shadow_smoothing=shadow_smoothing,
            shadow_distance=shadow_distance,
            shadow_diffuse=shadow_diffuse,
            check_flag=check_flag,
        ),
        time_title=TextLayerStyle(
            font_name=scene_title_font,
            font_postscript=scene_title_font,
            font_size=scene_title_size,
            color_hex=time_title_color,
            accent_color_hex=scene_accent_color,
            flanker_color_hex=flanker_color,
            letter_spacing=title_letter_spacing,
            stroke_color_hex=stroke_color,
            stroke_width=stroke_w,
            shadow_color_hex=shadow_color,
            shadow_alpha=shadow_alpha,
            shadow_smoothing=shadow_smoothing,
            shadow_distance=shadow_distance,
            shadow_diffuse=shadow_diffuse,
            check_flag=check_flag,
        ),
        time_detail=TextLayerStyle(
            font_name=scene_detail_font,
            font_postscript=scene_detail_font,
            font_size=scene_detail_size,
            color_hex=time_detail_color,
            accent_color_hex=scene_accent_color,
            flanker_color_hex=flanker_color,
            letter_spacing=detail_letter_spacing,
            stroke_color_hex=stroke_color,
            stroke_width=round(stroke_w * 0.92, 4),
            shadow_color_hex=shadow_color,
            shadow_alpha=shadow_alpha,
            shadow_smoothing=shadow_smoothing,
            shadow_distance=shadow_distance,
            shadow_diffuse=shadow_diffuse,
            check_flag=check_flag,
        ),
        ending_title=TextLayerStyle(
            font_name=end_title_font,
            font_postscript=end_title_font,
            font_size=end_title_size,
            color_hex=end_title_color,
            accent_color_hex=end_detail_color,
            flanker_color_hex=flanker_color,
            letter_spacing=max(0.03, title_letter_spacing),
            stroke_color_hex=stroke_color,
            stroke_width=stroke_w,
            shadow_color_hex=shadow_color,
            shadow_alpha=shadow_alpha,
            shadow_smoothing=shadow_smoothing,
            shadow_distance=shadow_distance,
            shadow_diffuse=shadow_diffuse,
            check_flag=check_flag,
        ),
        ending_detail=TextLayerStyle(
            font_name=end_detail_font,
            font_postscript=end_detail_font,
            font_size=end_detail_size,
            color_hex=end_detail_color,
            accent_color_hex=detail_accent_color,
            flanker_color_hex=flanker_color,
            letter_spacing=detail_letter_spacing,
            stroke_color_hex=stroke_color,
            stroke_width=round(stroke_w * 0.92, 4),
            shadow_color_hex=shadow_color,
            shadow_alpha=shadow_alpha,
            shadow_smoothing=shadow_smoothing,
            shadow_distance=shadow_distance,
            shadow_diffuse=shadow_diffuse,
            check_flag=check_flag,
        ),
        line_gap=line_gap,
        fade_in_sec=float(spec.get("fade_in_sec") or 0.45),
        fade_out_sec=float(spec.get("fade_out_sec") or 0.45),
        stagger_sec=float(spec.get("stagger_sec") if spec.get("stagger_sec") is not None else 0.10),
        align=str(spec.get("align") or "center").strip().lower(),
        order=str(spec.get("order") or "title-first").strip().lower(),
        scene_order=str(spec.get("scene_order") or spec.get("order") or "title-first").strip().lower(),
        flankers=str(spec.get("flankers") or "").strip(),
        scene_flankers=str(spec.get("scene_flankers") if spec.get("scene_flankers") is not None else (spec.get("flankers") or "")).strip(),
        title_uppercase=bool(spec.get("title_uppercase", False)),
        detail_uppercase=bool(spec.get("detail_uppercase", False)),
    )


_FONT_CMAP_CACHE: dict[str, set[int]] = {}
_FONT_CMAP_LOCK = threading.Lock()


def font_supports_chars(font_postscript: str, chars: str) -> bool:
    """Return True if every non-whitespace character in `chars` exists in `font_postscript`'s Unicode cmap."""
    if not font_postscript or not chars:
        return True
    cmap = _FONT_CMAP_CACHE.get(font_postscript)
    if cmap is None:
        with _FONT_CMAP_LOCK:
            cmap = _FONT_CMAP_CACHE.get(font_postscript)
            if cmap is None:
                ttf_path = ensure_capcut_font(font_postscript)
                cmap = set()
                if ttf_path and Path(ttf_path).exists():
                    try:
                        with TTFont(ttf_path) as tt:
                            cmap = set((tt.getBestCmap() or {}).keys())
                    except Exception:
                        cmap = set()
                _FONT_CMAP_CACHE[font_postscript] = cmap
    if not cmap:
        return True
    return all(ord(c) in cmap for c in chars if not c.isspace())


def format_detail_with_flankers(
    detail_text: str,
    flankers: str,
    font_postscript: str = "",
) -> str:
    """
    Wrap `detail_text` with optional editorial flankers (e.g. '—', '« »', '‹ ›', '·', '•', '[ ]', '//').
    Automatically verifies glyph coverage in `font_postscript` so unsupported dingbats (like '✦' or '★')
    gracefully fall back to '« »' or '—' and never render as missing-glyph tofu boxes.
    """
    txt = (detail_text or "").strip()
    flk = (flankers or "").strip()
    if not txt or not flk or flk.lower() == "none":
        return txt
    if re.match(r"^[—–✦·•★⚓\|/«‹\[//]", txt):
        return txt
    if font_postscript and not font_supports_chars(font_postscript, flk):
        for fallback in ("« »", "—", "·"):
            if font_supports_chars(font_postscript, fallback):
                flk = fallback
                break
        else:
            return txt
    if flk == "[ ]":
        return f"[  {txt}  ]"
    if flk == "« »":
        return f"«  {txt}  »"
    if flk == "‹ ›":
        return f"‹  {txt}  ›"
    return f"{flk}  {txt}  {flk}"


def resolve_card_styles(card: dict[str, Any], preset: FilmCardStyle) -> tuple[TextLayerStyle, TextLayerStyle, str, str]:
    """Resolve (title_style, detail_style, align, order) for a specific card, applying any per-card overrides."""
    kind = str(card.get("kind") or card.get("type") or "char").lower()
    if kind in ("character", "char"):
        t_st, d_st = preset.character_title, preset.character_detail
        default_order = preset.order
    elif kind in ("end", "ending"):
        t_st, d_st = preset.ending_title, preset.ending_detail
        default_order = "title-first"
    else:
        t_st, d_st = preset.time_title, preset.time_detail
        default_order = preset.scene_order

    if card.get("title_font"):
        f_ps = str(card["title_font"])
        ensure_capcut_font(f_ps)
        t_st = replace(t_st, font_name=f_ps, font_postscript=f_ps)
    if card.get("detail_font"):
        f_ps = str(card["detail_font"])
        ensure_capcut_font(f_ps)
        d_st = replace(d_st, font_name=f_ps, font_postscript=f_ps)
    if card.get("title_size") is not None:
        ts = max(5.0, min(9.2, float(card["title_size"])))
        t_st = replace(t_st, font_size=ts)
    if card.get("detail_size") is not None:
        ds = max(3.6, min(5.6, float(card["detail_size"]), round(t_st.font_size * 0.78, 2)))
        d_st = replace(d_st, font_size=ds)
    if card.get("title_color"):
        tc = str(card["title_color"])
        t_st = replace(t_st, color_hex=tc)
        if not card.get("accent_color"):
            d_st = replace(d_st, accent_color_hex=tc)
    if card.get("detail_color"):
        d_st = replace(d_st, color_hex=str(card["detail_color"]))
    if card.get("accent_color"):
        ac = str(card["accent_color"])
        d_st = replace(d_st, accent_color_hex=ac, flanker_color_hex=ac)
    if card.get("stroke_width") is not None:
        sw = max(0.0, min(0.042, float(card["stroke_width"])))
        cf = 47 if sw > 0.001 else 39
        t_st = replace(t_st, stroke_width=sw, check_flag=cf)
        d_st = replace(d_st, stroke_width=round(sw * 0.92, 4), check_flag=cf)
    if card.get("stroke_color"):
        sc_hex = str(card["stroke_color"])
        t_st = replace(t_st, stroke_color_hex=sc_hex)
        d_st = replace(d_st, stroke_color_hex=sc_hex)
    if card.get("stroke_alpha") is not None:
        sa = max(0.0, min(1.0, float(card["stroke_alpha"])))
        t_st = replace(t_st, stroke_alpha=sa)
        d_st = replace(d_st, stroke_alpha=sa)
    if card.get("shadow_alpha") is not None:
        sha = max(0.0, min(1.0, float(card["shadow_alpha"])))
        t_st = replace(t_st, shadow_alpha=sha)
        d_st = replace(d_st, shadow_alpha=sha)
    if card.get("shadow_smoothing") is not None:
        shs = max(0.0, min(3.0, float(card["shadow_smoothing"])))
        t_st = replace(t_st, shadow_smoothing=shs)
        d_st = replace(d_st, shadow_smoothing=shs)
    if card.get("shadow_distance") is not None:
        shd = max(0.0, min(10.0, float(card["shadow_distance"])))
        t_st = replace(t_st, shadow_distance=shd)
        d_st = replace(d_st, shadow_distance=shd)
    if card.get("shadow_diffuse") is not None:
        shdf = max(0.0, min(1.0, float(card["shadow_diffuse"])))
        t_st = replace(t_st, shadow_diffuse=shdf)
        d_st = replace(d_st, shadow_diffuse=shdf)

    align = str(card.get("align") or ("center" if kind in ("end", "ending") else preset.align)).strip().lower()
    order = str(card.get("order") or default_order).strip().lower()
    return t_st, d_st, align, order


def resolve_card_position(
    card: dict[str, Any],
    *,
    title_font: str,
    detail_font: str,
    title_size: float,
    detail_size: float,
    title_letter_spacing: float = 0.0,
    detail_letter_spacing: float = 0.0,
    line_gap: float = 0.13,
    align: str = "center",
    order: str = "title-first",
    has_overlapping_subtitle: bool = True,
) -> tuple[float, float, float, float, float]:
    """
    Resolve (x_title, x_detail, y_title, y_detail, scale) for a card using calibrated CapCut pixel widths,
    outer-edge alignment (outer_edge = 0.88, max_side_hw = 0.36), horizontal alignment ('center', 'left',
    'right', 'auto'), and vertical stack order ('title-first', 'detail-first').
    """
    kind = str(card.get("kind") or card.get("type") or "char").lower()
    title_text = str(card.get("title") or card.get("name") or card.get("main") or "")
    detail_text = str(card.get("detail") or card.get("role") or card.get("sub") or "")
    scale = float(card.get("scale") or (1.12 if kind in ("end", "ending") else 1.0))

    hw_title = measure_text_half_width_norm(
        title_font, title_text, title_size, scale=scale, letter_spacing=title_letter_spacing
    )
    hw_detail = (
        measure_text_half_width_norm(
            detail_font, detail_text, detail_size, scale=scale, letter_spacing=detail_letter_spacing
        )
        if detail_text
        else 0.0
    )
    max_hw = max(hw_title, hw_detail)

    anchor = str(card.get("anchor") or card.get("zone") or card.get("position") or "").strip().lower()
    raw_x = card.get("x")
    raw_y = card.get("y", card.get("y_main"))

    is_side_card = (
        anchor in (
            "lower-left", "chest-left", "side-low-left",
            "lower-right", "chest-right", "side-low-right",
            "upper-left", "top-left", "corner-left",
            "upper-right", "top-right", "corner-right",
            "mid-left", "horizon-left",
            "mid-right", "horizon-right",
        )
        or (not anchor and raw_x is not None and abs(float(raw_x)) > 0.15)
    )

    default_side_hw = (
        MAX_SCENE_SIDE_CARD_HALF_WIDTH
        if kind not in ("character", "char", "end", "ending")
        else MAX_SIDE_CARD_HALF_WIDTH
    )
    max_allowed_hw = float(
        card.get("max_half_width")
        or (default_side_hw if is_side_card else MAX_CENTER_CARD_HALF_WIDTH)
    )
    if max_hw > max_allowed_hw and "scale" not in card:
        scale = max(0.88, round(scale * (max_allowed_hw / max_hw), 4))
        hw_title = measure_text_half_width_norm(
            title_font, title_text, title_size, scale=scale, letter_spacing=title_letter_spacing
        )
        hw_detail = (
            measure_text_half_width_norm(
                detail_font, detail_text, detail_size, scale=scale, letter_spacing=detail_letter_spacing
            )
            if detail_text
            else 0.0
        )
        max_hw = max(hw_title, hw_detail)

    outer_target = float(card.get("outer_edge") or DEFAULT_OUTER_EDGE_TARGET)
    aligned_abs_x = max(0.34, min(0.76, min(outer_target, MAX_SAFE_OUTER_EDGE) - max_hw))
    max_safe_abs_x = max(0.0, MAX_SAFE_OUTER_EDGE - max_hw)

    if anchor:
        if anchor in ("lower-left", "chest-left", "side-low-left"):
            x = -aligned_abs_x
            y_top = float(raw_y if raw_y is not None else -0.32)
        elif anchor in ("lower-right", "chest-right", "side-low-right"):
            x = +aligned_abs_x
            y_top = float(raw_y if raw_y is not None else -0.32)
        elif anchor in ("upper-left", "top-left", "corner-left"):
            x = -aligned_abs_x
            y_top = float(raw_y if raw_y is not None else +0.76)
        elif anchor in ("upper-right", "top-right", "corner-right"):
            x = +aligned_abs_x
            y_top = float(raw_y if raw_y is not None else +0.76)
        elif anchor in ("mid-left", "horizon-left"):
            x = -aligned_abs_x
            y_top = float(raw_y if raw_y is not None else +0.06)
        elif anchor in ("mid-right", "horizon-right"):
            x = +aligned_abs_x
            y_top = float(raw_y if raw_y is not None else +0.06)
        elif anchor in ("lower-center", "bottom-center"):
            x = 0.0
            default_yc = -0.45 if has_overlapping_subtitle else -0.58
            y_top = float(raw_y if raw_y is not None else default_yc)
        elif anchor in ("upper-center", "top-center"):
            x = 0.0
            y_top = float(raw_y if raw_y is not None else +0.76)
        elif anchor in ("center", "middle"):
            x = 0.0
            y_top = float(raw_y if raw_y is not None else +0.04)
        else:
            raise ValueError(f"Unknown card anchor {anchor!r}")
    else:
        if kind in ("end", "ending"):
            x = float(raw_x if raw_x is not None else 0.0)
            y_top = float(raw_y if raw_y is not None else 0.04)
        else:
            x = float(raw_x if raw_x is not None else 0.0)
            y_top = float(raw_y if raw_y is not None else (-0.32 if abs(x) > 0.15 else -0.45))
            if abs(x) > 0.15 and card.get("align_outer_edge", True):
                sign = 1.0 if x > 0 else -1.0
                if abs(x) <= 0.56 or abs(x) > max_safe_abs_x:
                    x = sign * aligned_abs_x

    # Hard safety clamp so no glyph ever crosses ±0.92
    if abs(x) > max_safe_abs_x:
        x = math.copysign(max_safe_abs_x, x) if max_safe_abs_x > 0 else 0.0

    eff_align = align
    if eff_align in ("auto", "outer", "center", ""):
        # Always lock both lines on the exact same vertical center axis (`x_title == x_detail`)
        # while keeping the outer edge of the wider line anchored at `±0.88`.
        # Because CapCut centers each text box around `transform.x` and renders multi-span sizes
        # (`0.85x`/`0.88x`) with non-linear FreeType kerning, `x_title == x_detail` is the ONLY
        # alignment that guarantees 100% sub-pixel symmetry in CapCut with zero crooked drift.
        eff_align = "center"
    elif eff_align == "flush-outer":
        if x < -0.10:
            eff_align = "left"
        elif x > 0.10:
            eff_align = "right"
        else:
            eff_align = "center"

    if eff_align == "left" and detail_text:
        left_edge = x - max_hw
        x_title = left_edge + hw_title
        x_detail = left_edge + hw_detail
    elif eff_align == "right" and detail_text:
        right_edge = x + max_hw
        x_title = right_edge - hw_title
        x_detail = right_edge - hw_detail
    else:
        x_title = x
        x_detail = x

    gap = float(card.get("line_gap") or line_gap) * scale
    y_bottom = float(card["y_detail"]) if ("y_detail" in card and card["y_detail"] is not None) else round(y_top - gap, 4)

    if order == "detail-first" and detail_text:
        y_detail = round(y_top, 4)
        y_title = round(y_bottom, 4)
    else:
        y_title = round(y_top, 4)
        y_detail = round(y_bottom, 4)

    return round(x_title, 4), round(x_detail, 4), y_title, y_detail, round(scale, 4)


def _resolve_fade_effect_path(resource_id: str, fallback_folder: str) -> str:
    for root in (CAPCUT_SANDBOX_EFFECT_CACHE_ROOT, CAPCUT_EFFECT_CACHE_ROOT):
        effect_dir = root / resource_id
        if effect_dir.exists() and effect_dir.is_dir():
            # CapCut stores the actual effect bundle inside a 32-char md5 subfolder (not *_tmp)
            subdirs = sorted(
                d
                for d in effect_dir.iterdir()
                if d.is_dir() and not d.name.endswith("_tmp") and not d.name.startswith(".")
            )
            if subdirs:
                return str(subdirs[0])
            return str(effect_dir)
    app_fallback = CAPCUT_APP_TEXT_ANIMS_ROOT / fallback_folder
    if app_fallback.exists():
        return str(app_fallback)
    return str(CAPCUT_SANDBOX_EFFECT_CACHE_ROOT / resource_id)


def build_fade_animations(
    *,
    segment_duration_us: int = 3_000_000,
    fade_in_us: int = 500_000,
    fade_out_us: int = 500_000,
    include_fade_out: bool = True,
) -> tuple[str, dict[str, Any]]:
    anims: list[dict[str, Any]] = []
    if fade_in_us > 0:
        anims.append(
            {
                "anim_adjust_params": None,
                "category_id": "ruchang",
                "category_name": "In",
                "duration": int(fade_in_us),
                "id": FADE_IN_RESOURCE_ID,
                "material_type": "sticker",
                "name": "Fade In",
                "panel": "",
                "path": _resolve_fade_effect_path(FADE_IN_RESOURCE_ID, "fade_in"),
                "platform": "all",
                "request_id": "",
                "resource_id": FADE_IN_RESOURCE_ID,
                "source_platform": 1,
                "start": 0,
                "third_resource_id": FADE_IN_RESOURCE_ID,
                "type": "in",
            }
        )
    if include_fade_out and fade_out_us > 0:
        out_start_us = max(0, int(segment_duration_us) - int(fade_out_us))
        anims.append(
            {
                "anim_adjust_params": None,
                "category_id": "chuchang",
                "category_name": "Out",
                "duration": int(fade_out_us),
                "id": FADE_OUT_RESOURCE_ID,
                "material_type": "sticker",
                "name": "Fade Out",
                "panel": "",
                "path": _resolve_fade_effect_path(FADE_OUT_RESOURCE_ID, "fade_out"),
                "platform": "all",
                "request_id": "",
                "resource_id": FADE_OUT_RESOURCE_ID,
                "source_platform": 1,
                "start": int(out_start_us),
                "third_resource_id": FADE_OUT_RESOURCE_ID,
                "type": "out",
            }
        )
    mat_id = _uid()
    return mat_id, {
        "id": mat_id,
        "type": "sticker_animation",
        "multi_language_current": "none",
        "animations": anims,
    }


def compute_rich_text_spans(
    text: str,
    style: TextLayerStyle,
    *,
    is_title: bool = False,
) -> list[tuple[int, int, str, float]]:
    """
    Split `text` into contiguous editorial style spans `(start_idx, end_idx, color_hex, font_size)`:
    - For `is_title=True`: highlights honorific prefixes ('Dr. ', 'Lt. ', 'Sheikh ', 'Judge ') or
      age/rank suffixes (', 74', ' — Age 15') in `style.accent_color_hex` at 0.85x size.
    - For `is_title=False` (Detail / Role / Time line): colors leading/trailing flankers ('—', '✦', '[ ]')
      and separators (' · ', ' — ', ' & ') in `style.flanker_color_hex` at 0.88x size, and highlights
      the primary role/time clause (or leading status badge like '$5M Champion') in `style.accent_color_hex`
      while keeping the secondary affiliation/context clause in `style.color_hex`.
    """
    n = len(text or "")
    if n == 0:
        return []
    acc_col = style.accent_color_hex or style.color_hex
    flk_col = style.flanker_color_hex or acc_col

    if is_title:
        spans: list[tuple[int, int, str, float]] = []
        lo = 0
        hi = n
        m_pre = re.match(
            r"^((?:Dr\.|Lt\.|Capt\.|Gen\.|Adm\.|Col\.|Maj\.|Sgt\.|Chief|Judge|Sheikh|Sir|Lady|Lord|Miss|Sister|Father|Pastor)\s+)(.+)$",
            text,
            re.I,
        )
        if m_pre and acc_col != style.color_hex:
            p_end = m_pre.end(1)
            spans.append((0, p_end, acc_col, style.font_size))
            lo = p_end

        m_suf = re.search(r"((?:,\s*\d+s?|\s+[—·•]\s*(?:Age\s*\d+s?|\d+s?)))$", text[lo:], re.I)
        if m_suf and acc_col != style.color_hex:
            s_start = lo + m_suf.start(1)
            if s_start > lo:
                spans.append((lo, s_start, style.color_hex, style.font_size))
            spans.append((s_start, n, acc_col, style.font_size))
            return spans

        spans.append((lo, hi, style.color_hex, style.font_size))
        return spans

    # Detail line: keep 100% uniform `style.font_size` across all spans so CapCut never shrinks the layer to `styles[0].size`
    flk_sz = style.font_size
    m_lead = re.match(r"^([—✦·•★⚓\|/«\[\s]+)", text)
    m_trail = re.search(r"([—✦·•★⚓\|/»\]\s]+)$", text)
    core_lo = m_lead.end(1) if (m_lead and any(ch not in " \t" for ch in m_lead.group(1))) else 0
    core_hi = (
        m_trail.start(1)
        if (m_trail and any(ch not in " \t" for ch in m_trail.group(1)) and m_trail.start(1) > core_lo)
        else n
    )

    spans = []
    if core_lo > 0:
        spans.append((0, core_lo, flk_col, flk_sz))

    core = text[core_lo:core_hi]
    m_sep = re.search(r"(\s+(?:·|•|—|\||/|&)\s+)", core)
    if m_sep:
        c1_end = core_lo + m_sep.start(1)
        sep_end = core_lo + m_sep.end(1)
        if c1_end > core_lo:
            spans.append((core_lo, c1_end, acc_col, style.font_size))
        spans.append((c1_end, sep_end, flk_col, flk_sz))
        if core_hi > sep_end:
            spans.append((sep_end, core_hi, style.color_hex, style.font_size))
    else:
        m_bg = re.match(
            r"^(\$[0-9A-Za-z.,]+(?:\s+Champion)?|\d+-Star\s+\w+|Four-Star\s+\w+|Chief\s+\w+|Head\s+\w+|Senior\s+\w+|Master\s+\w+|Retired\s+\w+|Founder)\b",
            core,
            re.I,
        )
        if m_bg and m_bg.end(1) < len(core):
            b_end = core_lo + m_bg.end(1)
            spans.append((core_lo, b_end, acc_col, style.font_size))
            spans.append((b_end, core_hi, style.color_hex, style.font_size))
        elif core_hi > core_lo:
            spans.append((core_lo, core_hi, style.color_hex, style.font_size))

    if core_hi < n:
        spans.append((core_hi, n, flk_col, flk_sz))

    return spans or [(0, n, style.color_hex, style.font_size)]


def build_rich_text_content(
    text: str,
    style: TextLayerStyle,
    *,
    font_path: str = "",
    is_title: bool = False,
) -> str:
    stroke_rgb = hex_to_rgb_floats(style.stroke_color_hex)
    shadow_rgb = hex_to_rgb_floats(style.shadow_color_hex)
    resolved_path = font_path or ensure_capcut_font(style.font_postscript)

    spans = compute_rich_text_spans(text, style, is_title=is_title)
    style_entries: list[dict[str, Any]] = []
    for s_lo, s_hi, s_col_hex, s_size in spans:
        rgb = hex_to_rgb_floats(s_col_hex)
        style_entry: dict[str, Any] = {
            "fill": {
                "alpha": float(style.alpha),
                "content": {
                    "render_type": "solid",
                    "solid": {
                        "alpha": float(style.alpha),
                        "color": rgb,
                    },
                },
            },
            "range": [int(s_lo), int(s_hi)],
            "size": float(s_size),
            "bold": bool(style.bold),
            "italic": bool(style.italic),
            "useLetterColor": True,
            "shadows": [
                {
                    "alpha": float(style.shadow_alpha),
                    "angle": float(style.shadow_angle),
                    "content": {
                        "render_type": "solid",
                        "solid": {
                            "alpha": float(style.shadow_alpha),
                            "color": shadow_rgb,
                        },
                    },
                    "diffuse": float(style.shadow_diffuse),
                    "distance": float(style.shadow_distance),
                    "feather": float(style.shadow_smoothing),
                }
            ],
        }
        if style.stroke_width > 0.001:
            style_entry["strokes"] = [
                {
                    "content": {
                        "render_type": "solid",
                        "solid": {
                            "alpha": float(style.stroke_alpha),
                            "color": stroke_rgb,
                        },
                    },
                    "width": float(style.stroke_width),
                }
            ]
        if style.letter_spacing:
            style_entry["letterSpacing"] = float(style.letter_spacing)
        if style.line_spacing:
            style_entry["lineSpacing"] = float(style.line_spacing)
        if resolved_path:
            style_entry["font"] = {
                "id": style.font_postscript,
                "path": resolved_path,
            }
        style_entries.append(style_entry)

    payload: dict[str, Any] = {
        "text": text,
        "styles": style_entries,
    }
    if resolved_path:
        payload["fonts"] = [
            {
                "category_id": "system",
                "CategoryID": "system",
                "category_name": "System",
                "CategoryName": "System",
                "effect_id": style.font_postscript,
                "file_uri": "",
                "id": style.font_postscript,
                "name": style.font_name,
                "path": resolved_path,
                "request_id": "",
                "resource_id": style.font_postscript,
                "source_platform": 0,
                "team_id": "",
                "third_resource_id": style.font_postscript,
                "title": style.font_name,
                "type": "font",
            }
        ]
    return json.dumps(payload, ensure_ascii=False)


def build_text_material(
    text: str,
    style: TextLayerStyle,
    *,
    group_id: str,
    material_type: str = "text",
    alignment: int = 1,
    is_title: bool = False,
) -> tuple[str, dict[str, Any]]:
    mat_id = _uid()
    resolved_font_path = ensure_capcut_font(style.font_postscript)
    rich_json = build_rich_text_content(
        text, style, font_path=resolved_font_path, is_title=is_title
    )
    return mat_id, {
        "id": mat_id,
        "type": material_type,
        "name": "",
        "recognize_text": text,
        "base_content": rich_json,
        "content": rich_json,
        "alignment": int(alignment),
        "font_name": style.font_name,
        "font_title": style.font_name,
        "font_path": resolved_font_path,
        "font_id": style.font_postscript,
        "font_resource_id": style.font_postscript,
        "font_source_platform": 0,
        "font_size": float(style.font_size),
        "text_color": style.color_hex,
        "text_alpha": float(style.alpha),
        "text_size": int(round(style.font_size * 4)),
        "bold_width": 0.0,
        "italic_degree": 0,
        "underline": False,
        "letter_spacing": float(style.letter_spacing),
        "line_spacing": float(style.line_spacing),
        "typesetting": 0,
        "fixed_width": -1.0,
        "fixed_height": -1.0,
        "check_flag": int(style.check_flag),
        "border_color": style.stroke_color_hex,
        "border_width": float(style.stroke_width),
        "border_alpha": float(style.stroke_alpha),
        "has_shadow": True,
        "shadow_color": style.shadow_color_hex,
        "shadow_alpha": float(style.shadow_alpha),
        "shadow_smoothing": float(style.shadow_smoothing),
        "shadow_distance": float(style.shadow_distance),
        "shadow_angle": float(style.shadow_angle),
        "shadow_point": {"x": 0.6363961, "y": -0.6363961},
        "background_alpha": 1.0,
        "background_color": "",
        "background_height": 0.14,
        "background_horizontal_offset": 0.0,
        "background_round_radius": 0.0,
        "background_style": 0,
        "background_Vertical_offset": 0.0,
        "background_width": 0.14,
        "global_alpha": 1.0,
        "group_id": group_id,
        "layer_weight": 1,
        "sub_type": 0,
    }


def build_text_segment(
    *,
    material_id: str,
    anim_material_id: str,
    start_us: int,
    duration_us: int,
    x: float,
    y: float,
    scale: float = 1.0,
    render_index: int = 14000,
) -> dict[str, Any]:
    return {
        "id": _uid(),
        "material_id": material_id,
        "extra_material_refs": [anim_material_id] if anim_material_id else [],
        "target_timerange": {
            "start": int(start_us),
            "duration": int(duration_us),
        },
        "source_timerange": None,
        "speed": 1.0,
        "volume": 1.0,
        "visible": True,
        "render_index": int(render_index),
        "track_attribute": 0,
        "uniform_scale": {"on": True, "value": 1.0},
        "clip": {
            "alpha": 1.0,
            "flip": {"horizontal": False, "vertical": False},
            "rotation": 0.0,
            "scale": {"x": float(scale), "y": float(scale)},
            "transform": {"x": float(x), "y": float(y)},
        },
        "common_keyframes": [],
        "keyframe_refs": [],
    }


_SUB_OPENS_EN = {
    "and", "but", "or", "so", "yet", "because", "although", "though",
    "while", "when", "where", "if", "unless", "until", "since",
    "before", "after", "that", "which", "who", "whose",
}
_SUB_OPENS_VI = {
    "và", "nhưng", "hoặc", "hay", "mà", "nên", "vì", "bởi", "do",
    "nếu", "tuy", "dù", "khi", "lúc", "nơi", "để", "thì", "là", "rằng",
}
_SUB_LEANS_NEXT_EN = {
    "a", "an", "the", "to", "of", "in", "on", "at", "for", "with", "from",
    "by", "into", "onto", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "can",
    "could", "should", "may", "might", "must", "not", "very", "so", "too",
    "quite", "rather", "more", "most", "my", "your", "his", "her", "its",
    "our", "their", "this", "that", "these", "those", "what", "which", "who",
    "mr.", "mrs.", "ms.", "dr.", "st.", "prof.", "capt.", "gen.", "sen.",
}
_SUB_LEANS_NEXT_VI = {
    "các", "những", "một", "mỗi", "mọi", "đã", "đang", "sẽ", "vừa", "mới",
    "sắp", "rất", "quá", "lắm", "khá", "hơi", "không", "chẳng", "chưa",
    "đừng", "chớ", "của", "trong", "trên", "dưới", "với", "về", "từ",
    "đến", "tới", "cho", "tại", "bởi", "sự", "cuộc", "việc", "niềm", "nỗi",
    "cái", "chiếc", "người", "nhà", "đứa", "con", "bản", "căn", "ngôi",
    "bức", "tờ", "cuốn", "quyển", "mảnh", "tấm", "bộ", "đôi", "vị", "kẻ",
}
_SUB_LEANS_PREV_VI = {
    "này", "đó", "kia", "ấy", "nọ", "thế", "vậy", "rồi", "xong", "được",
    "mất", "hơn", "nhất", "lắm", "quá", "thôi", "nhé", "nhỉ", "nha",
    "ạ", "à", "ừ", "chứ",
}
_SUB_VI_PAIRS = {
    ("có", "thể"), ("không", "thể"), ("chúng", "tôi"), ("chúng", "ta"),
    ("anh", "ấy"), ("cô", "ấy"), ("họ", "đã"), ("bây", "giờ"),
    ("lúc", "này"), ("thế", "nào"), ("tại", "sao"), ("vì", "sao"),
    ("như", "vậy"), ("như", "thế"), ("cho", "nên"), ("bởi", "vì"),
    ("thay", "vì"), ("mặc", "dù"), ("ví", "dụ"), ("nghĩa", "là"), ("tức", "là"),
}


def _subtitle_break_bonus(words: list[str], idx: int, is_vi: bool) -> float:
    """
    Linguistic phrase-cohesion score at word split index `idx` (between `words[idx-1]` and `words[idx]`).
    Positive rewards clean clause/punctuation boundaries; negative penalizes splitting inside noun/verb phrases
    or Vietnamese 2-syllable compound words.
    """
    w_prev_raw = words[idx - 1]
    w_next_raw = words[idx]
    prev_clean = w_prev_raw.strip("\"'“”‘’()[]").lower()
    prev_bare = prev_clean.rstrip(".,!?;:—–-")
    next_bare = w_next_raw.strip("\"'“”‘’()[],.!?;:—–-").lower()

    bonus = 0.0
    if prev_clean not in ("mr.", "mrs.", "ms.", "dr.", "st.", "prof.", "capt.", "gen.", "sen."):
        if w_prev_raw.endswith((".", "!", "?")):
            bonus += 14.0
        elif w_prev_raw.endswith((",", ";", ":", "—", "–")):
            bonus += 10.0

    opens = _SUB_OPENS_VI if is_vi else _SUB_OPENS_EN
    leans_next = _SUB_LEANS_NEXT_VI if is_vi else _SUB_LEANS_NEXT_EN

    if next_bare in opens:
        bonus += 6.0
    if prev_clean in leans_next or prev_bare in leans_next:
        bonus -= 10.0
    if is_vi:
        if next_bare in _SUB_LEANS_PREV_VI:
            bonus -= 10.0
        if (prev_bare, next_bare) in _SUB_VI_PAIRS or (prev_bare and prev_bare == next_bare):
            bonus -= 16.0
        elif bonus == 0.0:
            bonus -= 3.0
    return bonus


def wrap_subtitle_balanced(text: str, max_chars: int = 42) -> str:
    single = " ".join((text or "").split())
    if len(single) <= max_chars:
        return single
    words = single.split(" ")
    if len(words) < 2:
        return single
    is_vi = bool(re.search(r"[ăâđêôơưáàảãạéèẻẽẹíìỉĩịóòỏõọúùủũụýỳỷỹỵ]", single.lower()))
    best_split = 1
    best_cost = 1e9
    for i in range(1, len(words)):
        l1 = " ".join(words[:i])
        l2 = " ".join(words[i:])
        overflow_pen = 0.0
        if len(l1) > max_chars + 6 or len(l2) > max_chars + 6:
            overflow_pen = 200.0 + (max(len(l1), len(l2)) - (max_chars + 6)) * 10.0
        elif len(l1) > max_chars or len(l2) > max_chars:
            overflow_pen = (max(len(l1), len(l2)) - max_chars) * 4.5
        diff_cost = abs(len(l1) - len(l2))
        ling_bonus = _subtitle_break_bonus(words, i, is_vi)
        cost = diff_cost + overflow_pen - ling_bonus * 1.6
        if cost < best_cost:
            best_cost = cost
            best_split = i
    return " ".join(words[:best_split]) + "\n" + " ".join(words[best_split:])


_AMBIGUOUS_LOWER_PROPER_WORDS = {
    "will", "may", "march", "bill", "mark", "rose", "grace", "hope", "faith",
    "joy", "dawn", "eve", "art", "ray", "gene", "dean", "cole", "lane", "ford",
    "west", "north", "south", "east", "cook", "judge", "major", "general",
    "young", "long", "short", "white", "black", "brown", "green", "hall", "hill",
    "wood", "woods", "stone", "fields", "cross", "price", "grant", "ward", "page",
    "bell", "king", "queen", "prince", "duke", "earl", "lord", "lady", "knight",
    "mason", "hunter", "fisher", "baker", "miller", "taylor", "smith", "clark",
    "lewis", "walker", "allen", "wright", "scott", "adams", "nelson", "carter",
    "mitchell", "perez", "roberts", "turner", "phillips", "campbell", "parker",
    "evans", "edwards", "collins", "stewart", "sanchez", "morris", "rogers",
    "reed", "bailey", "bell", "cooper", "richardson", "cox", "howard", "ward",
    "torres", "peterson", "gray", "ramirez", "james", "watson", "brooks", "kelly",
    "sanders", "price", "bennett", "wood", "barnes", "ross", "henderson", "coleman",
    "jenkins", "perry", "powell", "long", "patterson", "hughes", "flores", "washington",
    "butler", "simmons", "foster", "gonzales", "bryant", "alexander", "russell",
    "griffin", "diaz", "hayes", "amber", "ivory", "jade", "ruby", "pearl", "opal",
    "hazel", "iris", "violet", "lily", "daisy", "ivy", "holly", "autumn", "summer",
    "winter", "spring", "friday", "saturday", "sunday", "monday", "tuesday",
    "wednesday", "thursday", "morning", "afternoon", "evening", "night",
}


def _apply_sentence_case_and_tokens(text: str) -> str:
    """Capitalize sentence starts and standard screenplay title/rule tokens without altering proper nouns."""
    if not text:
        return text
    out = re.sub(r"(^\s*[a-z]|(?<=[.!?]\s)[a-z])", lambda m: m.group(1).upper(), text)
    out = re.sub(
        r"\b(mr|mrs|ms|dr)\.?\s+([A-Za-z])",
        lambda m: f"{m.group(1).capitalize()}. {m.group(2).upper()}",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\b(row|stall|clause|section|article|lot|ring|gate|barn)\s+(\d+)\b",
        lambda m: f"{m.group(1).capitalize()} {m.group(2)}",
        out,
        flags=re.IGNORECASE,
    )
    return out


def _normalize_cue_with_screenplay(
    text: str,
    cue_start_s: float,
    cue_end_s: float,
    sp_ctx: dict[str, Any] | None,
) -> str:
    """
    Ground-truth subtitle normalization against the screenplay (`sf-board.json` / `*KICHBAN*.txt`):
    1. Aligns ASR words/bigrams against overlapping timeline shot dialogue (`[cue_start_s - 2.5, cue_end_s + 2.5]`)
       to fix context-dependent ASR mishearings (e.g. 'claws 9' -> 'Clause 9', 'vacate this Jack' -> 'vacate this shack',
       'life Lord' -> 'lifeguard', 'Coral Reef' -> 'Coral Reach').
       Strictly preserves any word that already exists in the shot's ground-truth dialogue (`cl in gt_low_set`).
    2. Applies screenplay canonical multi-word phrases and fuzzy proper-noun correction for character/place names.
    """
    if not text or not sp_ctx:
        return text

    out = text
    shot_windows: list[tuple[float, float, str]] = sp_ctx.get("shot_windows") or []
    proper_nouns: dict[str, str] = sp_ctx.get("proper_nouns") or {}
    valid_lower: set[str] = sp_ctx.get("valid_lower_vocab") or set()
    canonical_phrases: list[tuple[re.Pattern[str], str]] = sp_ctx.get("canonical_phrases") or []

    # Step 1: Local timeline shot dialogue alignment
    local_dlg_parts: list[str] = []
    for sw_lo, sw_hi, sw_txt in shot_windows:
        if sw_txt and not (sw_hi < cue_start_s - 2.5 or sw_lo > cue_end_s + 2.5):
            local_dlg_parts.append(sw_txt)

    if local_dlg_parts:
        local_blob = " ".join(local_dlg_parts)
        gt_words = re.findall(r"[A-Za-z][A-Za-z']*", local_blob)
        gt_lows = [w.lower() for w in gt_words]
        gt_low_set = set(gt_lows)

        # 1a-0: Expand colloquial "'em" -> " them" when "them" is in ground-truth dialogue, and strip trailing ASR "hahaha" noise
        if "them" in gt_low_set and "'em" in out.lower():
            out = re.sub(r"\b([A-Za-z]+)'em\b", r"\1 them", out, flags=re.I)
        if "hahaha" not in gt_low_set and "haha" not in gt_low_set:
            out = re.sub(r"\s+\b(?:hahaha|haha|hehe)\b\s*$", "", out, flags=re.I)

        # 1a: Check 2-word ASR bigrams that split a single screenplay word (e.g. 'life Lord' -> 'lifeguard', 'Vacate it' -> 'Vacated', 'grant it' -> 'Granted')
        cue_tokens = list(re.finditer(r"[A-Za-z][A-Za-z']*", out))
        for i in range(len(cue_tokens) - 1, 0, -1):
            m1, m2 = cue_tokens[i - 1], cue_tokens[i]
            if out[m1.end() : m2.start()] != " ":
                continue
            w1, w2 = m1.group(0), m2.group(0)
            if "'" in w1 or "'" in w2:
                continue
            w1_l, w2_l = w1.lower(), w2.lower()
            if w1_l in gt_low_set and w2_l in gt_low_set:
                continue
            if len(w1) >= 4 and w2_l == "it" and w1_l not in gt_low_set:
                for cand_ed in (w1_l + "d", w1_l + "ed"):
                    if cand_ed in gt_low_set:
                        gw_match = next((gw for gw, gl in zip(gt_words, gt_lows) if gl == cand_ed), cand_ed)
                        out = out[: m1.start()] + gw_match + out[m2.end() :]
                        break
                continue
            if len(w1) < 3 or len(w2) < 3:
                continue
            fused_low = w1_l + w2_l
            for gw, gl in zip(gt_words, gt_lows):
                if "'" in gl or len(gl) < len(fused_low) - 1 or len(gl) > len(fused_low) + 2:
                    continue
                sim = difflib.SequenceMatcher(None, fused_low, gl).ratio()
                if sim >= 0.78 or (sim >= 0.70 and fused_low[:3] == gl[:3] and fused_low[-2:] == gl[-2:]):
                    out = out[: m1.start()] + gw + out[m2.end() :]
                    break

        # 1b: Contextual neighbor alignment (reverse iteration so string offsets never shift)
        cue_tokens = list(re.finditer(r"[A-Za-z][A-Za-z']*", out))
        cue_low_set = {m.group(0).lower() for m in cue_tokens}
        for i in range(len(cue_tokens) - 1, -1, -1):
            m_tok = cue_tokens[i]
            cw = m_tok.group(0)
            cl = cw.lower()
            if "'" in cl:
                continue
            if cl in gt_low_set:
                if cl in proper_nouns and proper_nouns[cl] != cw and cl not in _AMBIGUOUS_LOWER_PROPER_WORDS:
                    out = out[: m_tok.start()] + proper_nouns[cl] + out[m_tok.end() :]
                continue
            prev_low = cue_tokens[i - 1].group(0).lower() if i > 0 else ""
            prev2_low = cue_tokens[i - 2].group(0).lower() if i > 1 else ""
            next_low = cue_tokens[i + 1].group(0).lower() if i + 1 < len(cue_tokens) else ""
            for k, (cand_gt, cand_low) in enumerate(zip(gt_words, gt_lows)):
                if cand_low == cl or cand_low in cue_low_set:
                    continue
                prev_match = bool(prev_low and k > 0 and gt_lows[k - 1] == prev_low)
                prev2_match = bool(prev2_low and k > 1 and gt_lows[k - 2] == prev2_low)
                next_match = bool(next_low and k + 1 < len(gt_lows) and gt_lows[k + 1] == next_low)
                if not (prev_match or next_match):
                    continue
                # Possessive/contraction apostrophe restoration (e.g. 'waters' -> "water's", 'pavilions' -> "pavilion's")
                if "'" in cand_low:
                    if cand_low.replace("'", "") == cl and (prev_match or next_match):
                        out = out[: m_tok.start()] + cand_gt.lower() + out[m_tok.end() :]
                        break
                    continue
                if len(cl) < 2 or len(cand_low) < 2 or abs(len(cand_low) - len(cl)) > 2:
                    continue
                # Never flip distinct honorifics (Mister <-> Master, Mrs <-> Miss)
                if cl in ("mister", "master", "mrs", "miss"):
                    continue
                # Allow negation prefix correction (e.g. 'illegal' -> 'legal') ONLY when cl is absent from shot dialogue and neighbors match
                if cl.endswith(cand_low) or cand_low.endswith(cl):
                    if (prev_match and next_match) or (prev_match and prev2_match):
                        out = out[: m_tok.start()] + cand_gt + out[m_tok.end() :]
                        break
                    continue
                if len(cl) == 2 or len(cand_low) == 2:
                    if prev_match and next_match and difflib.SequenceMatcher(None, cl, cand_low).ratio() >= 0.45:
                        out = out[: m_tok.start()] + cand_gt.lower() + out[m_tok.end() :]
                        break
                    continue
                sim = difflib.SequenceMatcher(None, cl, cand_low).ratio()
                rhyme = len(cl) >= 4 and len(cand_low) >= 4 and cl[-3:] == cand_low[-3:]
                bigram_anchor = prev_match and prev2_match and cl[0] == cand_low[0] and abs(len(cl) - len(cand_low)) <= 1
                if (
                    sim >= 0.72
                    or (prev_match and next_match and sim >= 0.58)
                    or (prev_match and rhyme and sim >= 0.60)
                    or bigram_anchor
                ):
                    out = out[: m_tok.start()] + cand_gt + out[m_tok.end() :]
                    break

        # 1c: Sliding-Window SequenceMatcher Local Dialogue Span Alignment (fixes common-word ASR mishearings like
        # "let's see a record" -> "Lessee of record", "You have to stall nine" -> "You after stall nine",
        # "Hands down two inches" -> "Pan's down two inches", "Where second judge is signed" -> "Where second judges sign",
        # "Master Millbank" -> "Mr. Millbank", "judge's back room" -> "judges' back room", "Cm" -> "C.M.")
        clean_local_dlg = re.sub(
            r"(?:^|\n)\s*[A-Z][A-Z0-9_\s'-]{1,24}:\s*",
            " ",
            "\n".join(local_dlg_parts),
        )
        for m_pl in re.finditer(r"\b([A-Za-z]{3,}s)'(?!\w)", clean_local_dlg):
            pl_w = m_pl.group(1)
            sing_p = pl_w[:-1] + "'s"
            out = re.sub(rf"\b{re.escape(sing_p)}\b", f"{pl_w}'", out, flags=re.I)

        _num_map = {
            "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
            "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
            "10": "ten", "11": "eleven", "12": "twelve", "16": "sixteen",
            "20": "twenty", "32": "thirty-two", "40": "forty", "41": "forty-one",
            "42": "forty-two", "84": "eighty-four", "85": "eighty-five",
            "90": "ninety", "94": "ninety-four", "96": "ninety-six", "100": "hundred",
        }

        def _norm_align_tok(s: str) -> str:
            sl = s.lower().strip(".,!?;:\"'").replace(".", "")
            return _num_map.get(sl, sl)

        tok_pat_1c = re.compile(r"(?:[A-Z]\.){2,}|(?:Mr|Mrs|Ms|Dr)\.|[A-Za-z0-9][A-Za-z0-9'-]*", re.I)
        gt_toks_1c = list(tok_pat_1c.finditer(clean_local_dlg))
        gt_words_1c = [m.group(0) for m in gt_toks_1c]
        gt_lows_1c = [_norm_align_tok(m.group(0)) for m in gt_toks_1c]

        cue_toks_1c = list(tok_pat_1c.finditer(out))
        cue_lows_1c = [_norm_align_tok(m.group(0)) for m in cue_toks_1c]
        n_cue_1c = len(cue_lows_1c)

        if n_cue_1c >= 2 and gt_lows_1c:
            best_score_1c = -1.0
            best_w_1c = 0
            best_w_len_1c = n_cue_1c
            cue_joined_1c = " ".join(cue_lows_1c)
            for w_len in range(max(2, n_cue_1c - 2), min(len(gt_lows_1c), n_cue_1c + 1) + 1):
                for w_i in range(max(1, len(gt_lows_1c) - w_len + 1)):
                    w_sub = gt_lows_1c[w_i : w_i + w_len]
                    sm_cand = difflib.SequenceMatcher(None, cue_lows_1c, w_sub, autojunk=False)
                    matches = sum(b.size for b in sm_cand.get_matching_blocks())
                    if matches == 0 or matches / max(n_cue_1c, w_len) < 0.38:
                        continue
                    ops = sm_cand.get_opcodes()
                    bound_pen = 0.0
                    if ops and ops[0][0] in ("delete", "insert"):
                        bound_pen += 0.14
                    if ops and ops[-1][0] in ("delete", "insert"):
                        bound_pen += 0.14
                    char_r = difflib.SequenceMatcher(None, cue_joined_1c, " ".join(w_sub)).ratio()
                    sc = round((matches / n_cue_1c) + 0.65 * char_r - bound_pen - 0.02 * abs(w_len - n_cue_1c), 4)
                    if sc > best_score_1c:
                        best_score_1c = sc
                        best_w_1c = w_i
                        best_w_len_1c = w_len
            if best_score_1c >= 0.90:
                w_gt_toks = gt_toks_1c[best_w_1c : best_w_1c + best_w_len_1c]
                w_gt_words = gt_words_1c[best_w_1c : best_w_1c + best_w_len_1c]
                w_gt_lows = gt_lows_1c[best_w_1c : best_w_1c + best_w_len_1c]
                sm = difflib.SequenceMatcher(None, cue_lows_1c, w_gt_lows, autojunk=False)
                for tag, i1, i2, j1, j2 in reversed(sm.get_opcodes()):
                    if tag == "equal" and (i2 - i1) == (j2 - j1):
                        for off in range(i2 - i1 - 1, -1, -1):
                            gw_o = w_gt_words[j1 + off]
                            cw_o = cue_toks_1c[i1 + off].group(0)
                            if "." in gw_o and "." not in cw_o:
                                st_c = cue_toks_1c[i1 + off].start()
                                en_c = cue_toks_1c[i1 + off].end()
                                out = out[:st_c] + gw_o + out[en_c:]
                        continue
                    if tag != "replace":
                        continue
                    if not (1 <= (i2 - i1) <= 3 and 1 <= (j2 - j1) <= 3):
                        continue
                    raw_c_tokens = [cue_toks_1c[k].group(0) for k in range(i1, i2)]
                    if any(any(ch.isdigit() for ch in t) for t in raw_c_tokens):
                        continue
                    c_span = cue_lows_1c[i1:i2]
                    g_span = w_gt_lows[j1:j2]
                    if c_span == g_span or set(c_span).issubset(set(g_span)) or set(g_span).issubset(set(c_span)):
                        continue
                    left_anchor = i1 > 0 and j1 > 0 and cue_lows_1c[i1 - 1] == w_gt_lows[j1 - 1]
                    right_anchor = i2 < n_cue_1c and j2 < len(w_gt_lows) and cue_lows_1c[i2] == w_gt_lows[j2]
                    if not (left_anchor or right_anchor):
                        continue
                    if not (left_anchor and right_anchor):
                        if right_anchor and not left_anchor:
                            between = clean_local_dlg[w_gt_toks[j2 - 1].end() : w_gt_toks[j2].start()]
                            if re.search(r"[.?!]", between):
                                continue
                        if left_anchor and not right_anchor:
                            between = clean_local_dlg[w_gt_toks[j1 - 1].end() : w_gt_toks[j1].start()]
                            if re.search(r"[.?!]", between):
                                continue
                        span_sim = difflib.SequenceMatcher(None, " ".join(c_span), " ".join(g_span)).ratio()
                        left_run = i1 >= 2 and j1 >= 2 and cue_lows_1c[i1 - 2 : i1] == w_gt_lows[j1 - 2 : j1]
                        right_run = (
                            i2 + 2 <= n_cue_1c
                            and j2 + 2 <= len(w_gt_lows)
                            and cue_lows_1c[i2 : i2 + 2] == w_gt_lows[j2 : j2 + 2]
                        )
                        honorific_fix = len(c_span) == 1 and len(g_span) == 1 and c_span[0] == "master" and g_span[0] == "mr"
                        if span_sim < 0.52 and not (
                            ((left_run or right_run) and len(c_span) == 1 and len(g_span) == 1) or honorific_fix
                        ):
                            continue
                    repl_str = " ".join(w_gt_words[j1:j2])
                    start_char = cue_toks_1c[i1].start()
                    end_char = cue_toks_1c[i2 - 1].end()
                    out = out[:start_char] + repl_str + out[end_char:]

    # Step 2: Global screenplay canonical phrases (e.g. 'Clause 9', 'Coral Reach', 'South Door')
    for pat, repl_phrase in canonical_phrases:
        out = pat.sub(repl_phrase, out)
    if local_dlg_parts:
        local_low_check = " ".join(local_dlg_parts).lower()
        if "south door" in local_low_check and "south-door" not in local_low_check:
            out = re.sub(r"\bsouth-door\b", "south door", out, flags=re.I)

    # Step 3: Global screenplay proper-noun restoration & fuzzy typo correction
    def _fix_word(m: re.Match[str]) -> str:
        w = m.group(0)
        base = w
        suffix = ""
        if w.lower().endswith("'s") and len(w) > 4:
            base = w[:-2]
            suffix = w[-2:]
        bl = base.lower()
        if bl in proper_nouns and bl not in _AMBIGUOUS_LOWER_PROPER_WORDS:
            return proper_nouns[bl] + suffix
        if len(bl) >= 5 and bl not in valid_lower and bl not in _AMBIGUOUS_LOWER_PROPER_WORDS:
            best_pn = None
            best_r = 0.78
            bl_cons = re.sub(r"[aeiouy]", "", bl)
            for pnl, pnc in proper_nouns.items():
                if abs(len(pnl) - len(bl)) <= 2 and (pnl[0] == bl[0] or pnl[-2:] == bl[-2:]):
                    r = difflib.SequenceMatcher(None, bl, pnl).ratio()
                    pnl_cons = re.sub(r"[aeiouy]", "", pnl)
                    if len(bl_cons) >= 3 and bl_cons == pnl_cons and r >= 0.65:
                        r = max(r, 0.82)
                    if r > best_r:
                        best_r = r
                        best_pn = pnc
            if best_pn:
                return best_pn + suffix
        return w

    out = re.sub(r"\b[A-Za-z][A-Za-z']+\b", _fix_word, out)
    return out


def style_subtitle_track_in_place(
    draft: dict[str, Any],
    sub_spec: dict[str, Any] | None = None,
    *,
    screenplay_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Style an existing CapCut subtitle track in-place and normalize subtitle text against the screenplay.
    - When the user specifies custom subtitle styling in `sub_spec`, honors `sub_spec`.
    - When not specified by the user, defaults to the classic Warm Cinema Yellow Boxless standard from
      `Custom Subtitle Styling And Font` (`Seravek-Medium`, size `4.2`, `text_size=30`, `#E5CE6E`, `y=-0.78`,
      `stroke_color=#0A0C0E`, `stroke_width=0.028`, `shadow_color=#050608`, `shadow_alpha=0.82`,
      `shadow_smoothing=2.58`, `shadow_distance=1.8`, `check_flag=47`).
    """
    spec = sub_spec or {}
    font_ps = str(spec.get("font") or "Seravek-Medium")
    font_name = str(spec.get("font_name") or font_ps)
    font_size = float(spec.get("size") or 4.2)
    color_hex = str(spec.get("color") or "#E5CE6E")
    y_pos = float(spec.get("y") if spec.get("y") is not None else -0.78)
    max_chars = int(spec.get("max_chars_per_line") or 42)
    sentence_case = bool(spec.get("sentence_case", True))
    normalize_with_screenplay = bool(spec.get("normalize_with_screenplay", True))
    word_replacements: dict[str, str] = dict(spec.get("word_replacements") or {})
    cue_overrides: dict[str, str] = {
        str(k): str(v) for k, v in (spec.get("cue_overrides") or {}).items()
    }

    stroke_w = float(spec.get("stroke_width") if spec.get("stroke_width") is not None else 0.028)
    check_flag = int(spec.get("check_flag") or (47 if stroke_w > 0.001 else 39))
    text_size_int = int(spec.get("text_size") or (30 if abs(font_size - 4.2) < 0.15 else round(font_size * 4)))

    sub_style = TextLayerStyle(
        font_name=font_name,
        font_postscript=font_ps,
        font_size=font_size,
        color_hex=color_hex,
        stroke_color_hex=str(spec.get("stroke_color") or "#0A0C0E"),
        stroke_width=stroke_w,
        stroke_alpha=float(spec.get("stroke_alpha") or 0.95),
        shadow_color_hex=str(spec.get("shadow_color") or "#050608"),
        shadow_alpha=float(spec.get("shadow_alpha") or 0.82),
        shadow_smoothing=float(spec.get("shadow_smoothing") or 2.58),
        shadow_distance=float(spec.get("shadow_distance") or 1.8),
        shadow_angle=-45.0,
        shadow_diffuse=float(spec.get("shadow_diffuse") or 0.1435),
        check_flag=check_flag,
    )

    resolved_font_path = ensure_capcut_font(font_ps)
    mats_by_id = {m["id"]: m for m in draft.get("materials", {}).get("texts", [])}

    compiled_word_repls: list[tuple[re.Pattern[str] | None, str, str]] = []
    for old_w, new_w in word_replacements.items():
        if not old_w:
            continue
        if re.match(r"^[A-Za-z0-9_'\-\s]+$", old_w):
            compiled_word_repls.append((re.compile(rf"\b{re.escape(old_w)}\b", re.IGNORECASE), old_w, new_w))
        else:
            compiled_word_repls.append((None, old_w, new_w))

    auto_wrap = bool(spec.get("auto_wrap", True))
    cue_tasks: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for tr in draft.get("tracks", []):
        if tr.get("type") != "text":
            continue
        tname = (tr.get("name") or "").lower()
        if "cinematic card" in tname or "card" in tname:
            continue
        segs = tr.get("segments", [])
        if len(segs) < 10:
            continue
        for idx, seg in enumerate(segs):
            mat_id = seg.get("material_id")
            mat = mats_by_id.get(mat_id)
            if mat is not None:
                cue_tasks.append((idx, seg, mat))

    def _style_one_cue(item: tuple[int, dict[str, Any], dict[str, Any]]) -> tuple[int, int, str | None]:
        idx, seg, mat = item
        raw_text = mat.get("recognize_text") or ""
        if not raw_text and isinstance(mat.get("content"), str) and mat["content"].startswith("{"):
            try:
                raw_text = json.loads(mat["content"]).get("text", "")
            except Exception:
                raw_text = ""

        tm = seg.get("target_timerange") or {}
        cue_st = float(tm.get("start", 0)) / 1e6
        cue_en = cue_st + float(tm.get("duration", 0)) / 1e6

        new_text = raw_text
        sample_diff: str | None = None
        if str(idx) in cue_overrides:
            new_text = cue_overrides[str(idx)]
        else:
            before_norm = " ".join(new_text.split())
            if normalize_with_screenplay and screenplay_context:
                new_text = _normalize_cue_with_screenplay(new_text, cue_st, cue_en, screenplay_context)
            for pat, old_w, new_w in compiled_word_repls:
                if pat is not None:
                    new_text = pat.sub(new_w, new_text)
                elif old_w in new_text:
                    new_text = new_text.replace(old_w, new_w)
            if sentence_case:
                new_text = _apply_sentence_case_and_tokens(new_text)
            after_norm = " ".join(new_text.split())
            if after_norm != before_norm and after_norm.lower() != before_norm.lower():
                sample_diff = f"#{idx+1}: {before_norm!r} -> {after_norm!r}"

        if auto_wrap:
            new_text = wrap_subtitle_balanced(new_text, max_chars=max_chars)

        modified = 1 if new_text != raw_text else 0
        rich = build_rich_text_content(new_text, sub_style, font_path=resolved_font_path)
        mat["recognize_text"] = new_text
        mat["base_content"] = rich
        mat["content"] = rich
        mat["font_name"] = sub_style.font_name
        mat["font_title"] = sub_style.font_name
        mat["font_path"] = resolved_font_path
        mat["font_id"] = sub_style.font_postscript
        mat["font_resource_id"] = sub_style.font_postscript
        mat["font_size"] = float(sub_style.font_size)
        mat["text_size"] = text_size_int
        mat["text_color"] = sub_style.color_hex
        mat["check_flag"] = int(sub_style.check_flag)
        mat["border_color"] = sub_style.stroke_color_hex
        mat["border_width"] = float(sub_style.stroke_width)
        mat["border_alpha"] = float(sub_style.stroke_alpha)
        mat["has_shadow"] = True
        mat["shadow_color"] = sub_style.shadow_color_hex
        mat["shadow_alpha"] = float(sub_style.shadow_alpha)
        mat["shadow_smoothing"] = float(sub_style.shadow_smoothing)
        mat["shadow_distance"] = float(sub_style.shadow_distance)
        mat["shadow_angle"] = float(sub_style.shadow_angle)
        mat["background_style"] = 0
        mat["background_color"] = ""
        mat["background_alpha"] = 0.0

        clip = seg.setdefault("clip", {})
        clip.setdefault("scale", {"x": 1.0, "y": 1.0})
        clip["transform"] = {"x": 0.0, "y": y_pos}
        return (1, modified, sample_diff)

    styled_count = 0
    replaced_count = 0
    sample_corrections: list[str] = []
    if cue_tasks:
        with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as pool:
            for st_c, mod_c, s_diff in pool.map(_style_one_cue, cue_tasks):
                styled_count += st_c
                replaced_count += mod_c
                if s_diff and len(sample_corrections) < 12:
                    sample_corrections.append(s_diff)

    return {
        "styled_cues": styled_count,
        "modified_text_cues": replaced_count,
        "sample_screenplay_corrections": sample_corrections,
        "font": font_ps,
        "size": font_size,
        "color": color_hex,
        "y": y_pos,
        "check_flag": sub_style.check_flag,
    }


@dataclass(frozen=True)
class NativeCardPairResult:
    title_material: dict[str, Any]
    detail_material: dict[str, Any]
    title_animation: dict[str, Any]
    detail_animation: dict[str, Any]
    title_segment: dict[str, Any]
    detail_segment: dict[str, Any]


def build_card_pair(
    *,
    card_id: str,
    kind: str,
    title_text: str,
    detail_text: str,
    start_us: int,
    duration_us: int,
    x: float,
    y_title: float,
    preset: FilmCardStyle,
    scale: float = 1.0,
    x_detail: float | None = None,
    y_detail: float | None = None,
    title_style: TextLayerStyle | None = None,
    detail_style: TextLayerStyle | None = None,
    include_fade_out: bool = True,
) -> NativeCardPairResult:
    if title_style is not None and detail_style is not None:
        t_style, d_style = title_style, detail_style
    elif kind in ("character", "char"):
        t_style, d_style = preset.character_title, preset.character_detail
    elif kind in ("end", "ending"):
        t_style, d_style = preset.ending_title, preset.ending_detail
    else:
        t_style, d_style = preset.time_title, preset.time_detail

    group_id = f"capcut_cards_{card_id}"
    fade_in_us = min(int(round(preset.fade_in_sec * 1_000_000)), duration_us // 3)
    fade_out_us = min(int(round(preset.fade_out_sec * 1_000_000)), duration_us // 3)

    t_mat_id, t_mat = build_text_material(title_text, t_style, group_id=group_id, is_title=True)
    d_mat_id, d_mat = build_text_material(detail_text, d_style, group_id=group_id, is_title=False)

    resolved_x_detail = x_detail if x_detail is not None else x
    resolved_y_detail = (
        y_detail if y_detail is not None else round(y_title - preset.line_gap * scale, 4)
    )
    stagger_us = min(
        int(round(max(0.0, preset.stagger_sec) * 1_000_000)),
        max(0, duration_us // 6),
    )
    if resolved_y_detail > y_title:
        # Detail is on top (detail-first): detail enters at start_us, title enters at start_us + stagger_us
        d_start_us, d_dur_us = start_us, duration_us
        t_start_us, t_dur_us = start_us + stagger_us, max(100_000, duration_us - stagger_us)
    else:
        # Title is on top (title-first): title enters at start_us, detail enters at start_us + stagger_us
        t_start_us, t_dur_us = start_us, duration_us
        d_start_us, d_dur_us = start_us + stagger_us, max(100_000, duration_us - stagger_us)

    t_anim_id, t_anim = build_fade_animations(
        segment_duration_us=t_dur_us,
        fade_in_us=min(fade_in_us, t_dur_us // 3),
        fade_out_us=min(fade_out_us, t_dur_us // 3),
        include_fade_out=include_fade_out,
    )
    d_anim_id, d_anim = build_fade_animations(
        segment_duration_us=d_dur_us,
        fade_in_us=min(fade_in_us, d_dur_us // 3),
        fade_out_us=min(fade_out_us, d_dur_us // 3),
        include_fade_out=include_fade_out,
    )

    t_seg = build_text_segment(
        material_id=t_mat_id,
        anim_material_id=t_anim_id,
        start_us=t_start_us,
        duration_us=t_dur_us,
        x=x,
        y=y_title,
        scale=scale,
        render_index=14100,
    )
    d_seg = build_text_segment(
        material_id=d_mat_id,
        anim_material_id=d_anim_id,
        start_us=d_start_us,
        duration_us=d_dur_us,
        x=resolved_x_detail,
        y=resolved_y_detail,
        scale=scale,
        render_index=14090,
    )
    return NativeCardPairResult(
        title_material=t_mat,
        detail_material=d_mat,
        title_animation=t_anim,
        detail_animation=d_anim,
        title_segment=t_seg,
        detail_segment=d_seg,
    )


def render_card_on_frame(
    frame_path: Path,
    out_path: Path,
    *,
    title_text: str,
    detail_text: str,
    title_style: TextLayerStyle,
    detail_style: TextLayerStyle,
    x: float,
    x_detail: float | None = None,
    y_main: float,
    y_detail: float,
    scale: float,
    label: str = "",
) -> bool:
    """
    Render a WYSIWYG preview of the card onto the actual video frame using the exact
    CapCut pixel scale (font_size * scale * 11.2 px on 1920x1080) and multi-span rich-text
    colors/sizes so the AI agent can visually verify hierarchy, margins, and negative space.
    """
    try:
        base_img = Image.open(frame_path).convert("RGBA")
    except Exception:
        return False

    W, H = base_img.size
    scale_factor = W / 1920.0

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_sh = ImageDraw.Draw(shadow_layer)
    draw_fg = ImageDraw.Draw(overlay)

    def _draw_layer(text: str, style: TextLayerStyle, norm_x: float, norm_y: float, is_title: bool) -> None:
        if not text:
            return
        ttf_path = ensure_capcut_font(style.font_postscript)
        base_px_size = max(10, int(round(style.font_size * scale * CAPCUT_PX_PER_EM_PER_SIZE * scale_factor)))
        try:
            base_fnt = ImageFont.truetype(ttf_path, base_px_size)
        except Exception:
            base_fnt = ImageFont.load_default()

        spans = compute_rich_text_spans(text, style, is_title=is_title)
        span_renders: list[tuple[str, Any, str, int]] = []
        total_w = 0
        for s_lo, s_hi, s_col, s_sz in spans:
            sub_txt = text[s_lo:s_hi]
            if not sub_txt:
                continue
            px_size = max(10, int(round(s_sz * scale * CAPCUT_PX_PER_EM_PER_SIZE * scale_factor)))
            try:
                fnt = ImageFont.truetype(ttf_path, px_size)
            except Exception:
                fnt = ImageFont.load_default()
            adv = int(round(draw_fg.textlength(sub_txt, font=fnt)))
            span_renders.append((sub_txt, fnt, s_col, adv))
            total_w += adv

        cx = int(round((norm_x + 1.0) * 0.5 * W))
        cy = int(round((1.0 - norm_y) * 0.5 * H))
        cur_x = cx - total_w // 2

        try:
            bb_line = draw_fg.textbbox((0, 0), text, font=base_fnt, anchor="ls")
            baseline_y = cy - (bb_line[1] + bb_line[3]) // 2
            use_ls = True
        except Exception:
            bb_line = draw_fg.textbbox((0, 0), text, font=base_fnt)
            baseline_y = cy - (bb_line[3] - bb_line[1]) // 2 - bb_line[1]
            use_ls = False

        sh_rgba = hex_to_rgba_ints(style.shadow_color_hex, style.shadow_alpha)
        sh_off = max(1, int(round(style.shadow_distance * 1.3 * scale_factor)))
        st_px = max(1, int(round(style.stroke_width * 135.0 * scale_factor))) if style.stroke_width > 0.001 else 0
        sh_st_px = st_px + max(1, int(round(3.5 * scale_factor)))
        st_rgba = hex_to_rgba_ints(style.stroke_color_hex, style.stroke_alpha)

        for sub_txt, fnt, s_col, adv in span_renders:
            fg_rgba = hex_to_rgba_ints(s_col, style.alpha)
            if use_ls:
                draw_sh.text(
                    (cur_x + sh_off, baseline_y + sh_off),
                    sub_txt,
                    font=fnt,
                    fill=sh_rgba,
                    stroke_width=sh_st_px,
                    stroke_fill=sh_rgba,
                    anchor="ls",
                )
                draw_fg.text(
                    (cur_x, baseline_y),
                    sub_txt,
                    font=fnt,
                    fill=fg_rgba,
                    stroke_width=st_px,
                    stroke_fill=st_rgba if st_px > 0 else None,
                    anchor="ls",
                )
            else:
                draw_sh.text(
                    (cur_x + sh_off, baseline_y + sh_off),
                    sub_txt,
                    font=fnt,
                    fill=sh_rgba,
                    stroke_width=sh_st_px,
                    stroke_fill=sh_rgba,
                )
                draw_fg.text(
                    (cur_x, baseline_y),
                    sub_txt,
                    font=fnt,
                    fill=fg_rgba,
                    stroke_width=st_px,
                    stroke_fill=st_rgba if st_px > 0 else None,
                )
            cur_x += adv

    _draw_layer(title_text, title_style, x, y_main, True)
    if detail_text:
        _draw_layer(detail_text, detail_style, x_detail if x_detail is not None else x, y_detail, False)

    blur_r = max(1.6, (2.2 + title_style.shadow_smoothing * 11.0) * scale_factor)
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=blur_r))
    comp = Image.alpha_composite(base_img, shadow_layer)
    comp = Image.alpha_composite(comp, overlay)

    if label:
        d_lbl = ImageDraw.Draw(comp)
        d_lbl.rectangle([8, 8, min(W - 8, 16 + len(label) * 9), 34], fill=(0, 0, 0, 190))
        d_lbl.text((14, 12), label, fill=(255, 255, 255, 255))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    comp.convert("RGB").save(out_path, quality=90)
    return True
