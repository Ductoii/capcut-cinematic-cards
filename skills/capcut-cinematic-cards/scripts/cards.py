#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from native_text import (
    DEFAULT_MAX_WORKERS,
    FilmCardStyle,
    build_card_pair,
    ensure_capcut_font,
    ensure_capcut_fonts_parallel,
    format_detail_with_flankers,
    list_available_fonts,
    measure_text_half_width_norm,
    render_card_on_frame,
    resolve_card_position,
    resolve_card_styles,
    resolve_style,
    style_subtitle_track_in_place,
)

DEFAULT_PROJECTS_ROOT = Path(
    os.path.expanduser("~/Movies/CapCut/User Data/Projects/com.lveditor.draft")
)


@dataclass(frozen=True)
class VideoSegment:
    index: int
    timeline_start_s: float
    timeline_end_s: float
    timeline_dur_s: float
    source_start_s: float
    source_dur_s: float
    speed: float
    path: str
    clip_name: str


def resolve_project_dir(project: str) -> Path:
    candidate = Path(os.path.expanduser(project))
    if candidate.is_dir() and (candidate / "draft_info.json").exists():
        return candidate.resolve()
    by_name = DEFAULT_PROJECTS_ROOT / project
    if by_name.is_dir() and (by_name / "draft_info.json").exists():
        return by_name.resolve()
    raise FileNotFoundError(
        f"Could not find CapCut project {project!r} locally or under {DEFAULT_PROJECTS_ROOT}"
    )


def load_draft(project_dir: Path) -> dict[str, Any]:
    with (project_dir / "draft_info.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_and_sync_draft(project_dir: Path, draft: dict[str, Any]) -> list[str]:
    """Write draft_info.json, sync to draft_content.json and Timelines/*/draft_info.json, and clear stale patches in parallel."""
    main_path = project_dir / "draft_info.json"
    tmp_path = project_dir / "draft_info.json.tmp"
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(draft, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp_path, main_path)

    copy_targets: list[str] = []
    dc_path = project_dir / "draft_content.json"
    if dc_path.exists():
        copy_targets.append(str(dc_path))
    copy_targets.extend(sorted(glob.glob(str(project_dir / "Timelines" / "*" / "draft_info.json"))))

    patch_files = sorted(
        glob.glob(str(project_dir / "Timelines" / "*" / "attachment" / "patch" / "patch.json"))
    )
    mini_files = sorted(
        glob.glob(str(project_dir / "Timelines" / "*" / "attachment" / "patch" / "mini_draft.json"))
    )

    def _copy_one(dst_str: str) -> str:
        shutil.copy2(main_path, dst_str)
        return dst_str

    def _clear_patch(pf: str) -> None:
        try:
            with open(pf, "w", encoding="utf-8") as pfh:
                pfh.write('{"patch_list":[]}')
        except Exception:
            pass

    def _remove_mini(mf: str) -> None:
        try:
            os.remove(mf)
        except Exception:
            pass

    synced = [str(main_path)]
    with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as pool:
        if copy_targets:
            synced.extend(pool.map(_copy_one, copy_targets))
        if patch_files:
            list(pool.map(_clear_patch, patch_files))
        if mini_files:
            list(pool.map(_remove_mini, mini_files))
    return synced


def load_video_timeline(draft: dict[str, Any]) -> list[VideoSegment]:
    """
    Extract ordered timeline video segments.
    Walks top-level video tracks in order, unwrapping any Compound Clip (`materials.drafts[].draft`)
    segment inline and falling back to the largest compound subdraft when the main track holds a
    compound wrapper segment.
    """
    top_videos = {
        m["id"]: m.get("path", "")
        for m in draft.get("materials", {}).get("videos", [])
        if m.get("path")
    }
    draft_mats = {
        dr["id"]: dr.get("draft") or {}
        for dr in draft.get("materials", {}).get("drafts", [])
        if dr.get("draft")
    }

    largest_sub: dict[str, Any] | None = None
    largest_count = 0
    for dr in draft.get("materials", {}).get("drafts", []):
        sub = dr.get("draft") or {}
        sv = {
            m["id"]: m.get("path", "")
            for m in sub.get("materials", {}).get("videos", [])
            if m.get("path")
        }
        cnt = sum(
            len([s for s in tr.get("segments", []) if s.get("material_id") in sv])
            for tr in sub.get("tracks", [])
            if tr.get("type") == "video"
        )
        if cnt > largest_count:
            largest_count = cnt
            largest_sub = sub

    def _find_subdraft(seg: dict[str, Any]) -> dict[str, Any] | None:
        mid = seg.get("material_id")
        if mid in draft_mats:
            return draft_mats[mid]
        for ref_id in seg.get("extra_material_refs") or []:
            if ref_id in draft_mats:
                return draft_mats[ref_id]
        return None

    def _unwrap_sub(
        sub: dict[str, Any],
        tl_offset_s: float = 0.0,
        src_offset_s: float = 0.0,
        parent_src_dur_s: float | None = None,
        parent_spd: float = 1.0,
    ) -> list[tuple[float, float, float, float, float, str]]:
        sv = {
            m["id"]: m.get("path", "")
            for m in sub.get("materials", {}).get("videos", [])
            if m.get("path")
        }
        items: list[tuple[float, float, float, float, float, str]] = []
        p_s0 = src_offset_s
        p_s1 = (src_offset_s + parent_src_dur_s) if parent_src_dur_s is not None else None
        p_spd = max(parent_spd, 1e-6)
        for tr in sub.get("tracks", []):
            if tr.get("type") != "video":
                continue
            segs = [
                s for s in tr.get("segments", [])
                if s.get("material_id") in sv or _find_subdraft(s) is not None
            ]
            if not segs:
                continue
            for s in segs:
                t_r = s.get("target_timerange") or {}
                s_r = s.get("source_timerange") or t_r
                sub_t0 = float(t_r.get("start", 0)) / 1e6
                sub_t_dur = float(t_r.get("duration", 0)) / 1e6
                sub_t1 = sub_t0 + sub_t_dur
                sub_s0 = float(s_r.get("start", 0)) / 1e6
                sub_s_dur = float(s_r.get("duration", sub_t_dur * 1e6)) / 1e6
                sub_spd = float(s.get("speed") or (sub_s_dur / sub_t_dur if sub_t_dur > 0 else 1.0))

                ov_0 = max(sub_t0, p_s0)
                ov_1 = min(sub_t1, p_s1) if p_s1 is not None else sub_t1
                if ov_1 <= ov_0 + 1e-3:
                    continue

                eff_t_start = tl_offset_s + (ov_0 - p_s0) / p_spd
                eff_t_dur = (ov_1 - ov_0) / p_spd
                eff_s_start = sub_s0 + (ov_0 - sub_t0) * sub_spd
                eff_s_dur = (ov_1 - ov_0) * sub_spd
                eff_spd = sub_spd * p_spd
                mid = s.get("material_id")
                if mid in sv:
                    items.append((eff_t_start, eff_t_dur, eff_s_start, eff_s_dur, eff_spd, sv[mid]))
                else:
                    nested_sub = _find_subdraft(s)
                    if nested_sub is not None:
                        items.extend(_unwrap_sub(nested_sub, eff_t_start, eff_s_start, eff_s_dur, eff_spd))
            break
        return items

    raw_items: list[tuple[float, float, float, float, float, str]] = []
    for tr in draft.get("tracks", []):
        if tr.get("type") != "video":
            continue
        t_segs = tr.get("segments", [])
        if not t_segs:
            continue
        for s in t_segs:
            mid = s.get("material_id")
            t_r = s.get("target_timerange") or {}
            s_r = s.get("source_timerange") or {"start": 0, "duration": t_r.get("duration", 0)}
            t_start = float(t_r.get("start", 0)) / 1e6
            t_dur = float(t_r.get("duration", 0)) / 1e6
            s_start = float(s_r.get("start", 0)) / 1e6
            s_dur = float(s_r.get("duration", t_dur * 1e6)) / 1e6
            spd = float(s.get("speed") or (s_dur / t_dur if t_dur > 0 else 1.0))
            matched_sub = _find_subdraft(s)
            if mid in top_videos:
                raw_items.append((t_start, t_dur, s_start, s_dur, spd, top_videos[mid]))
            elif matched_sub is not None:
                raw_items.extend(_unwrap_sub(matched_sub, t_start, s_start, s_dur, spd))
            elif len(t_segs) <= 2 and largest_sub is not None:
                raw_items.extend(_unwrap_sub(largest_sub, t_start, s_start, s_dur, spd))
        if raw_items:
            break

    raw_items.sort(key=lambda r: r[0])
    return [
        VideoSegment(
            index=idx,
            timeline_start_s=round(t_start, 3),
            timeline_end_s=round(t_start + t_dur, 3),
            timeline_dur_s=round(t_dur, 3),
            source_start_s=round(s_start, 3),
            source_dur_s=round(s_dur, 3),
            speed=round(spd, 4),
            path=vpath,
            clip_name=os.path.basename(vpath),
        )
        for idx, (t_start, t_dur, s_start, s_dur, spd, vpath) in enumerate(raw_items)
    ]


def group_scene_boundaries(segments: list[VideoSegment]) -> list[dict[str, Any]]:
    """Group consecutive video segments by scene identifier (e.g. scene_001.mp4 or V-S1-*)."""
    if not segments:
        return []

    def scene_key(clip_name: str) -> str:
        m_s = re.match(r"^(V-S\d+)", clip_name, re.I)
        if m_s:
            return m_s.group(1).upper()
        m_sc = re.match(r"^(scene_\d+)", clip_name, re.I)
        if m_sc:
            return m_sc.group(1).lower()
        return os.path.splitext(clip_name)[0]

    groups: list[dict[str, Any]] = []
    for seg in segments:
        skey = scene_key(seg.clip_name)
        if groups and groups[-1]["scene_id"] == skey:
            groups[-1]["end_s"] = seg.timeline_end_s
            groups[-1]["dur_s"] = round(seg.timeline_end_s - groups[-1]["start_s"], 3)
            groups[-1]["segment_count"] += 1
            if seg.clip_name not in groups[-1]["clips"]:
                groups[-1]["clips"].append(seg.clip_name)
        else:
            groups.append(
                {
                    "scene_id": skey,
                    "start_s": seg.timeline_start_s,
                    "end_s": seg.timeline_end_s,
                    "dur_s": seg.timeline_dur_s,
                    "segment_count": 1,
                    "clips": [seg.clip_name],
                }
            )
    return groups


def extract_subtitles(draft: dict[str, Any]) -> list[dict[str, Any]]:
    mats = {m["id"]: m for m in draft.get("materials", {}).get("texts", [])}
    cues: list[dict[str, Any]] = []
    for tr in draft.get("tracks", []):
        if tr.get("type") != "text":
            continue
        segs = tr.get("segments", [])
        if len(segs) <= 100:
            continue
        for idx, s in enumerate(segs):
            m = mats.get(s.get("material_id"), {})
            raw_c = m.get("content", "")
            txt = raw_c
            if raw_c.startswith("{"):
                try:
                    txt = json.loads(raw_c).get("text", "")
                except Exception:
                    txt = raw_c
            tm = s.get("target_timerange") or {}
            st = round(float(tm.get("start", 0)) / 1e6, 2)
            en = round((float(tm.get("start", 0)) + float(tm.get("duration", 0))) / 1e6, 2)
            cues.append(
                {
                    "index": idx,
                    "start_s": st,
                    "end_s": en,
                    "text": " ".join(txt.splitlines()),
                }
            )
    return cues


def extract_existing_cards(draft: dict[str, Any]) -> list[dict[str, Any]]:
    mats = {m["id"]: m for m in draft.get("materials", {}).get("texts", [])}
    cards: list[dict[str, Any]] = []
    for ti, tr in enumerate(draft.get("tracks", [])):
        if tr.get("type") != "text":
            continue
        segs = tr.get("segments", [])
        if len(segs) > 100:
            continue
        for s in segs:
            m = mats.get(s.get("material_id"), {})
            raw_c = m.get("content", "")
            txt = raw_c
            sz = m.get("font_size", 5.0)
            font_ps = m.get("font_id", "")
            if raw_c.startswith("{"):
                try:
                    cobj = json.loads(raw_c)
                    txt = cobj.get("text", "")
                    st0 = (cobj.get("styles") or [{}])[0]
                    sz = st0.get("size", sz)
                    font_ps = (st0.get("font") or {}).get("id", font_ps)
                except Exception:
                    pass
            tm = s.get("target_timerange") or {}
            st = round(float(tm.get("start", 0)) / 1e6, 2)
            en = round((float(tm.get("start", 0)) + float(tm.get("duration", 0))) / 1e6, 2)
            clip = s.get("clip") or {}
            tr_xy = clip.get("transform") or {}
            sc_xy = clip.get("scale") or {}
            cards.append(
                {
                    "track": ti,
                    "start_s": st,
                    "end_s": en,
                    "x": round(float(tr_xy.get("x", 0.0)), 3),
                    "y": round(float(tr_xy.get("y", 0.0)), 3),
                    "scale": round(float(sc_xy.get("x", 1.0)), 2),
                    "size": round(float(sz), 2),
                    "font": font_ps,
                    "text": txt,
                }
            )
    cards.sort(key=lambda r: (r["start_s"], -r["y"]))
    return cards


def detect_window_cuts(
    segments: list[VideoSegment],
    win_start: float,
    win_end: float,
    scdet_threshold: float = 10.0,
) -> dict[str, list[float]]:
    """Return both edit-segment boundaries and internal ffmpeg scdet camera cuts inside [win_start, win_end] in parallel."""
    seg_cuts: list[float] = []
    scdet_tasks: list[tuple[VideoSegment, float, float]] = []

    for seg in segments:
        if seg.timeline_end_s <= win_start or seg.timeline_start_s >= win_end:
            continue
        if win_start < seg.timeline_start_s < win_end:
            seg_cuts.append(round(seg.timeline_start_s, 2))
        if win_start < seg.timeline_end_s < win_end:
            seg_cuts.append(round(seg.timeline_end_s, 2))

        if not os.path.exists(seg.path):
            continue
        ov_start = max(win_start, seg.timeline_start_s)
        ov_end = min(win_end, seg.timeline_end_s)
        ov_dur = ov_end - ov_start
        if ov_dur <= 0.3:
            continue
        scdet_tasks.append((seg, ov_start, ov_dur))

    def _run_scdet(item: tuple[VideoSegment, float, float]) -> list[float]:
        seg, ov_start, ov_dur = item
        src_offset = seg.source_start_s + (ov_start - seg.timeline_start_s) * seg.speed
        src_dur = ov_dur * seg.speed
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-ss",
            f"{src_offset:.3f}",
            "-t",
            f"{src_dur:.3f}",
            "-i",
            seg.path,
            "-vf",
            f"scale=160:90,scdet=t={scdet_threshold}:s=1,metadata=mode=print",
            "-an",
            "-f",
            "null",
            "-",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        found: list[float] = []
        for m in re.findall(r"lavfi\.scd\.time=([0-9.]+)", res.stderr):
            tl_cut = round(ov_start + float(m) / max(seg.speed, 1e-6), 2)
            if win_start + 0.15 < tl_cut < win_end - 0.15:
                found.append(tl_cut)
        return found

    scdet_cuts: list[float] = []
    if len(scdet_tasks) == 1:
        scdet_cuts.extend(_run_scdet(scdet_tasks[0]))
    elif len(scdet_tasks) > 1:
        with ThreadPoolExecutor(max_workers=min(DEFAULT_MAX_WORKERS, len(scdet_tasks))) as pool:
            for sub_cuts in pool.map(_run_scdet, scdet_tasks):
                scdet_cuts.extend(sub_cuts)

    all_cuts = sorted(set(seg_cuts + scdet_cuts))
    return {
        "segment_cuts": sorted(set(seg_cuts)),
        "scdet_cuts": sorted(set(scdet_cuts)),
        "all_cuts": all_cuts,
    }


def extract_frame_at_timeline_sec(
    segments: list[VideoSegment],
    t_sec: float,
    out_jpg: Path,
    width: int = 640,
    height: int = 360,
    include_guides: bool = True,
) -> tuple[bool, str]:
    """Extract a single frame at timeline second `t_sec`, with disk caching by source clip & timestamp."""
    target_seg: VideoSegment | None = None
    for seg in segments:
        if seg.timeline_start_s <= t_sec <= seg.timeline_end_s:
            target_seg = seg
            break
    if target_seg is None and segments:
        target_seg = segments[-1] if t_sec > segments[-1].timeline_end_s else segments[0]
    if target_seg is None or not os.path.exists(target_seg.path):
        return False, ""

    src_sec = (
        target_seg.source_start_s
        + max(0.0, t_sec - target_seg.timeline_start_s) * target_seg.speed
    )
    cache_dir = Path("/tmp/_capcut_frame_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        abs_p = os.path.abspath(target_seg.path)
        mtime_ns = os.stat(abs_p).st_mtime_ns
    except Exception:
        abs_p = target_seg.path
        mtime_ns = 0
    path_sig = hashlib.md5(f"{abs_p}:{mtime_ns}".encode("utf-8")).hexdigest()[:10]
    cache_key = f"{path_sig}_{target_seg.clip_name}_{int(round(src_sec * 20)):05d}_{width}x{height}_g{int(include_guides)}.jpg"
    cache_path = cache_dir / cache_key
    if cache_path.exists() and cache_path.stat().st_size > 500:
        out_jpg.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.resolve() != out_jpg.resolve():
            shutil.copyfile(str(cache_path), str(out_jpg))
        return True, target_seg.clip_name

    if include_guides:
        vf = (
            f"scale={width}:{height},"
            f"drawbox=x=0:y={int(height*0.84)}:w={width}:h=2:color=yellow@0.45:t=fill,"
            f"drawbox=x={int(width*0.06)}:y={int(height*0.06)}:w={int(width*0.34)}:h={int(height*0.18)}:color=cyan@0.35:t=1,"
            f"drawbox=x={int(width*0.60)}:y={int(height*0.06)}:w={int(width*0.34)}:h={int(height*0.18)}:color=cyan@0.35:t=1,"
            f"drawbox=x={int(width*0.06)}:y={int(height*0.58)}:w={int(width*0.34)}:h={int(height*0.18)}:color=lime@0.35:t=1,"
            f"drawbox=x={int(width*0.60)}:y={int(height*0.58)}:w={int(width*0.34)}:h={int(height*0.18)}:color=lime@0.35:t=1"
        )
    else:
        vf = f"scale={width}:{height}"
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{src_sec:.3f}",
        "-i",
        target_seg.path,
        "-frames:v",
        "1",
        "-vf",
        vf,
        "-q:v",
        "4",
        str(out_jpg),
    ]
    subprocess.run(cmd, check=False)
    if out_jpg.exists() and out_jpg.stat().st_size > 500:
        try:
            shutil.copyfile(str(out_jpg), str(cache_path))
        except Exception:
            pass
    return out_jpg.exists(), target_seg.clip_name


def score_frame_negative_space(frame_path: Path) -> dict[str, Any]:
    """
    Evaluate luminance, 90th-percentile brightness (glare/white signage), and bright-pixel ratio
    across the 4 corner zones ('lower-left', 'lower-right', 'upper-left', 'upper-right') on `frame_path`.
    Returns zone stats and `best_anchor` (lowest cost = darkest, least glared negative space).
    """
    try:
        from PIL import Image

        with Image.open(frame_path) as im:
            gray = im.convert("L").resize((160, 90))
        boxes = {
            "lower-left": (10, 52, 74, 72),
            "lower-right": (86, 52, 150, 72),
            "upper-left": (10, 6, 74, 26),
            "upper-right": (86, 6, 150, 26),
        }
        zones: dict[str, dict[str, float]] = {}
        for zname, box in boxes.items():
            cropped = gray.crop(box)
            px = sorted(getattr(cropped, "get_flattened_data", cropped.getdata)())
            n = max(1, len(px))
            mean_l = sum(px) / n
            p90_l = float(px[min(n - 1, int(n * 0.90))])
            bright_r = sum(1 for v in px if v >= 185) / n
            upper_pen = 18.0 if zname.startswith("upper") else 0.0
            cost = round(mean_l + 0.85 * p90_l + 240.0 * bright_r + upper_pen, 2)
            zones[zname] = {
                "mean_luma": round(mean_l, 1),
                "p90_luma": round(p90_l, 1),
                "bright_ratio": round(bright_r, 3),
                "cost": cost,
            }
        best_anchor = min(zones.keys(), key=lambda k: zones[k]["cost"])
        return {"best_anchor": best_anchor, "zones": zones}
    except Exception:
        return {"best_anchor": "lower-left", "zones": {}}


def extract_fast_timeline_cuts(video_segs: list[VideoSegment]) -> list[float]:
    """
    Extract all timeline edit-segment boundaries PLUS any internal camera shot cuts defined
    in `sf-board.json` (`goc` intervals like `(0-5s)`, `(5-10s)`) in < 0.002s without spawning ffmpeg.
    """
    cuts: set[float] = set()
    for seg in video_segs:
        cuts.add(round(seg.timeline_start_s, 2))
        cuts.add(round(seg.timeline_end_s, 2))

    sf_board_path: Path | None = None
    for seg in video_segs:
        if not seg.path:
            continue
        p = Path(seg.path)
        for parent in (p.parent, p.parent.parent):
            cand = parent / "sf-board.json"
            if cand.exists():
                sf_board_path = cand
                break
        if sf_board_path:
            break

    if sf_board_path:
        try:
            sb = json.loads(sf_board_path.read_text(encoding="utf-8"))
            segs_by_clip: dict[str, list[VideoSegment]] = {}
            for seg in video_segs:
                segs_by_clip.setdefault(Path(seg.clip_name).stem, []).append(seg)
            for sc in sb.get("scenes", [])[1:]:
                for sh in (sc.get("shots") or sc.get("sfs") or []):
                    cid = sh.get("id")
                    goc = sh.get("goc", "")
                    if not cid or not goc or cid not in segs_by_clip:
                        continue
                    for m in re.finditer(r"\(?(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*s\)?", goc):
                        for src_t in (float(m.group(1)), float(m.group(2))):
                            for seg in segs_by_clip[cid]:
                                s0 = seg.source_start_s
                                s1 = s0 + seg.source_dur_s
                                if s0 + 0.05 < src_t < s1 - 0.05:
                                    tl_t = round(seg.timeline_start_s + (src_t - s0) / max(seg.speed, 1e-6), 2)
                                    cuts.add(tl_t)
        except Exception:
            pass
    return sorted(cuts)


def build_contact_sheet(
    frame_items: list[tuple[float, str, Path]],
    out_sheet: Path,
    cols: int = 4,
) -> bool:
    """Assemble extracted frame JPEGs into a compact labeled contact sheet using PIL."""
    if not frame_items:
        return False
    try:
        from PIL import Image, ImageDraw, ImageFont

        cell_w, cell_h = 480, 270
        rows = (len(frame_items) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (12, 14, 18))
        draw = ImageDraw.Draw(sheet)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14)
        except Exception:
            font = ImageFont.load_default()

        for idx, (t_sec, clip_name, fpath) in enumerate(frame_items):
            if not fpath.exists():
                continue
            r, c = divmod(idx, cols)
            x0, y0 = c * cell_w, r * cell_h
            with Image.open(fpath) as im:
                sheet.paste(im.resize((cell_w, cell_h)), (x0, y0))
            label = f" t={t_sec:6.2f}s | {clip_name} "
            draw.rectangle([x0 + 5, y0 + 5, min(x0 + cell_w - 5, x0 + 5 + len(label) * 9), y0 + 26], fill=(0, 0, 0))
            draw.text((x0 + 7, y0 + 7), label, fill=(255, 230, 110), font=font)

        out_sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out_sheet, quality=80)
        return True
    except Exception:
        return False


def strip_card_tracks(draft: dict[str, Any]) -> None:
    """Remove all non-subtitle text tracks (<= 100 segments or named Cinematic Cards*) and their orphaned materials."""
    kept_tracks: list[dict[str, Any]] = []
    removed_mat_ids: set[str] = set()
    removed_anim_ids: set[str] = set()

    for tr in draft.get("tracks", []):
        if tr.get("type") == "text":
            segs = tr.get("segments", [])
            name = str(tr.get("name") or "")
            if len(segs) <= 100 or name.startswith("Cinematic Cards"):
                for s in segs:
                    if s.get("material_id"):
                        removed_mat_ids.add(s["material_id"])
                    for ex in s.get("extra_material_refs", []):
                        removed_anim_ids.add(ex)
                continue
        kept_tracks.append(tr)

    draft["tracks"] = kept_tracks
    mats = draft.setdefault("materials", {})
    if "texts" in mats:
        mats["texts"] = [m for m in mats["texts"] if m.get("id") not in removed_mat_ids]
    if "material_animations" in mats:
        mats["material_animations"] = [
            a for a in mats["material_animations"] if a.get("id") not in removed_anim_ids
        ]


def apply_plan_to_draft(
    draft: dict[str, Any],
    plan: dict[str, Any],
    *,
    snap_to_cuts: bool = True,
) -> dict[str, Any]:
    """
    Apply a card + subtitle plan directly to `draft` in memory.
    Automatically handles:
    - Font extraction for any macOS system font
    - Outer-edge alignment using true fontTools glyph width
    - Simultaneous overlapping cards (multi-track allocation: Track Pair 1, Track Pair 2, ...)
    - Camera-cut end snapping so cards don't bleed 0.3-1.0s into the next shot
    - Optional in-place subtitle styling with check_flag=47 drop shadow and screenplay-grounded normalization
    """
    video_segs = load_video_timeline(draft)
    cut_times = extract_fast_timeline_cuts(video_segs)
    film_duration_s = (
        video_segs[-1].timeline_end_s
        if video_segs
        else round(float(draft.get("duration", 0)) / 1e6, 3)
    )
    sub_cues = extract_subtitles(draft)
    sp_ctx = build_screenplay_subtitle_context(video_segs, sub_cues)

    raw_style = dict(plan.get("style") or {})
    rec_style = sp_ctx.get("recommended_style") or {}
    # Guard against industrial ALL-CAPS sans-serif / outer-align templates (`SpaceGrotesk-SemiBold` + `detail_uppercase: true`)
    is_industrial_sans = (
        "SpaceGrotesk" in str(raw_style.get("detail_font") or "")
        and bool(raw_style.get("detail_uppercase"))
    )
    if (not raw_style or is_industrial_sans) and rec_style:
        merged_style = dict(rec_style)
        if not is_industrial_sans:
            merged_style.update(raw_style)
        raw_style = merged_style

    preset: FilmCardStyle = resolve_style(raw_style)
    raw_cards: list[dict[str, Any]] = list(plan.get("cards") or [])
    raw_cards.sort(key=lambda c: (float(c.get("start", 0.0)), str(c.get("kind", ""))))

    # Warm up all unique fonts across preset, cards, and subtitles in parallel
    all_font_specs: list[str] = [
        preset.character_title.font_postscript,
        preset.character_detail.font_postscript,
        preset.time_title.font_postscript,
        preset.time_detail.font_postscript,
        preset.ending_title.font_postscript,
        preset.ending_detail.font_postscript,
    ]
    for c in raw_cards:
        if c.get("title_font"):
            all_font_specs.append(str(c["title_font"]))
        if c.get("detail_font"):
            all_font_specs.append(str(c["detail_font"]))
    if isinstance(plan.get("subtitles"), dict) and plan["subtitles"].get("font"):
        all_font_specs.append(str(plan["subtitles"]["font"]))
    ensure_capcut_fonts_parallel(all_font_specs)

    # Strip old card tracks first
    strip_card_tracks(draft)

    # Pre-adjust sub-shot boundaries using fast cut_times (< 0.002s)
    resolved_times: list[tuple[float, float]] = []
    for card in raw_cards:
        kind = str(card.get("kind") or card.get("type") or "char").lower()
        kind_norm = "char" if kind in ("character", "char") else ("end" if kind in ("end", "ending") else "time")
        start_s = float(card.get("start", card.get("start_s", 0.0)))
        end_s = float(card.get("end", card.get("end_s", start_s + 4.0)))
        if kind_norm == "end" and card.get("hold_to_end", False) and film_duration_s > start_s:
            end_s = film_duration_s
        if (
            snap_to_cuts
            and kind_norm != "end"
            and card.get("snap_to_cut", True)
            and video_segs
        ):
            probe_lo = max(0.0, round(start_s - 0.6, 2))
            probe_hi = min(film_duration_s, round(end_s + 0.6, 2))
            if probe_hi > probe_lo:
                bounds = [probe_lo] + [c for c in cut_times if probe_lo + 0.05 < c < probe_hi - 0.05] + [probe_hi]
                best_sub = (probe_lo, probe_hi)
                best_ov = -1.0
                for bi in range(len(bounds) - 1):
                    slo, shi = bounds[bi], bounds[bi + 1]
                    ov = max(0.0, min(end_s, shi) - max(start_s, slo))
                    if ov > best_ov:
                        best_ov = ov
                        best_sub = (slo, shi)
                slo, shi = best_sub
                if shi - slo >= 1.9:
                    if slo > probe_lo + 0.02 and start_s < slo + 0.12:
                        start_s = round(slo + 0.15, 2)
                    if shi < probe_hi - 0.02 and end_s > shi - 0.06:
                        end_s = round(shi - 0.08, 2)
        resolved_times.append((start_s, end_s))

    # Parallel frame extraction + negative-space scoring + card pair construction across all worker threads
    need_mid_frames = bool(video_segs) and any(
        str(c.get("anchor") or "").strip().lower() in ("", "auto") or c.get("auto_avoid_glare", True)
        for c in raw_cards
    )
    proj_sig = (
        hashlib.md5(os.path.abspath(video_segs[0].path).encode("utf-8")).hexdigest()[:10]
        if video_segs and video_segs[0].path
        else "default"
    )
    tmp_fdir = Path(f"/tmp/_capcut_frame_cache/midpoints_{proj_sig}")
    if need_mid_frames:
        tmp_fdir.mkdir(parents=True, exist_ok=True)

    def _build_one_card(idx_and_card: tuple[int, dict[str, Any]]) -> dict[str, Any]:
        idx, card = idx_and_card
        kind = str(card.get("kind") or card.get("type") or "char").lower()
        if kind in ("character", "char"):
            kind_norm = "char"
        elif kind in ("end", "ending"):
            kind_norm = "end"
        else:
            kind_norm = "time"

        t_style, d_style, card_align, card_order = resolve_card_styles(card, preset)
        start_s, end_s = resolved_times[idx - 1]
        dur_s = max(0.5, round(end_s - start_s, 3))
        start_us = int(round(start_s * 1_000_000))
        dur_us = int(round(dur_s * 1_000_000))
        end_us = start_us + dur_us

        has_sub = any(
            not (cue["end_s"] <= start_s + 0.1 or cue["start_s"] >= end_s - 0.1)
            for cue in sub_cues
        )

        title_text = str(card.get("title") or card.get("name") or card.get("main") or "").strip()
        raw_detail_text = str(card.get("detail") or card.get("role") or card.get("sub") or "").strip()
        if card.get("title_uppercase", preset.title_uppercase):
            title_text = title_text.upper()
        if card.get("detail_uppercase", preset.detail_uppercase):
            raw_detail_text = raw_detail_text.upper()

        card_flankers = str(
            card.get("flankers")
            if card.get("flankers") is not None
            else (preset.flankers if kind_norm in ("char", "end") else preset.scene_flankers)
        ).strip()
        detail_text = format_detail_with_flankers(
            raw_detail_text, card_flankers, font_postscript=d_style.font_postscript
        )
        card_for_pos = dict(card, title=title_text, detail=detail_text)

        flip_note: str | None = None
        req_anchor = str(card_for_pos.get("anchor") or "").strip().lower()
        if need_mid_frames and (req_anchor in ("", "auto") or card_for_pos.get("auto_avoid_glare", True)):
            mid_t = round((start_s + end_s) * 0.5, 2)
            f_p = tmp_fdir / f"mid_{idx:03d}_{int(round(mid_t*10)):06d}.jpg"
            ok, _ = extract_frame_at_timeline_sec(
                video_segs, mid_t, f_p, width=960, height=540, include_guides=False
            )
            if ok and f_p.exists():
                ns = score_frame_negative_space(f_p)
                zones = ns.get("zones", {})
                if req_anchor in ("", "auto"):
                    card_for_pos["anchor"] = ns["best_anchor"]
                elif card_for_pos.get("auto_avoid_glare", True) and req_anchor in ("lower-left", "lower-right") and zones:
                    opp = "lower-right" if req_anchor == "lower-left" else "lower-left"
                    z_cur = zones.get(req_anchor, {})
                    z_opp = zones.get(opp, {})
                    if z_cur.get("bright_ratio", 0.0) >= 0.22 or z_cur.get("p90_luma", 0.0) >= 195.0:
                        if (
                            z_opp.get("cost", 999.0) < z_cur.get("cost", 0.0) - 35.0
                            and z_opp.get("p90_luma", 255.0) < 195.0
                        ):
                            card_for_pos["anchor"] = opp
                            flip_note = f"#{idx:02d} {title_text}: {req_anchor}->{opp}"

        x_title, x_detail, y_main, y_detail, scale = resolve_card_position(
            card_for_pos,
            title_font=t_style.font_postscript,
            detail_font=d_style.font_postscript,
            title_size=t_style.font_size,
            detail_size=d_style.font_size,
            title_letter_spacing=t_style.letter_spacing,
            detail_letter_spacing=d_style.letter_spacing,
            line_gap=preset.line_gap,
            align=card_align,
            order=card_order,
            has_overlapping_subtitle=has_sub,
        )

        include_fade_out = not bool(card.get("no_fade_out", False))
        pair_res = build_card_pair(
            card_id=f"{idx:02d}",
            kind=kind_norm,
            title_text=title_text,
            detail_text=detail_text,
            start_us=start_us,
            duration_us=dur_us,
            x=x_title,
            x_detail=x_detail,
            y_title=y_main,
            y_detail=y_detail,
            preset=preset,
            title_style=t_style,
            detail_style=d_style,
            scale=scale,
            include_fade_out=include_fade_out,
        )
        return {
            "idx": idx,
            "kind_norm": kind_norm,
            "start_s": start_s,
            "dur_s": dur_s,
            "start_us": start_us,
            "end_us": end_us,
            "x_title": x_title,
            "x_detail": x_detail,
            "y_main": y_main,
            "y_detail": y_detail,
            "scale": scale,
            "card_align": card_align,
            "card_order": card_order,
            "title_text": title_text,
            "detail_text": detail_text,
            "pair_res": pair_res,
            "flip_note": flip_note,
            "raw_card": card,
        }

    built_cards: list[dict[str, Any]] = []
    if raw_cards:
        with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as pool:
            built_cards = list(pool.map(_build_one_card, enumerate(raw_cards, start=1)))

    # Track pairs: each pair holds [title_segments, detail_segments, last_end_us]
    track_pairs: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = []
    pair_end_us: list[int] = []

    mats = draft.setdefault("materials", {})
    texts_list = mats.setdefault("texts", [])
    anims_list = mats.setdefault("material_animations", [])

    applied_cards: list[dict[str, Any]] = []
    glare_flips: list[str] = []

    for bc in built_cards:
        pair_res = bc["pair_res"]
        detail_text = bc["detail_text"]
        start_us = bc["start_us"]
        end_us = bc["end_us"]
        if bc["flip_note"]:
            glare_flips.append(bc["flip_note"])

        texts_list.append(pair_res.title_material)
        anims_list.append(pair_res.title_animation)
        if detail_text:
            texts_list.append(pair_res.detail_material)
            anims_list.append(pair_res.detail_animation)

        allocated_pair_idx: int | None = None
        for p_idx, last_end in enumerate(pair_end_us):
            if start_us >= last_end - 20_000:
                allocated_pair_idx = p_idx
                break
        if allocated_pair_idx is None:
            allocated_pair_idx = len(track_pairs)
            track_pairs.append(([], []))
            pair_end_us.append(0)

        t_segs, d_segs = track_pairs[allocated_pair_idx]
        t_segs.append(pair_res.title_segment)
        if detail_text:
            d_segs.append(pair_res.detail_segment)
        pair_end_us[allocated_pair_idx] = max(pair_end_us[allocated_pair_idx], end_us)

        applied_cards.append(
            {
                "index": bc["idx"],
                "kind": bc["kind_norm"],
                "track_pair": allocated_pair_idx + 1,
                "start_s": round(bc["start_s"], 2),
                "end_s": round(bc["start_s"] + bc["dur_s"], 2),
                "x": bc["x_title"],
                "x_detail": bc["x_detail"],
                "y_main": bc["y_main"],
                "y_detail": bc["y_detail"],
                "scale": bc["scale"],
                "align": bc["card_align"],
                "order": bc["card_order"],
                "title": bc["title_text"],
                "detail": detail_text,
                "_raw_card": bc["raw_card"],
            }
        )

    for p_idx, (t_segs, d_segs) in enumerate(track_pairs, start=1):
        suffix = "" if p_idx == 1 else f" {p_idx}"
        draft.setdefault("tracks", []).append(
            {
                "attribute": 0,
                "flag": 0,
                "id": f"CC_MAIN_TRACK_{p_idx}",
                "is_default_name": False,
                "name": f"Cinematic Cards · Main{suffix}",
                "segments": t_segs,
                "type": "text",
            }
        )
        draft.setdefault("tracks", []).append(
            {
                "attribute": 0,
                "flag": 0,
                "id": f"CC_DETAIL_TRACK_{p_idx}",
                "is_default_name": False,
                "name": f"Cinematic Cards · Detail{suffix}",
                "segments": d_segs,
                "type": "text",
            }
        )

    sub_report = None
    if plan.get("subtitles") is not None:
        sub_spec = plan["subtitles"]
        if isinstance(sub_spec, dict) and sub_spec.get("style_in_place", True):
            sub_report = style_subtitle_track_in_place(draft, sub_spec, screenplay_context=sp_ctx)

    return {
        "style_archetype": rec_style.get("archetype", "custom"),
        "title_font": preset.character_title.font_postscript,
        "detail_font": preset.character_detail.font_postscript,
        "title_size": preset.character_title.font_size,
        "detail_size": preset.character_detail.font_size,
        "cards_applied": len(applied_cards),
        "track_pairs_created": len(track_pairs),
        "glare_flips": glare_flips,
        "cards": applied_cards,
        "subtitles": sub_report,
        "_preset": preset,
    }


def _map_shot_breakdown_to_timeline(goc_text: str, segs: list[VideoSegment]) -> str:
    """
    Project source clip shot intervals like `(0-5s)` or `(4.2-9.0s)` in `goc_text` through the
    actual surviving `VideoSegment` slices on the edited CapCut timeline (`source_start_s`, `source_dur_s`, `speed`).
    If the user trimmed out a shot in CapCut, marks it `[TRIMMED_OUT src=a-bs]`.
    """
    if not goc_text or not segs:
        return goc_text

    def _repl(m: re.Match[str]) -> str:
        src_a = float(m.group(1))
        src_b = float(m.group(2))
        mapped: list[str] = []
        for seg in segs:
            s0 = seg.source_start_s
            s1 = seg.source_start_s + seg.source_dur_s
            ov_a = max(src_a, s0)
            ov_b = min(src_b, s1)
            if ov_b > ov_a + 0.15:
                spd = max(seg.speed, 1e-6)
                tl_a = round(seg.timeline_start_s + (ov_a - s0) / spd, 2)
                tl_b = round(seg.timeline_start_s + (ov_b - s0) / spd, 2)
                mapped.append(f"TL {tl_a:.2f}-{tl_b:.2f}s")
        if mapped:
            return f"({', '.join(mapped)} | src {m.group(1)}-{m.group(2)}s)"
        return f"(TRIMMED_OUT | src {m.group(1)}-{m.group(2)}s)"

    return re.sub(r"\(?(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*s\)?", _repl, goc_text)


def _norm_words(txt: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", (txt or "").lower()) if len(w) >= 3}


def extract_screenplay_ground_truth(
    video_segs: list[VideoSegment],
    subs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Automatically locate `sf-board.json` from video segment paths (or by matching subtitle dialogue
    against workspace `.project/sf-board.json` files when the video is a single flat export), and map
    story scenes (`S01..SNN`) and character appearances (`CHAR1..CHARN`, `AL1..ALN`) to exact edited
    CapCut timeline timestamps, accounting for trimmed/split segments (`source_timerange`).
    """
    sf_board_path: Path | None = None
    for seg in video_segs:
        if not seg.path:
            continue
        p = Path(seg.path)
        for parent in (p.parent, p.parent.parent):
            cand = parent / "sf-board.json"
            if cand.exists():
                sf_board_path = cand
                break
        if sf_board_path:
            break

    # Fallback when video is a flat exported MP4 without V-NNN filenames: match subtitle lines against workspace sf-board.json in parallel
    if not sf_board_path and subs:
        sub_blob = " ".join(c.get("text", "") for c in subs[:40]).lower()
        sub_words = _norm_words(sub_blob)
        ws_root = Path("/Users/daho100/Documents/SF Board")
        if ws_root.exists() and sub_words:
            cands = list(ws_root.glob("*.project/sf-board.json"))
            min_hits = max(6, int(len(sub_words) * 0.35))

            def _score_cand(cand: Path) -> tuple[int, Path]:
                try:
                    raw = cand.read_text(encoding="utf-8")[:60000].lower()
                    return sum(1 for w in sub_words if w in raw), cand
                except Exception:
                    return 0, cand

            if cands:
                with ThreadPoolExecutor(max_workers=min(DEFAULT_MAX_WORKERS, len(cands))) as pool:
                    scored = list(pool.map(_score_cand, cands))
                best_score, best_cand = max(scored, key=lambda x: x[0])
                if best_score >= min_hits:
                    sf_board_path = best_cand

    if not sf_board_path:
        return {}

    try:
        with sf_board_path.open("r", encoding="utf-8") as fh:
            sb = json.load(fh)
    except Exception:
        return {}

    # Detect cold-open hook at the beginning of the timeline (e.g. S7 clips placed before S1/S2)
    hook_end_s = 0.0
    if video_segs:
        first_chron_idx = None
        for idx_s, seg in enumerate(video_segs[:25]):
            m_sc = re.match(r"^V-S(\d+)", seg.clip_name, re.I)
            if m_sc and int(m_sc.group(1)) <= 2:
                first_chron_idx = idx_s
                break
        if first_chron_idx and first_chron_idx > 0:
            hook_end_s = video_segs[first_chron_idx].timeline_start_s

    clip_segs: dict[str, list[VideoSegment]] = {}
    clip_ranges: dict[str, tuple[float, float]] = {}
    for seg in video_segs:
        if hook_end_s > 0.0 and seg.timeline_end_s <= hook_end_s + 0.05:
            continue
        cid = Path(seg.clip_name).stem
        clip_segs.setdefault(cid, []).append(seg)
        if cid not in clip_ranges:
            clip_ranges[cid] = (seg.timeline_start_s, seg.timeline_end_s)
        else:
            lo, hi = clip_ranges[cid]
            clip_ranges[cid] = (min(lo, seg.timeline_start_s), max(hi, seg.timeline_end_s))

    # If flat video without V-NNN clip names, map V-NNN ranges from subtitle dialogue matching
    if not any(k.startswith("V-") for k in clip_ranges) and subs:
        for sc in sb.get("scenes", [])[1:]:
            for sh in (sc.get("shots") or sc.get("sfs") or []):
                cid = sh.get("id")
                dlg = (sh.get("text") or "").strip()
                if not cid or not dlg:
                    continue
                dw = _norm_words(dlg)
                if not dw:
                    continue
                matched_cues = [
                    cue for cue in subs
                    if len(dw & _norm_words(cue.get("text", ""))) >= max(2, int(len(dw) * 0.5))
                ]
                if matched_cues:
                    clip_ranges[cid] = (matched_cues[0]["start_s"], matched_cues[-1]["end_s"])

    clip_info: dict[str, dict[str, Any]] = {}
    sf_char_refs: dict[str, list[str]] = {}
    story_scenes: list[dict[str, Any]] = []
    probe_windows: list[str] = []

    for sc in sb.get("scenes", [])[1:]:
        sid = sc.get("id", "")
        sname = sc.get("name", sid)
        for sf_item in sc.get("sfs") or []:
            sf_id = sf_item.get("id")
            c_refs = (sf_item.get("refs") or {}).get("chars") or []
            if sf_id and c_refs:
                sf_char_refs[sf_id] = list(c_refs)
        shots = sc.get("shots") or sc.get("sfs") or []
        sc_clips = [sh.get("id") for sh in shots if sh.get("id") in clip_ranges]
        for sh in shots:
            cid = sh.get("id")
            if cid:
                raw_goc = sh.get("goc", "")
                mapped_goc = _map_shot_breakdown_to_timeline(raw_goc, clip_segs.get(cid, []))
                kept_slices = [
                    {
                        "timeline_s": [s.timeline_start_s, s.timeline_end_s],
                        "source_s": [s.source_start_s, round(s.source_start_s + s.source_dur_s, 2)],
                        "dur_s": s.timeline_dur_s,
                    }
                    for s in clip_segs.get(cid, [])
                ]
                clip_info[cid] = {
                    "scene_id": sid,
                    "scene_name": sname,
                    "sf": sh.get("sf", ""),
                    "prompt": sh.get("prompt", ""),
                    "raw_goc": raw_goc,
                    "notes": sh.get("notes", ""),
                    "dialogue": sh.get("text", ""),
                    "shot_breakdown": mapped_goc,
                    "kept_segments": kept_slices,
                }
        if sc_clips:
            first_c = sc_clips[0]
            last_c = sc_clips[-1]
            s_start = clip_ranges[first_c][0]
            s_end = clip_ranges[last_c][1]
            story_scenes.append(
                {
                    "scene_id": sid,
                    "scene_name": sname,
                    "start_s": s_start,
                    "end_s": s_end,
                    "first_clip": first_c,
                    "first_clip_window_s": list(clip_ranges[first_c]),
                    "first_clip_kept_segments": clip_info.get(first_c, {}).get("kept_segments", []),
                    "first_clip_shots": clip_info.get(first_c, {}).get("shot_breakdown", ""),
                }
            )
            w_lo = int(max(0.0, s_start))
            w_hi = int(min(s_end, s_start + 12.0)) + 1
            probe_windows.append(f"{w_lo}-{w_hi}")

    char_groups: dict[str, dict[str, Any]] = {}
    ref_sfs = (sb.get("scenes") or [{}])[0].get("sfs", [])
    for ref in ref_sfs:
        rid = str(ref.get("id") or "")
        m_char = re.match(r"^((?:CHAR|AL)\d+)", rid)
        m_named = re.match(r"^REF_([A-Z0-9]+)_", rid)
        if m_char:
            base_id = m_char.group(1)
        elif m_named and m_named.group(1) not in {"BG", "PROP", "PROPS", "LOC", "SCENE"}:
            base_id = m_named.group(1)
        else:
            continue
        # Only include clips that survive on the timeline with >= 1.2s duration
        used = [
            c for c in (ref.get("usedBy") or [])
            if c in clip_ranges and (clip_ranges[c][1] - clip_ranges[c][0]) >= 1.2
        ]
        if not used and m_named:
            char_token = m_named.group(1)
            for cid, ci in clip_info.items():
                if cid not in clip_ranges or (clip_ranges[cid][1] - clip_ranges[cid][0]) < 1.2:
                    continue
                sf_refs = sf_char_refs.get(ci.get("sf", ""), [])
                if rid in sf_refs or any(r.startswith(f"REF_{char_token}_") for r in sf_refs):
                    used.append(cid)
                elif re.search(rf"\b{re.escape(char_token)}\b", ci.get("raw_goc", "") + "\n" + ci.get("prompt", "")):
                    used.append(cid)
        lbl_str = ref.get("label") or ""
        desc_str = (ref.get("desc") or "").splitlines()[0]
        full_label = f"{lbl_str} — {desc_str}".strip(" —") if (lbl_str or desc_str) else rid
        entry = char_groups.setdefault(
            base_id,
            {
                "id": base_id,
                "label": full_label,
                "clips": [],
            },
        )
        for c in used:
            if c not in entry["clips"]:
                entry["clips"].append(c)

    char_appearances: list[dict[str, Any]] = []
    for base_id, info in sorted(char_groups.items()):
        clips_sorted = sorted(info["clips"], key=lambda c: clip_ranges[c][0])
        if not clips_sorted:
            continue
        first_clips = []
        for idx_c_clip, c in enumerate(clips_sorted[:2]):
            c_lo, c_hi = clip_ranges[c]
            ci = clip_info.get(c, {})
            first_clips.append(
                {
                    "clip": c,
                    "start_s": c_lo,
                    "end_s": c_hi,
                    "kept_segments": ci.get("kept_segments", []),
                    "notes": ci.get("notes", ""),
                    "dialogue": ci.get("dialogue", ""),
                    "shot_breakdown": ci.get("shot_breakdown", ""),
                }
            )
            if idx_c_clip == 0:
                probe_windows.append(f"{int(c_lo)}-{int(min(c_hi, c_lo + 14.0)) + 1}")
        char_appearances.append(
            {
                "character_id": base_id,
                "label": info["label"],
                "first_appearance_s": clip_ranges[clips_sorted[0]][0],
                "first_clips": first_clips,
            }
        )

    char_appearances.sort(key=lambda x: x["first_appearance_s"])
    # Merge overlapping probe windows (keeping each merged window <= 24s so dead gaps aren't probed)
    parsed_wins: list[tuple[int, int]] = []
    for pw in probe_windows:
        if "-" in pw:
            a_str, b_str = pw.split("-", 1)
            parsed_wins.append((int(a_str), int(b_str)))
    parsed_wins.sort()
    merged_wins: list[tuple[int, int]] = []
    for a_w, b_w in parsed_wins:
        if (
            merged_wins
            and a_w <= merged_wins[-1][1] + 2
            and max(merged_wins[-1][1], b_w) - merged_wins[-1][0] <= 24
        ):
            merged_wins[-1] = (merged_wins[-1][0], max(merged_wins[-1][1], b_w))
        else:
            merged_wins.append((a_w, b_w))

    rec_style = recommend_style_for_screenplay(sb, str(sf_board_path.parent.name))
    return {
        "screenplay_source": str(sf_board_path),
        "recommended_style": rec_style,
        "story_scenes": story_scenes,
        "character_appearances": char_appearances,
        "recommended_probe_windows": ",".join(f"{a}-{b}" for a, b in merged_wins),
    }


_STOP_PROPER_NOUNS: set[str] = {
    "the", "you", "your", "yours", "what", "why", "when", "where", "who", "whom", "whose", "how",
    "that", "this", "there", "they", "their", "them", "then", "these", "those", "she", "her", "hers",
    "his", "him", "he", "and", "but", "for", "nor", "not", "are", "was", "were", "will", "would",
    "could", "should", "shall", "may", "might", "must", "have", "has", "had", "can", "did", "does",
    "don't", "didn't", "doesn't", "won't", "can't", "isn't", "aren't", "wasn't", "weren't", "haven't",
    "hasn't", "hadn't", "wouldn't", "couldn't", "shouldn't", "let", "let's", "look", "listen", "wait",
    "stop", "get", "got", "come", "came", "take", "took", "give", "gave", "keep", "kept", "make",
    "made", "tell", "told", "call", "called", "move", "step", "hold", "stay", "leave", "left", "open",
    "close", "put", "bring", "send", "check", "read", "sign", "walk", "run", "sit", "stand", "turn",
    "back", "out", "off", "down", "over", "under", "here", "now", "yes", "yeah", "yep", "no", "nope",
    "okay", "well", "just", "only", "even", "still", "never", "always", "every", "all", "some", "any",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "first", "second",
    "third", "last", "next", "old", "new", "good", "bad", "right", "wrong", "sir", "ma'am", "madam",
    "mister", "miss", "mrs", "doctor", "captain", "chief", "officer", "agent", "judge", "coach",
    "dad", "mom", "father", "mother", "brother", "sister", "son", "daughter", "uncle", "aunt",
    "with", "from", "into", "onto", "upon", "about", "after", "before", "until", "while", "since",
    "because", "though", "although", "unless", "whether", "both", "either", "neither", "each",
    "much", "many", "more", "most", "other", "another", "such", "very", "too", "quite", "rather",
    "enough", "almost", "nearly", "already", "yet", "soon", "later", "today", "tonight", "tomorrow",
    "yesterday", "morning", "afternoon", "evening", "night", "day", "week", "month", "year",
    "man", "woman", "men", "women", "boy", "girl", "kid", "kids", "guy", "guys", "people", "person",
    "nobody", "somebody", "anybody", "everybody", "nothing", "something", "anything", "everything",
    "someone", "anyone", "everyone", "no", "none", "mine", "ours", "our", "we", "us", "it", "its",
}


def recommend_style_for_screenplay(sb: dict[str, Any], project_name: str = "") -> dict[str, Any]:
    """
    Synthesize a world-matched Cinema Art-Direction Style (`style` dict) directly from the screenplay
    (`sf-board.json`), selecting from 8 distinct film archetypes so every film gets a bespoke
    typography pairing, color palette, flankers, and alignment.
    """
    text_chunks: list[str] = [project_name]
    for sc in sb.get("scenes", []):
        text_chunks.append(str(sc.get("name") or ""))
        for sf_item in sc.get("sfs") or []:
            text_chunks.append(str(sf_item.get("label") or ""))
            text_chunks.append(str(sf_item.get("desc") or "")[:200])
        for sh in (sc.get("shots") or [])[:15]:
            text_chunks.append(str(sh.get("notes") or ""))
            text_chunks.append(str(sh.get("text") or ""))
    corpus = " ".join(text_chunks).lower()

    archetypes: list[tuple[str, set[str], dict[str, Any]]] = [
        (
            "coastal_lifeguard_rescue",
            {"lifeguard", "beach", "ocean", "surf", "shoreline", "pier", "bay", "tide", "coral", "marina", "boathouse", "jetty", "coast"},
            {
                "archetype": "coastal_lifeguard_rescue",
                "title_font": "Cinzel-Bold",
                "detail_font": "CormorantGaramond-BoldItalic",
                "scene_title_font": "PlayfairDisplay-Bold",
                "scene_detail_font": "CormorantGaramond-BoldItalic",
                "end_title_font": "Cinzel-Bold",
                "end_detail_font": "CormorantGaramond-BoldItalic",
                "title_size": 6.8,
                "detail_size": 4.3,
                "scene_title_size": 6.6,
                "scene_detail_size": 4.1,
                "end_title_size": 8.0,
                "end_detail_size": 4.3,
                "detail_uppercase": False,
                "char_title_color": "#F3CA6E",
                "char_detail_color": "#F6EFE2",
                "detail_accent_color": "#F2CE7E",
                "time_title_color": "#FBF5E8",
                "time_detail_color": "#EFE2C8",
                "scene_accent_color": "#F3CA6E",
                "flanker_color": "#D8B268",
                "stroke_color": "#0E0B08",
                "stroke_width": 0.015,
                "shadow_color": "#050403",
                "shadow_alpha": 0.94,
                "shadow_smoothing": 0.42,
                "shadow_distance": 2.4,
                "flankers": "—",
                "scene_flankers": "·",
                "stagger_sec": 0.10,
                "align": "center",
                "order": "title-first",
                "scene_order": "detail-first",
                "line_gap": 0.15,
            },
        ),
        (
            "equestrian_heritage_estate",
            {"stallion", "horse", "stable", "equestrian", "thoroughbred", "paddock", "bridle", "dressage", "barn", "foal", "mare", "colt"},
            {
                "archetype": "equestrian_heritage_estate",
                "title_font": "PlayfairDisplay-Bold",
                "detail_font": "CormorantGaramond-BoldItalic",
                "scene_title_font": "PlayfairDisplay-Bold",
                "scene_detail_font": "CormorantGaramond-BoldItalic",
                "end_title_font": "Cinzel-Bold",
                "end_detail_font": "CormorantGaramond-BoldItalic",
                "title_size": 6.8,
                "detail_size": 4.3,
                "scene_title_size": 6.6,
                "scene_detail_size": 4.1,
                "end_title_size": 8.0,
                "end_detail_size": 4.3,
                "detail_uppercase": False,
                "char_title_color": "#F3CA6E",
                "char_detail_color": "#F6EFE2",
                "detail_accent_color": "#F2CE7E",
                "time_title_color": "#FBF5E8",
                "time_detail_color": "#EFE2C8",
                "scene_accent_color": "#F3CA6E",
                "flanker_color": "#D8B268",
                "stroke_color": "#0E0B08",
                "stroke_width": 0.015,
                "shadow_color": "#050403",
                "shadow_alpha": 0.94,
                "shadow_smoothing": 0.42,
                "shadow_distance": 2.4,
                "flankers": "—",
                "scene_flankers": "·",
                "stagger_sec": 0.10,
                "align": "center",
                "order": "title-first",
                "scene_order": "detail-first",
                "line_gap": 0.15,
            },
        ),
        (
            "legal_corporate_dynasty",
            {"courtroom", "lawyer", "attorney", "judge", "deposition", "boardroom", "ceo", "executive", "penthouse", "billionaire", "trust", "inheritance", "hospital", "surgeon", "clinic"},
            {
                "archetype": "legal_corporate_dynasty",
                "title_font": "PlayfairDisplay-Bold",
                "detail_font": "CormorantGaramond-BoldItalic",
                "scene_title_font": "PlayfairDisplay-Bold",
                "scene_detail_font": "CormorantGaramond-BoldItalic",
                "end_title_font": "Cinzel-Bold",
                "end_detail_font": "CormorantGaramond-BoldItalic",
                "title_size": 6.8,
                "detail_size": 4.3,
                "scene_title_size": 6.6,
                "scene_detail_size": 4.1,
                "end_title_size": 8.0,
                "end_detail_size": 4.3,
                "detail_uppercase": False,
                "char_title_color": "#F3CA6E",
                "char_detail_color": "#F6EFE2",
                "detail_accent_color": "#F2CE7E",
                "time_title_color": "#FBF5E8",
                "time_detail_color": "#EFE2C8",
                "scene_accent_color": "#F3CA6E",
                "flanker_color": "#D8B268",
                "stroke_color": "#0E0B08",
                "stroke_width": 0.015,
                "shadow_color": "#050403",
                "shadow_alpha": 0.94,
                "shadow_smoothing": 0.42,
                "shadow_distance": 2.4,
                "flankers": "—",
                "scene_flankers": "·",
                "stagger_sec": 0.10,
                "align": "center",
                "order": "title-first",
                "scene_order": "detail-first",
                "line_gap": 0.15,
            },
        ),
        (
            "military_tactical_thriller",
            {"military", "colonel", "general", "sergeant", "veteran", "tactical", "hangar", "radar", "bunker", "precinct", "detective", "federal", "swat", "convoy"},
            {
                "archetype": "military_tactical_thriller",
                "title_font": "Cinzel-Bold",
                "detail_font": "CormorantGaramond-BoldItalic",
                "scene_title_font": "Cinzel-Bold",
                "scene_detail_font": "CormorantGaramond-BoldItalic",
                "end_title_font": "Cinzel-Bold",
                "end_detail_font": "CormorantGaramond-BoldItalic",
                "title_size": 6.8,
                "detail_size": 4.3,
                "scene_title_size": 6.6,
                "scene_detail_size": 4.1,
                "end_title_size": 8.0,
                "end_detail_size": 4.3,
                "detail_uppercase": False,
                "char_title_color": "#F3CA6E",
                "char_detail_color": "#F6EFE2",
                "detail_accent_color": "#F2CE7E",
                "time_title_color": "#FBF5E8",
                "time_detail_color": "#EFE2C8",
                "scene_accent_color": "#F3CA6E",
                "flanker_color": "#D8B268",
                "stroke_color": "#0E0B08",
                "stroke_width": 0.015,
                "shadow_color": "#050403",
                "shadow_alpha": 0.94,
                "shadow_smoothing": 0.42,
                "shadow_distance": 2.4,
                "flankers": "—",
                "scene_flankers": "·",
                "stagger_sec": 0.10,
                "align": "center",
                "order": "title-first",
                "scene_order": "detail-first",
                "line_gap": 0.15,
            },
        ),
        (
            "high_society_gala_drama",
            {"gala", "ballroom", "symphony", "violin", "piano", "opera", "couture", "auction", "gallery", "chandelier", "conservatory", "banquet"},
            {
                "archetype": "high_society_gala_drama",
                "title_font": "PlayfairDisplay-Bold",
                "detail_font": "CormorantGaramond-BoldItalic",
                "scene_title_font": "PlayfairDisplay-Bold",
                "scene_detail_font": "CormorantGaramond-BoldItalic",
                "end_title_font": "Cinzel-Bold",
                "end_detail_font": "CormorantGaramond-BoldItalic",
                "title_size": 6.8,
                "detail_size": 4.3,
                "scene_title_size": 6.6,
                "scene_detail_size": 4.1,
                "end_title_size": 8.0,
                "end_detail_size": 4.3,
                "detail_uppercase": False,
                "char_title_color": "#F3CA6E",
                "char_detail_color": "#F6EFE2",
                "detail_accent_color": "#F2CE7E",
                "time_title_color": "#FBF5E8",
                "time_detail_color": "#EFE2C8",
                "scene_accent_color": "#F3CA6E",
                "flanker_color": "#D8B268",
                "stroke_color": "#0E0B08",
                "stroke_width": 0.015,
                "shadow_color": "#050403",
                "shadow_alpha": 0.94,
                "shadow_smoothing": 0.42,
                "shadow_distance": 2.4,
                "flankers": "—",
                "scene_flankers": "·",
                "stagger_sec": 0.10,
                "align": "center",
                "order": "title-first",
                "scene_order": "detail-first",
                "line_gap": 0.15,
            },
        ),
        (
            "rustic_heartland_americana",
            {"diner", "farmhouse", "tractor", "sheriff", "county", "porch", "bakery", "orchard", "harvest", "mill", "workshop", "mechanic", "truck", "cafe", "ribs", "smoker", "pitmaster", "barbecue"},
            {
                "archetype": "rustic_heartland_americana",
                "title_font": "PlayfairDisplay-Bold",
                "detail_font": "CormorantGaramond-BoldItalic",
                "scene_title_font": "PlayfairDisplay-Bold",
                "scene_detail_font": "CormorantGaramond-BoldItalic",
                "end_title_font": "Cinzel-Bold",
                "end_detail_font": "CormorantGaramond-BoldItalic",
                "title_size": 6.8,
                "detail_size": 4.3,
                "scene_title_size": 6.6,
                "scene_detail_size": 4.1,
                "end_title_size": 8.0,
                "end_detail_size": 4.3,
                "detail_uppercase": False,
                "char_title_color": "#F3CA6E",
                "char_detail_color": "#F6EFE2",
                "detail_accent_color": "#F2CE7E",
                "time_title_color": "#FBF5E8",
                "time_detail_color": "#EFE2C8",
                "scene_accent_color": "#F3CA6E",
                "flanker_color": "#D8B268",
                "stroke_color": "#0E0B08",
                "stroke_width": 0.015,
                "shadow_color": "#050403",
                "shadow_alpha": 0.94,
                "shadow_smoothing": 0.42,
                "shadow_distance": 2.4,
                "flankers": "—",
                "scene_flankers": "·",
                "stagger_sec": 0.10,
                "align": "center",
                "order": "title-first",
                "scene_order": "detail-first",
                "line_gap": 0.15,
            },
        ),
    ]

    best_arch = None
    best_hits = 0
    for _, kw_set, style_dict in archetypes:
        hits = sum(corpus.count(kw) for kw in kw_set)
        if hits > best_hits:
            best_hits = hits
            best_arch = style_dict

    if best_arch is not None and best_hits > 0:
        return dict(best_arch)

    return {
        "archetype": "modern_prestige_drama",
        "title_font": "PlayfairDisplay-Bold",
        "detail_font": "CormorantGaramond-BoldItalic",
        "scene_title_font": "PlayfairDisplay-Bold",
        "scene_detail_font": "CormorantGaramond-BoldItalic",
        "end_title_font": "Cinzel-Bold",
        "end_detail_font": "CormorantGaramond-BoldItalic",
        "title_size": 6.8,
        "detail_size": 4.3,
        "scene_title_size": 6.6,
        "scene_detail_size": 4.1,
        "end_title_size": 8.0,
        "end_detail_size": 4.3,
        "detail_uppercase": False,
        "char_title_color": "#F3CA6E",
        "char_detail_color": "#F6EFE2",
        "detail_accent_color": "#F2CE7E",
        "time_title_color": "#FBF5E8",
        "time_detail_color": "#EFE2C8",
        "scene_accent_color": "#F3CA6E",
        "flanker_color": "#D8B268",
        "stroke_color": "#0E0B08",
        "stroke_width": 0.015,
        "shadow_color": "#050403",
        "shadow_alpha": 0.94,
        "shadow_smoothing": 0.42,
        "shadow_distance": 2.4,
        "flankers": "—",
        "scene_flankers": "·",
        "stagger_sec": 0.10,
        "align": "center",
        "order": "title-first",
        "scene_order": "detail-first",
        "line_gap": 0.15,
    }


def build_screenplay_subtitle_context(
    video_segs: list[VideoSegment],
    subs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build a screenplay-grounded normalization context from `sf-board.json` (and any `*KICHBAN*.txt`
    in the project directory) for `style_subtitle_track_in_place()`:
    - `shot_windows`: timeline `[start_s, end_s]` intervals paired with exact screenplay dialogue (`sh["text"]`)
    - `proper_nouns`: canonical casing map (`lower -> ProperCase`) for all character names, surnames, and locations
    - `valid_lower_vocab`: set of all lowercase vocabulary words in the screenplay
    - `canonical_phrases`: compiled regexes for numbered clauses (`Clause 9`, `Stall 9`) and multi-word proper names (`Coral Reach`)
    - `recommended_style`: world-matched Cinema Art-Direction Style
    """
    sf_board_path: Path | None = None
    for seg in video_segs:
        if not seg.path:
            continue
        p = Path(seg.path)
        for parent in (p.parent, p.parent.parent):
            cand = parent / "sf-board.json"
            if cand.exists():
                sf_board_path = cand
                break
        if sf_board_path:
            break

    if not sf_board_path and subs:
        sub_blob = " ".join(c.get("text", "") for c in subs[:40]).lower()
        sub_words = _norm_words(sub_blob)
        ws_root = Path("/Users/daho100/Documents/SF Board")
        if ws_root.exists() and sub_words:
            cands = list(ws_root.glob("*.project/sf-board.json"))
            min_hits = max(6, int(len(sub_words) * 0.35))

            def _score_cand(cand: Path) -> tuple[int, Path]:
                try:
                    raw = cand.read_text(encoding="utf-8")[:60000].lower()
                    return sum(1 for w in sub_words if w in raw), cand
                except Exception:
                    return 0, cand

            if cands:
                with ThreadPoolExecutor(max_workers=min(DEFAULT_MAX_WORKERS, len(cands))) as pool:
                    scored = list(pool.map(_score_cand, cands))
                best_score, best_cand = max(scored, key=lambda x: x[0])
                if best_score >= min_hits:
                    sf_board_path = best_cand

    if not sf_board_path:
        return {}

    try:
        sb = json.loads(sf_board_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    clip_ranges: dict[str, list[tuple[float, float]]] = {}
    for seg in video_segs:
        cid = Path(seg.clip_name).stem
        clip_ranges.setdefault(cid, []).append((seg.timeline_start_s, seg.timeline_end_s))

    shot_windows: list[tuple[float, float, str]] = []
    char_proper_nouns: dict[str, str] = {}
    mid_sentence_proper_nouns: dict[str, str] = {}
    lowercase_seen: set[str] = set()
    valid_lower_vocab: set[str] = set()
    phrase_candidates: set[str] = set()

    def _harvest_dialogue_or_notes(txt: str) -> None:
        if not txt:
            return
        for w in re.findall(r"[A-Za-z][A-Za-z0-9'-]*", txt):
            wl = w.lower()
            valid_lower_vocab.add(wl)
            if w.islower():
                lowercase_seen.add(wl)
                lowercase_seen.add(wl.rstrip("s"))
        # Harvest mid-sentence TitleCase words (preceded by a lowercase word and space)
        for m_mid in re.finditer(r"(?<=[a-z]\s)([A-Z][a-z]{2,})\b", txt):
            w = m_mid.group(1)
            wl = w.lower()
            if wl not in _STOP_PROPER_NOUNS:
                mid_sentence_proper_nouns[wl] = w
        # Numbered designations like Clause 9, Stall 9, Gate 4, Section 7, Pier 3, Row 4
        for m_num in re.finditer(r"\b([A-Z][a-z]+)\s+(\d+)\b", txt):
            phrase_candidates.add(f"{m_num.group(1)} {m_num.group(2)}")
        # Multi-word capitalized proper names (e.g. Coral Reach, South Door, Tamarack Estate)
        for m_prop in re.finditer(r"\b([A-Z][a-z]{2,})\s+([A-Z][a-z]{2,})\b", txt):
            w1, w2 = m_prop.group(1), m_prop.group(2)
            if w1.lower() not in _STOP_PROPER_NOUNS and w2.lower() not in _STOP_PROPER_NOUNS:
                phrase_candidates.add(f"{w1} {w2}")

    # Harvest character names from scenes[0].sfs (only CHAR/AL/named character refs, not BG/PROP)
    for ref in (sb.get("scenes") or [{}])[0].get("sfs", []):
        rid = str(ref.get("id") or "")
        is_char_ref = bool(
            re.match(r"^(?:CHAR|AL)\d+", rid)
            or (re.match(r"^REF_([A-Z0-9]+)_", rid) and not re.match(r"^REF_(?:BG|PROP|PROPS|LOC|SCENE)_", rid))
        )
        lbl = str(ref.get("label") or "")
        lbl_head = lbl.split("—")[0].split("-")[0].split("(")[0].strip()
        if is_char_ref and lbl_head:
            title_words = [
                w.capitalize() if w.isupper() else w
                for w in re.findall(r"[A-Za-z][A-Za-z'-]*", lbl_head)
                if len(w) >= 3 and w.lower() not in _STOP_PROPER_NOUNS
            ]
            for tw in title_words:
                char_proper_nouns[tw.lower()] = tw
                valid_lower_vocab.add(tw.lower())
            if len(title_words) == 2:
                phrase_candidates.add(f"{title_words[0]} {title_words[1]}")
        _harvest_dialogue_or_notes(str(ref.get("desc") or "")[:400])

    # Harvest scenes and shot dialogues
    for sc in sb.get("scenes", [])[1:]:
        sname = str(sc.get("name") or "")
        for m_sc_prop in re.finditer(r"\b([A-Z]{3,})\s+([A-Z]{3,})\b", sname):
            w1, w2 = m_sc_prop.group(1).capitalize(), m_sc_prop.group(2).capitalize()
            if w1.lower() not in _STOP_PROPER_NOUNS and w2.lower() not in _STOP_PROPER_NOUNS:
                phrase_candidates.add(f"{w1} {w2}")
        for sh in (sc.get("shots") or sc.get("sfs") or []):
            cid = sh.get("id")
            dlg = str(sh.get("text") or "").strip()
            notes = str(sh.get("notes") or "").strip()
            _harvest_dialogue_or_notes(dlg)
            _harvest_dialogue_or_notes(notes)
            if cid and dlg and cid in clip_ranges:
                for lo_s, hi_s in clip_ranges[cid]:
                    shot_windows.append((lo_s, hi_s, dlg))

    # Also check for any *KICHBAN*.txt in the project directory
    proj_folder = sf_board_path.parent
    for kb_file in list(proj_folder.glob("*KICHBAN*.txt")) + list(proj_folder.glob("*kichban*.txt")):
        try:
            _harvest_dialogue_or_notes(kb_file.read_text(encoding="utf-8")[:80000])
        except Exception:
            pass

    # Combine character proper nouns + mid-sentence proper nouns that never appear in lowercase
    proper_nouns: dict[str, str] = {}
    for k, v in mid_sentence_proper_nouns.items():
        if k not in lowercase_seen:
            proper_nouns[k] = v
    for k, v in char_proper_nouns.items():
        proper_nouns[k] = v

    # Build canonical phrase regexes
    canonical_phrases: list[tuple[re.Pattern[str], str]] = []
    homophone_map: dict[str, str] = {
        "clause": r"(?:clause|claws|close|clothes|claus)",
        "stall": r"(?:stall|stole|still|tall)",
        "pier": r"(?:pier|peer|beer)",
    }
    for phr in sorted(phrase_candidates):
        parts = phr.split()
        if len(parts) == 2 and parts[1].isdigit():
            w1_l = parts[0].lower()
            pat_w1 = homophone_map.get(w1_l, re.escape(parts[0]))
            canonical_phrases.append(
                (re.compile(rf"\b{pat_w1}\s+{re.escape(parts[1])}\b", re.I), phr)
            )
        elif len(parts) == 2:
            w1, w2 = parts[0], parts[1]
            # Exact case-insensitive match
            canonical_phrases.append(
                (re.compile(rf"\b{re.escape(w1)}\s+{re.escape(w2)}\b", re.I), phr)
            )
            # Phonetic neighbor on second word when first word matches and second word starts with same 3 letters (e.g. Coral Reef -> Coral Reach)
            if len(w2) >= 4:
                prefix3 = re.escape(w2[:3])
                canonical_phrases.append(
                    (re.compile(rf"\b{re.escape(w1)}\s+{prefix3}[a-z]+\b", re.I), phr)
                )

    rec_style = recommend_style_for_screenplay(sb, str(sf_board_path.parent.name))
    return {
        "shot_windows": shot_windows,
        "proper_nouns": proper_nouns,
        "valid_lower_vocab": valid_lower_vocab,
        "canonical_phrases": canonical_phrases,
        "recommended_style": rec_style,
    }


def cmd_inspect(args: argparse.Namespace) -> int:
    project_dir = resolve_project_dir(args.project)
    draft = load_draft(project_dir)
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_vsegs = pool.submit(load_video_timeline, draft)
        f_subs = pool.submit(extract_subtitles, draft)
        f_cards = pool.submit(extract_existing_cards, draft)
        video_segs = f_vsegs.result()
        subs = f_subs.result()
        cards = f_cards.result()
        f_scenes = pool.submit(group_scene_boundaries, video_segs)
        f_gt = pool.submit(extract_screenplay_ground_truth, video_segs, subs)
        scenes = f_scenes.result()
        gt = f_gt.result()

    sub_status = (
        "ready"
        if subs
        else "none_in_draft_do_not_search_other_files (auto-captions not generated in CapCut yet)"
    )

    payload = {
        "project": project_dir.name,
        "project_dir": str(project_dir),
        "duration_sec": (
            video_segs[-1].timeline_end_s
            if video_segs
            else round(float(draft.get("duration", 0)) / 1e6, 3)
        ),
        "video_segment_count": len(video_segs),
        "scene_count": len(gt.get("story_scenes") or scenes),
        "recommended_style": gt.get("recommended_style", {}),
        "story_scenes": gt.get("story_scenes") or scenes,
        "character_appearances": gt.get("character_appearances", []),
        "recommended_probe_windows": gt.get("recommended_probe_windows", ""),
        "screenplay_source": gt.get("screenplay_source"),
        "video_segments": [
            {
                "index": s.index,
                "start_s": s.timeline_start_s,
                "end_s": s.timeline_end_s,
                "dur_s": s.timeline_dur_s,
                "src_start_s": s.source_start_s,
                "clip": s.clip_name,
            }
            for s in video_segs
        ],
        "existing_card_segment_count": len(cards),
        "existing_cards": cards,
        "subtitle_cue_count": len(subs),
        "subtitle_status": sub_status,
        "subtitles": subs,
    }

    out_path = (
        Path(os.path.expanduser(args.out))
        if getattr(args, "out", None)
        else Path(f"/tmp/inspect_{project_dir.name}.json")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                "project": payload["project"],
                "duration_sec": payload["duration_sec"],
                "video_segment_count": payload["video_segment_count"],
                "scene_count": payload["scene_count"],
                "character_count": len(payload.get("character_appearances", [])),
                "screenplay_source": payload.get("screenplay_source"),
                "recommended_style_archetype": (payload.get("recommended_style") or {}).get("archetype"),
                "recommended_probe_windows": payload.get("recommended_probe_windows", ""),
                "existing_card_segment_count": payload["existing_card_segment_count"],
                "subtitle_cue_count": payload["subtitle_cue_count"],
                "subtitle_status": sub_status,
                "saved_to": str(out_path),
            },
            indent=2,
        )
    )
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    project_dir = resolve_project_dir(args.project)
    draft = load_draft(project_dir)
    video_segs = load_video_timeline(draft)
    if not video_segs:
        raise RuntimeError(f"No video segments found in {project_dir}")

    out_dir = Path(os.path.expanduser(args.out))
    out_dir.mkdir(parents=True, exist_ok=True)
    for old_f in list(out_dir.glob("sheet_*.jpg")) + list(out_dir.glob("probe_batch_*.jpg")):
        old_f.unlink(missing_ok=True)
    frames_dir = out_dir / "frames"
    shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    raw_windows = [w.strip() for w in (args.windows or "").split(",") if w.strip()]
    windows: list[tuple[float, float]] = []
    for rw in raw_windows:
        if "-" in rw:
            a, b = rw.split("-", 1)
            windows.append((max(0.0, float(a)), float(b)))
        else:
            t = float(rw)
            windows.append((max(0.0, t - 1.0), t + 5.0))

    fast_cuts = extract_fast_timeline_cuts(video_segs)

    # Phase 1: Compute window cuts across all windows in parallel
    def _compute_window_cuts(item: tuple[int, tuple[float, float]]) -> dict[str, Any]:
        w_idx, (w_start, w_end) = item
        win_fast = [c for c in fast_cuts if w_start + 0.15 < c < w_end - 0.15]
        if getattr(args, "scdet", False) or not win_fast:
            cuts_info = detect_window_cuts(video_segs, w_start, w_end)
            all_cuts = sorted(set(cuts_info["all_cuts"] + win_fast))
            seg_cuts = cuts_info["segment_cuts"]
            scdet_cuts = cuts_info["scdet_cuts"]
        else:
            seg_cuts = [
                round(s.timeline_start_s, 2)
                for s in video_segs
                if w_start < s.timeline_start_s < w_end
            ]
            scdet_cuts = [c for c in win_fast if c not in seg_cuts]
            all_cuts = sorted(set(win_fast))

        boundaries = [w_start] + [c for c in all_cuts if w_start < c < w_end] + [w_end]
        sub_intervals: list[tuple[float, float, float, Path]] = []
        for i in range(len(boundaries) - 1):
            a, b = round(boundaries[i], 2), round(boundaries[i + 1], 2)
            if b - a >= 1.2:
                mid_t = round((a + b) * 0.5, 2)
                f_jpg = frames_dir / f"w{w_idx:02d}_{int(round(mid_t*100)):06d}.jpg"
                sub_intervals.append((a, b, mid_t, f_jpg))
        return {
            "w_idx": w_idx,
            "w_start": w_start,
            "w_end": w_end,
            "seg_cuts": seg_cuts,
            "scdet_cuts": scdet_cuts,
            "all_cuts": all_cuts,
            "sub_intervals": sub_intervals,
        }

    with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as pool:
        win_metas = list(pool.map(_compute_window_cuts, enumerate(windows, start=1)))

    # Phase 2: Flatten all frame extractions + negative-space scoring across all windows into one parallel pool
    flat_frame_tasks: list[tuple[int, float, float, float, Path]] = []
    for wm in win_metas:
        w_idx = wm["w_idx"]
        for a, b, mid_t, f_jpg in wm["sub_intervals"]:
            flat_frame_tasks.append((w_idx, a, b, mid_t, f_jpg))

    def _extract_and_score(task: tuple[int, float, float, float, Path]) -> tuple[int, float, float, float, Path, bool, str, str]:
        w_idx, a, b, mid_t, f_jpg = task
        ok, cname = extract_frame_at_timeline_sec(video_segs, mid_t, f_jpg)
        best_anc = score_frame_negative_space(f_jpg).get("best_anchor", "lower-left") if (ok and f_jpg.exists()) else "lower-left"
        return (w_idx, a, b, mid_t, f_jpg, ok, cname, best_anc)

    flat_results: list[tuple[int, float, float, float, Path, bool, str, str]] = []
    if flat_frame_tasks:
        with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as pool:
            flat_results = list(pool.map(_extract_and_score, flat_frame_tasks))

    by_win: dict[int, list[tuple[float, float, float, Path, bool, str, str]]] = {}
    for w_idx, a, b, mid_t, f_jpg, ok, cname, best_anc in flat_results:
        by_win.setdefault(w_idx, []).append((a, b, mid_t, f_jpg, ok, cname, best_anc))

    # Phase 3: Build per-window contact sheets and overview batch sheets in parallel
    report_windows: list[dict[str, Any]] = []
    all_frame_items: list[tuple[float, str, Path]] = []
    sheet_jobs: list[tuple[list[tuple[float, str, Path]], Path, int]] = []

    for wm in win_metas:
        w_idx = wm["w_idx"]
        w_start, w_end = wm["w_start"], wm["w_end"]
        w_items = by_win.get(w_idx, [])
        frame_items: list[tuple[float, str, Path]] = []
        sub_shots: list[dict[str, Any]] = []
        for a, b, mid_t, f_jpg, ok, cname, best_anc in w_items:
            if ok:
                frame_items.append((mid_t, cname, f_jpg))
                all_frame_items.append((mid_t, f"{a:.1f}-{b:.1f}s ({best_anc})", f_jpg))
            sub_shots.append(
                {
                    "start_s": a,
                    "end_s": b,
                    "dur_s": round(b - a, 2),
                    "best_anchor": best_anc,
                }
            )
        sheet_path = out_dir / f"sheet_{w_idx:02d}_{int(w_start):04d}_{int(w_end):04d}.jpg"
        if frame_items:
            sheet_jobs.append((frame_items, sheet_path, 4))
        report_windows.append(
            {
                "window": f"{w_start:.2f}-{w_end:.2f}s",
                "segment_cuts": wm["seg_cuts"],
                "scdet_cuts": wm["scdet_cuts"],
                "all_cuts": wm["all_cuts"],
                "sub_shots": sub_shots,
                "contact_sheet": str(sheet_path) if frame_items else None,
            }
        )

    batch_paths: list[Path] = []
    batch_size = 24
    for b_idx in range(0, len(all_frame_items), batch_size):
        chunk = all_frame_items[b_idx : b_idx + batch_size]
        b_path = out_dir / f"probe_batch_{(b_idx // batch_size) + 1:02d}.jpg"
        batch_paths.append(b_path)
        sheet_jobs.append((chunk, b_path, 4))

    if sheet_jobs:
        with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as pool:
            list(pool.map(lambda jb: build_contact_sheet(jb[0], jb[1], cols=jb[2]), sheet_jobs))

    batch_sheets = [str(bp) for bp in batch_paths if bp.exists()]

    report_path = out_dir / "probe_report.json"
    out_payload = {
        "project": project_dir.name,
        "report": str(report_path),
        "batch_sheets": batch_sheets,
        "windows": report_windows,
    }
    with report_path.open("w", encoding="utf-8") as fh:
        json.dump(out_payload, fh, indent=2)
    print(
        json.dumps(
            {
                "project": project_dir.name,
                "window_count": len(report_windows),
                "sub_shot_count": len(all_frame_items),
                "batch_sheets": batch_sheets,
                "saved_report": str(report_path),
            },
            indent=2,
        )
    )
    return 0


def render_preview_sheet(
    draft: dict[str, Any],
    applied_cards: list[dict[str, Any]],
    preset: FilmCardStyle,
    out_sheet_path: Path,
) -> tuple[str | None, list[str]]:
    video_segs = load_video_timeline(draft)
    if not video_segs or not applied_cards:
        return None, []
    tmp_dir = out_sheet_path.parent / f"_preview_frames_{out_sheet_path.stem}"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for old_p in out_sheet_path.parent.glob(f"{out_sheet_path.stem}_p*.jpg"):
        old_p.unlink(missing_ok=True)

    card_specs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for c in applied_cards:
        raw_c = c.pop("_raw_card", None) or dict(c)
        card_specs.append((c, raw_c))

    def _render_one(pair: tuple[dict[str, Any], dict[str, Any]]) -> tuple[int, Path | None]:
        c, raw_c = pair
        idx_c = int(c["index"])
        mid_t = round((float(c["start_s"]) + float(c["end_s"])) * 0.5, 2)
        raw_jpg = tmp_dir / f"raw_{idx_c:02d}.jpg"
        comp_jpg = tmp_dir / f"comp_{idx_c:02d}.jpg"
        ok, _ = extract_frame_at_timeline_sec(
            video_segs, mid_t, raw_jpg, width=960, height=540, include_guides=False
        )
        if not ok:
            return idx_c, None
        t_st, d_st, _, _ = resolve_card_styles(raw_c, preset)
        lbl = f"#{idx_c:02d} {c['start_s']:.1f}-{c['end_s']:.1f}s | x={c['x']:+.2f} y={c['y_main']:+.2f} sc={c['scale']:.2f}"
        if render_card_on_frame(
            raw_jpg,
            comp_jpg,
            title_text=c["title"],
            detail_text=c["detail"],
            title_style=t_st,
            detail_style=d_st,
            x=float(c["x"]),
            x_detail=float(c.get("x_detail", c["x"])),
            y_main=float(c["y_main"]),
            y_detail=float(c["y_detail"]),
            scale=float(c["scale"]),
            label=lbl,
        ):
            return idx_c, comp_jpg
        return idx_c, None

    with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as pool:
        res_list = sorted(pool.map(_render_one, card_specs), key=lambda x: x[0])

    rendered_items = [p for _, p in res_list if p is not None]
    if not rendered_items:
        return None, []

    from PIL import Image

    tw, th = 480, 270
    out_sheet_path.parent.mkdir(parents=True, exist_ok=True)

    def _save_grid(job: tuple[list[Path], Path, int, int]) -> str:
        items_p, target_p, g_cols, qual = job
        g_rows = (len(items_p) + g_cols - 1) // g_cols
        grid_im = Image.new("RGB", (g_cols * tw, g_rows * th), (12, 14, 18))
        for k, p in enumerate(items_p):
            try:
                with Image.open(p) as im:
                    grid_im.paste(im.resize((tw, th)), ((k % g_cols) * tw, (k // g_cols) * th))
            except Exception:
                pass
        grid_im.save(target_p, quality=qual)
        return str(target_p)

    cols = 4 if len(rendered_items) > 12 else 3
    grid_jobs: list[tuple[list[Path], Path, int, int]] = [(rendered_items, out_sheet_path, cols, 82)]
    if len(rendered_items) > 16:
        per_page = 16
        for pg_idx in range(0, len(rendered_items), per_page):
            chunk = rendered_items[pg_idx : pg_idx + per_page]
            pg_num = (pg_idx // per_page) + 1
            pg_file = out_sheet_path.parent / f"{out_sheet_path.stem}_p{pg_num}.jpg"
            grid_jobs.append((chunk, pg_file, 4, 84))

    with ThreadPoolExecutor(max_workers=min(DEFAULT_MAX_WORKERS, len(grid_jobs))) as pool:
        saved_grids = list(pool.map(_save_grid, grid_jobs))

    return saved_grids[0], saved_grids[1:]


def cmd_apply(args: argparse.Namespace) -> int:
    project_dir = resolve_project_dir(args.project)
    plan_path = Path(os.path.expanduser(args.plan))
    with plan_path.open("r", encoding="utf-8") as fh:
        plan = json.load(fh)

    draft = load_draft(project_dir)
    summary = apply_plan_to_draft(
        draft,
        plan,
        snap_to_cuts=not bool(getattr(args, "no_snap_cuts", False)),
    )
    preset = summary.pop("_preset")

    if not getattr(args, "dry_run", False):
        synced = save_and_sync_draft(project_dir, draft)
        summary["synced_files"] = synced
    else:
        summary["dry_run"] = True

    if getattr(args, "no_preview", False) or getattr(args, "preview", None) == "":
        for c in summary["cards"]:
            c.pop("_raw_card", None)
    else:
        preview_target = (
            Path(os.path.expanduser(args.preview))
            if getattr(args, "preview", None)
            else plan_path.parent / f"preview_{plan_path.stem}.jpg"
        )
        preview_sheet, preview_pages = render_preview_sheet(draft, summary["cards"], preset, preview_target)
        if preview_sheet:
            summary["preview_sheet"] = preview_sheet
        if preview_pages:
            summary["preview_pages"] = preview_pages

    applied_log_path = plan_path.parent / f"applied_{plan_path.stem}.json"
    with applied_log_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    compact_stdout = {
        k: v
        for k, v in summary.items()
        if k != "cards"
    }
    compact_stdout["applied_cards_log"] = str(applied_log_path)
    print(json.dumps(compact_stdout, ensure_ascii=False, indent=2))
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    project_dir = resolve_project_dir(args.project)
    draft = load_draft(project_dir)
    strip_card_tracks(draft)
    synced = save_and_sync_draft(project_dir, draft)
    print(json.dumps({"project": project_dir.name, "cleared": True, "synced_files": synced}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fast native CapCut cinematic cards & in-place subtitle styling engine."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ins = sub.add_parser("inspect", help="Inspect video timeline, scene boundaries, cards, and subtitles.")
    p_ins.add_argument("project", help="CapCut project name or path")
    p_ins.add_argument("--out", help="Optional JSON output path")
    p_ins.set_defaults(func=cmd_inspect)

    p_prb = sub.add_parser("probe", help="Detect shot cuts (segment + scdet) and render labeled contact sheets.")
    p_prb.add_argument("project", help="CapCut project name or path")
    p_prb.add_argument("--windows", required=True, help="Comma-separated timeline windows in sec, e.g. '0-25,200-212'")
    p_prb.add_argument("--out", required=True, help="Output directory for contact sheets and probe_report.json")
    p_prb.add_argument("--scdet", action="store_true", help="Force full ffmpeg scdet even when sf-board.json sub-shots exist")
    p_prb.set_defaults(func=cmd_probe)

    p_app = sub.add_parser("apply", help="Apply card + subtitle plan.json directly to CapCut project and render WYSIWYG preview sheet.")
    p_app.add_argument("project", help="CapCut project name or path")
    p_app.add_argument("--plan", required=True, help="Path to plan.json")
    p_app.add_argument("--preview", help="Optional path for WYSIWYG preview contact sheet (.jpg)")
    p_app.add_argument("--no-preview", action="store_true", help="Skip rendering preview sheet for instant (<0.3s) application")
    p_app.add_argument("--no-snap-cuts", action="store_true", help="Disable automatic end-snapping to nearby shot cuts")
    p_app.add_argument("--dry-run", action="store_true", help="Compute and validate without writing to CapCut project")
    p_app.set_defaults(func=cmd_apply)

    p_clr = sub.add_parser("clear", help="Remove all cinematic card tracks while preserving subtitles.")
    p_clr.add_argument("project", help="CapCut project name or path")
    p_clr.set_defaults(func=cmd_clear)

    p_fnt = sub.add_parser("fonts", help="List available macOS PostScript fonts and on-demand Google Fonts.")
    p_fnt.set_defaults(
        func=lambda _a: (
            print(json.dumps(list_available_fonts(), indent=2)) or 0
        )
    )

    p_fet = sub.add_parser("fetch-font", help="Download, normalize (1.20*upm), and install any Google Font or macOS font into CapCut.")
    p_fet.add_argument("specs", nargs="+", help="Font specs, e.g. 'Cinzel-Bold' 'CormorantGaramond-SemiBoldItalic' 'PlayfairDisplay-Bold'")
    p_fet.set_defaults(
        func=lambda a: (
            print(
                json.dumps(
                    ensure_capcut_fonts_parallel(a.specs),
                    indent=2,
                )
            )
            or 0
        )
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
