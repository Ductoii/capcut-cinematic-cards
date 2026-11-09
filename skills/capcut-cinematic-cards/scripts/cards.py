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
from dataclasses import dataclass, replace
import difflib
from pathlib import Path
from typing import Any

from native_text import (
    DEFAULT_MAX_WORKERS,
    FilmCardStyle,
    TextLayerStyle,
    _uid,
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
    subdraft_id: str | None = None

    @property
    def duration_s(self) -> float:
        return self.timeline_dur_s

    @property
    def start_s(self) -> float:
        return self.timeline_start_s

    @property
    def end_s(self) -> float:
        return self.timeline_end_s

    @property
    def material_path(self) -> str:
        return self.path


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


extract_video_segments = load_video_timeline


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
    *,
    threshold: float | None = None,
    enable_scdet: bool = True,
) -> dict[str, list[float]]:
    """Return both edit-segment boundaries and internal ffmpeg scdet camera cuts inside [win_start, win_end] in parallel."""
    eff_thresh = float(threshold) if threshold is not None else float(scdet_threshold)
    seg_cuts: list[float] = []
    scdet_tasks: list[tuple[VideoSegment, float, float]] = []

    for seg in segments:
        if seg.timeline_end_s <= win_start or seg.timeline_start_s >= win_end:
            continue
        if win_start < seg.timeline_start_s < win_end:
            seg_cuts.append(round(seg.timeline_start_s, 2))
        if win_start < seg.timeline_end_s < win_end:
            seg_cuts.append(round(seg.timeline_end_s, 2))

        if not enable_scdet or not os.path.exists(seg.path):
            continue
        ov_start = max(win_start, seg.timeline_start_s)
        ov_end = min(win_end, seg.timeline_end_s)
        ov_dur = ov_end - ov_start
        if ov_dur <= 0.3:
            continue
        scdet_tasks.append((seg, ov_start, ov_dur))

    scdet_cache_dir = Path("/tmp/_capcut_scdet_cache")
    if scdet_tasks:
        scdet_cache_dir.mkdir(parents=True, exist_ok=True)

    def _run_scdet(item: tuple[VideoSegment, float, float]) -> list[float]:
        seg, ov_start, ov_dur = item
        src_offset = seg.source_start_s + (ov_start - seg.timeline_start_s) * seg.speed
        src_dur = ov_dur * seg.speed
        try:
            st = os.stat(seg.path)
            cache_sig = hashlib.md5(
                f"{os.path.abspath(seg.path)}:{st.st_mtime_ns}:{src_offset:.2f}:{src_dur:.2f}:{eff_thresh:.1f}".encode("utf-8")
            ).hexdigest()[:14]
        except Exception:
            cache_sig = ""
        cache_f = scdet_cache_dir / f"scdet_{cache_sig}.json" if cache_sig else None
        if cache_f and cache_f.exists():
            try:
                rel_cuts = json.loads(cache_f.read_text(encoding="utf-8"))
                return [
                    round(ov_start + float(rc) / max(seg.speed, 1e-6), 2)
                    for rc in rel_cuts
                    if win_start + 0.15 < round(ov_start + float(rc) / max(seg.speed, 1e-6), 2) < win_end - 0.15
                ]
            except Exception:
                pass

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
            f"scale=160:90,scdet=t={eff_thresh}:s=1,metadata=mode=print",
            "-an",
            "-f",
            "null",
            "-",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        rel_times = [float(m) for m in re.findall(r"lavfi\.scd\.time=([0-9.]+)", res.stderr)]
        if cache_f:
            try:
                cache_f.write_text(json.dumps(rel_times), encoding="utf-8")
            except Exception:
                pass
        found: list[float] = []
        for rt in rel_times:
            tl_cut = round(ov_start + rt / max(seg.speed, 1e-6), 2)
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
        "fast_cuts": sorted(set(seg_cuts)),
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
    Evaluate luminance, 90th-percentile brightness (glare/white signage/sky), and bright-pixel ratio
    across the 4 corner zones ('lower-left', 'lower-right', 'upper-left', 'upper-right') on `frame_path`.
    Returns zone stats (both in `zones` and as top-level keys) and `best_anchor`.
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
        zones: dict[str, dict[str, Any]] = {}
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
                "anchor": zname,
                "mean_luma": round(mean_l, 1),
                "p90_luma": round(p90_l, 1),
                "bright_ratio": round(bright_r, 3),
                "bright_glare": bool(p90_l >= 195.0 or bright_r >= 0.22),
                "cost": cost,
            }
        best_anchor = min(zones.keys(), key=lambda k: zones[k]["cost"])
        return {
            "best_anchor": best_anchor,
            "recommended_anchor": best_anchor,
            "zones": zones,
            **zones,
        }
    except Exception:
        return {"best_anchor": "lower-left", "recommended_anchor": "lower-left", "zones": {}}


score_negative_space = score_frame_negative_space


def resolve_glare_safe_anchor(
    req_anchor: str,
    ns_or_zones: dict[str, Any],
    *,
    is_scene_card: bool = False,
) -> tuple[str, str]:
    """
    Check if `req_anchor` ('lower-left', 'lower-right', 'upper-left', 'upper-right') sits over
    bright glare / sky / white signage, and automatically flip to a darker, cleaner corner.
    """
    zones = ns_or_zones.get("zones") if isinstance(ns_or_zones.get("zones"), dict) else ns_or_zones
    if not zones:
        return req_anchor, ""
    canon_map = {
        "lower-left": "lower-left",
        "chest-left": "lower-left",
        "side-low-left": "lower-left",
        "lower-right": "lower-right",
        "chest-right": "lower-right",
        "side-low-right": "lower-right",
        "upper-left": "upper-left",
        "top-left": "upper-left",
        "corner-left": "upper-left",
        "upper-right": "upper-right",
        "top-right": "upper-right",
        "corner-right": "upper-right",
    }
    canon = canon_map.get(req_anchor)
    if not canon or canon not in zones:
        return req_anchor, ""

    z_cur = zones[canon]
    cur_p90 = float(z_cur.get("p90_luma", 0.0))
    cur_br = float(z_cur.get("bright_ratio", 0.0))
    cur_mean = float(z_cur.get("mean_luma", 0.0))
    cur_cost = float(z_cur.get("cost", 0.0))

    has_glare = cur_p90 >= 195.0 or cur_br >= 0.22 or cur_mean >= 152.0
    if not has_glare:
        return req_anchor, ""

    if canon.startswith("upper-"):
        opp_upper = "upper-left" if canon == "upper-right" else "upper-right"
        cands = [opp_upper, "lower-left", "lower-right"]
    else:
        opp_lower = "lower-right" if canon == "lower-left" else "lower-left"
        cands = [opp_lower, "upper-left", "upper-right"]

    best_cand = canon
    best_cost = cur_cost
    for cand in cands:
        zc = zones.get(cand)
        if not zc:
            continue
        c_cost = float(zc.get("cost", 999.0))
        c_p90 = float(zc.get("p90_luma", 255.0))
        if c_cost < best_cost - 32.0 and (c_p90 < 195.0 or c_p90 < cur_p90 - 25.0):
            best_cand = cand
            best_cost = c_cost

    if best_cand != canon:
        return best_cand, f"{req_anchor}->{best_cand}(glare_p90={cur_p90:.0f})"
    return req_anchor, ""


def apply_daylight_contrast_guard(
    t_style: TextLayerStyle,
    d_style: TextLayerStyle,
    zone_metrics: dict[str, Any] | None,
) -> tuple[TextLayerStyle, TextLayerStyle, bool]:
    """
    When a card's resolved zone still sits over bright daylight (p90_luma >= 180 or mean_luma >= 135),
    automatically boost dark outline stroke_width and optical drop shadow so light serif text never
    washes out against bright skies, concrete, or sunlit walls.
    """
    if not zone_metrics:
        return t_style, d_style, False
    p90 = float(zone_metrics.get("p90_luma", 0.0))
    mean_l = float(zone_metrics.get("mean_luma", 0.0))
    bright_r = float(zone_metrics.get("bright_ratio", 0.0))
    if p90 < 112.0 and mean_l < 62.0 and bright_r < 0.02:
        return t_style, d_style, False

    min_sw = 0.032 if (p90 >= 165.0 or mean_l >= 120.0) else 0.027
    min_sh_a = 0.96 if (p90 >= 165.0 or mean_l >= 120.0) else 0.92
    min_sh_sm = 0.42
    min_sh_dist = 2.4

    new_t_sw = max(t_style.stroke_width, min_sw)
    new_d_sw = max(d_style.stroke_width, round(new_t_sw * 0.92, 4))
    new_sh_a = max(t_style.shadow_alpha, min_sh_a)
    new_sh_sm = max(t_style.shadow_smoothing, min_sh_sm)
    new_sh_dist = max(t_style.shadow_distance, min_sh_dist)

    t_boosted = replace(
        t_style,
        stroke_width=new_t_sw,
        stroke_alpha=max(t_style.stroke_alpha, 0.94),
        shadow_alpha=new_sh_a,
        shadow_smoothing=new_sh_sm,
        shadow_distance=new_sh_dist,
        check_flag=47,
    )
    d_boosted = replace(
        d_style,
        stroke_width=new_d_sw,
        stroke_alpha=max(d_style.stroke_alpha, 0.94),
        shadow_alpha=new_sh_a,
        shadow_smoothing=new_sh_sm,
        shadow_distance=new_sh_dist,
        check_flag=47,
    )
    return t_boosted, d_boosted, True


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


def _ensure_outro_black_segment(draft: dict[str, Any], outro_black_sec: float) -> float:
    """
    Idempotently append or update a solid 1920x1080 30fps black video segment (`V-OUTRO-BLACK.mp4`)
    at the end of the main video track when `outro_black_sec > 0`, returning the updated film duration in seconds.
    """
    dur_s = round(max(0.0, float(outro_black_sec)), 3)
    if dur_s <= 0.05:
        return 0.0
    dur_us = int(round(dur_s * 1_000_000))
    cache_dir = Path("/tmp/_capcut_frame_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    black_mp4 = cache_dir / f"V-OUTRO-BLACK-{int(round(dur_s * 10)):04d}.mp4"
    if not black_mp4.exists() or black_mp4.stat().st_size < 1000:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=black:s=1920x1080:r=30:d={dur_s:.2f}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(black_mp4),
            ],
            check=False,
        )

    mats = draft.setdefault("materials", {})
    vids = mats.setdefault("videos", [])
    outro_mat_id = "CC_OUTRO_BLACK_MAT"
    existing_mat = next((m for m in vids if m.get("id") == outro_mat_id or "V-OUTRO-BLACK" in str(m.get("path", ""))), None)
    if existing_mat is not None:
        outro_mat_id = existing_mat["id"]
        existing_mat["path"] = str(black_mp4)
        existing_mat["duration"] = dur_us
        existing_mat["material_name"] = "V-OUTRO-BLACK.mp4"
    else:
        vids.append(
            {
                "id": outro_mat_id,
                "type": "video",
                "path": str(black_mp4),
                "material_name": "V-OUTRO-BLACK.mp4",
                "duration": dur_us,
                "width": 1920,
                "height": 1080,
                "has_audio": False,
                "category_name": "local",
            }
        )

    v_tracks = [tr for tr in draft.get("tracks", []) if tr.get("type") == "video" and tr.get("segments")]
    if not v_tracks:
        return 0.0
    main_vtr = v_tracks[0]
    segs = main_vtr["segments"]
    # Remove any prior outro black segment so re-running apply is 100% idempotent
    segs[:] = [s for s in segs if s.get("material_id") != outro_mat_id and s.get("id") != "CC_OUTRO_BLACK_SEG"]
    base_end_us = max(
        (int(s.get("target_timerange", {}).get("start", 0)) + int(s.get("target_timerange", {}).get("duration", 0)) for s in segs),
        default=0,
    )
    segs.append(
        {
            "id": "CC_OUTRO_BLACK_SEG",
            "material_id": outro_mat_id,
            "target_timerange": {"start": base_end_us, "duration": dur_us},
            "source_timerange": {"start": 0, "duration": dur_us},
            "speed": 1.0,
            "volume": 0.0,
            "visible": True,
            "render_index": 0,
            "clip": {
                "alpha": 1.0,
                "flip": {"horizontal": False, "vertical": False},
                "rotation": 0.0,
                "scale": {"x": 1.0, "y": 1.0},
                "transform": {"x": 0.0, "y": 0.0},
            },
        }
    )
    total_us = base_end_us + dur_us
    draft["duration"] = max(int(draft.get("duration", 0)), total_us)
    return round(total_us / 1e6, 3)


def apply_plan_to_draft(
    draft: dict[str, Any],
    plan: dict[str, Any],
    *,
    snap_to_cuts: bool = True,
    screenplay_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Apply a card + subtitle plan directly to `draft` in memory.
    Automatically handles:
    - Font extraction for any macOS system font
    - Outer-edge alignment using true fontTools glyph width
    - Simultaneous overlapping cards (multi-track allocation: Track Pair 1, Track Pair 2, ...)
    - Camera-cut end snapping so cards don't bleed 0.3-1.0s into the next shot
    - Optional `outro_black_sec` (appends/updates a black outro segment for THE END card)
    - Optional in-place subtitle styling with check_flag=47 drop shadow and screenplay-grounded normalization
    """
    outro_black_s = float(plan.get("outro_black_sec") or plan.get("append_black_outro_sec") or 0.0)
    if outro_black_s > 0.05:
        _ensure_outro_black_segment(draft, outro_black_s)

    video_segs = load_video_timeline(draft)
    cut_times = extract_fast_timeline_cuts(video_segs)
    film_duration_s = (
        video_segs[-1].timeline_end_s
        if video_segs
        else round(float(draft.get("duration", 0)) / 1e6, 3)
    )
    sub_cues = extract_subtitles(draft)
    sp_ctx = build_screenplay_subtitle_context(video_segs, sub_cues, screenplay_path=screenplay_path)

    raw_style = dict(plan.get("style") or {})
    rec_style = sp_ctx.get("recommended_style") or {}
    # Anti-clone & anti-industrial guard:
    # 1. If `style` is empty, apply `rec_style`.
    # 2. If `style` copies the Horse test template (`PlayfairDisplay-Bold` + `CormorantGaramond*`) on a non-equestrian project,
    #    OR uses tiny ALL-CAPS `SpaceGrotesk-SemiBold` (`detail_uppercase: true`), apply the screenplay's `recommended_style`.
    is_horse_clone = (
        raw_style.get("title_font") == "PlayfairDisplay-Bold"
        and "CormorantGaramond" in str(raw_style.get("detail_font") or "")
        and rec_style.get("archetype") not in ("", "equestrian_heritage_estate")
    )
    is_industrial_sans = (
        "SpaceGrotesk" in str(raw_style.get("detail_font") or "")
        and bool(raw_style.get("detail_uppercase"))
    )
    if (not raw_style or is_horse_clone or is_industrial_sans) and rec_style:
        merged_style = dict(rec_style)
        if not (is_horse_clone or is_industrial_sans):
            merged_style.update(raw_style)
        raw_style = merged_style

    preset: FilmCardStyle = resolve_style(raw_style)
    raw_cards: list[dict[str, Any]] = list(plan.get("cards") or [])
    raw_cards.sort(
        key=lambda c: (
            float(c.get("start", c.get("start_s", c.get("start_sec", 0.0)))),
            str(c.get("kind", "")),
        )
    )

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
        start_s = float(card.get("start", card.get("start_s", card.get("start_sec", 0.0))))
        dur_hint = float(card.get("duration", card.get("duration_s", card.get("duration_sec", 4.0))))
        end_s = float(card.get("end", card.get("end_s", card.get("end_sec", round(start_s + dur_hint, 3)))))
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
            title_text = re.sub(r"\b(\d{2})S\b", r"\1s", title_text.upper())
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
        if need_mid_frames and kind_norm != "end" and (req_anchor in ("", "auto") or card_for_pos.get("auto_avoid_glare", True)):
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
                elif card_for_pos.get("auto_avoid_glare", True) and zones:
                    new_anc, reason = resolve_glare_safe_anchor(
                        req_anchor, ns, is_scene_card=(kind_norm == "time")
                    )
                    if new_anc != req_anchor:
                        card_for_pos["anchor"] = new_anc
                        flip_note = f"#{idx:02d} {title_text}: {reason}"
                final_anc = str(card_for_pos.get("anchor") or "").strip().lower()
                canon_final = {
                    "chest-left": "lower-left",
                    "side-low-left": "lower-left",
                    "chest-right": "lower-right",
                    "side-low-right": "lower-right",
                    "top-left": "upper-left",
                    "corner-left": "upper-left",
                    "top-right": "upper-right",
                    "corner-right": "upper-right",
                }.get(final_anc, final_anc)
                if card_for_pos.get("daylight_contrast_guard", True) and canon_final in zones:
                    t_style, d_style, boosted = apply_daylight_contrast_guard(
                        t_style, d_style, zones[canon_final]
                    )
                    if boosted:
                        card = dict(
                            card,
                            stroke_width=t_style.stroke_width,
                            shadow_alpha=t_style.shadow_alpha,
                            shadow_smoothing=t_style.shadow_smoothing,
                            shadow_distance=t_style.shadow_distance,
                        )
                        if not flip_note:
                            flip_note = f"#{idx:02d} {title_text}: daylight_contrast_guard(sw={t_style.stroke_width:.3f})"

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


_VI_DIACRITIC_RE = re.compile(r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]", re.I)


def _strip_vietnamese_clauses(text: str) -> str:
    """Remove parenthetical or trailing clauses that contain Vietnamese diacritics."""
    if not text:
        return ""
    cleaned = re.sub(
        r"\([^)]*\)",
        lambda m: "" if _VI_DIACRITIC_RE.search(m.group(0)) else m.group(0),
        text,
    )
    parts = [p.strip() for p in re.split(r"\s*[—–\-|]\s*", cleaned) if p.strip()]
    en_parts = [p for p in parts if not _VI_DIACRITIC_RE.search(p)]
    return " · ".join(en_parts) if en_parts else (parts[0] if parts else "")


def _to_editorial_title_case(s: str) -> str:
    small = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the", "to", "with"}
    words = s.split()
    out: list[str] = []
    for i, w in enumerate(words):
        w_clean = w.strip(".,:;()[]")
        if w_clean.isupper() and len(w_clean) >= 2:
            tc = w.capitalize()
            if 0 < i < len(words) - 1 and w_clean.lower() in small:
                tc = w.lower()
            out.append(tc)
        else:
            out.append(w)
    return " ".join(out)


def _translate_vi_time_of_day(par_text: str) -> str:
    """Translate Vietnamese parenthetical time/continuity annotations into English."""
    if not par_text:
        return ""
    s = par_text.strip()
    if not _VI_DIACRITIC_RE.search(s):
        return _to_editorial_title_case(s)
    sl = s.lower()
    days_map = [
        ("thứ hai", "Monday"),
        ("thứ ba", "Tuesday"),
        ("thứ tư", "Wednesday"),
        ("thứ năm", "Thursday"),
        ("thứ sáu", "Friday"),
        ("thứ bảy", "Saturday"),
        ("chủ nhật", "Sunday"),
    ]
    day_en = ""
    for vi_d, en_d in days_map:
        if vi_d in sl:
            day_en = en_d
            break

    clock_en = ""
    m_clk = re.search(r"(\d{1,2}:\d{2})\s*(sáng|chiều|tối)?", sl)
    if m_clk:
        ampm = "PM" if m_clk.group(2) in ("chiều", "tối") else "AM"
        clock_en = f"{m_clk.group(1)} {ampm}"
    else:
        m_hr = re.search(r"(\d{1,2})\s*giờ(?:\s*(sáng|trưa|chiều|tối|đêm))?", sl)
        if m_hr:
            hr = int(m_hr.group(1))
            period = m_hr.group(2) or ""
            ampm = "PM" if (period in ("trưa", "chiều", "tối", "đêm") or hr == 12) else "AM"
            clock_en = f"{hr}:00 {ampm}"

    tod_en = ""
    if "rạng sáng" in sl or "rạng đông" in sl or "bình minh" in sl:
        tod_en = "Dawn"
    elif "sáng sớm" in sl:
        tod_en = "Early Morning"
    elif "sáng" in sl and not clock_en:
        tod_en = "Morning"
    elif "trưa" in sl and not clock_en:
        tod_en = "Noon"
    elif "chiều" in sl and not clock_en:
        tod_en = "Afternoon"
    elif ("tối" in sl or "đêm" in sl) and not clock_en:
        tod_en = "Night"

    extras: list[str] = []
    if "sáu tuần sau" in sl or "6 tuần sau" in sl:
        extras.append("Six Weeks Later")
    elif "sáu tháng sau" in sl or "6 tháng sau" in sl:
        extras.append("Six Months Later")
    elif "ba tháng trước" in sl or "3 tháng trước" in sl:
        extras.append("Three Months Earlier")
    elif "mười năm trước" in sl or "10 năm trước" in sl:
        extras.append("Ten Years Earlier")
    elif "một năm sau" in sl or "1 năm sau" in sl:
        extras.append("One Year Later")
    elif "nhiều năm sau" in sl:
        extras.append("Years Later")
    elif "liền sau" in sl or "liền mạch" in sl or "ngay sau đó" in sl:
        extras.append("Moments Later")

    if "cắt song song" in sl:
        extras.append("Intercut")
    if "lễ động thổ" in sl:
        extras.append("Groundbreaking")
    if "hồi tưởng" in sl:
        extras.append("Flashback")

    pieces: list[str] = list(extras)
    if day_en and clock_en:
        pieces.append(f"{day_en}, {clock_en}")
    elif day_en and tod_en:
        pieces.append(f"{day_en} {tod_en}")
    elif day_en:
        pieces.append(day_en)
    elif clock_en:
        pieces.append(clock_en)
    elif tod_en:
        pieces.append(tod_en)
    return " · ".join(pieces)


def _translate_vi_location(loc_text: str, prompt: str = "") -> tuple[str, bool]:
    """Translate Vietnamese scene location headings into clean English titles + (is_exterior)."""
    raw = re.sub(r"^(?:SCENE|SC|S)\s*\d+(?:\s*→\s*S?\d+)?\s*[:.\-—–]?\s*", "", loc_text.strip(), flags=re.I)
    raw = re.sub(r"\([^)]*\)", "", raw).strip(" —–-·:")
    if not _VI_DIACRITIC_RE.search(raw):
        return _to_editorial_title_case(raw), False

    rl = raw.lower()
    pl = (prompt or "").lower()
    street_name = "Mulberry Street" if "mulberry" in (rl + " " + pl) else ""

    m_num = re.search(r"nhà\s+số\s+(\d+)", rl)
    house_prefix = f"{m_num.group(1)} {street_name}" if (m_num and street_name) else (f"House No. {m_num.group(1)}" if m_num else "")

    if "cửa sau" in rl and house_prefix:
        return f"{house_prefix} · Back Door", True
    if "sân trước" in rl and house_prefix:
        return f"{house_prefix} · Front Yard", True
    if "sân sau" in rl and house_prefix:
        return f"{house_prefix} · Backyard", True
    if ("bậc thềm trước" in rl or "hiên trước" in rl or "hiên nhà" in rl) and house_prefix:
        return f"{house_prefix} · Front Porch", True
    if "bếp" in rl and house_prefix and "căn hộ" not in rl:
        return f"{house_prefix} · Kitchen", False
    if "gác mái" in rl and house_prefix:
        return f"{house_prefix} · The Attic", False

    m_board = re.search(r"phòng\s+họp\s+([A-Za-z0-9\s&'-]+)", raw, re.I)
    if m_board:
        return f"{m_board.group(1).strip()} Boardroom", False
    if "phòng nhà đất" in rl or "bàn thanh tra" in rl:
        return "City Housing Inspection Office", False
    m_pent = re.search(r"penthouse\s+của\s+([A-Za-z]+)", raw, re.I)
    if m_pent:
        return f"{m_pent.group(1).strip()}'s Penthouse Study", False
    m_soup = re.search(r"bếp\s+ăn\s+từ\s+thiện\s+([A-Za-z0-9\s&'-]+)", raw, re.I)
    if m_soup:
        return f"{m_soup.group(1).strip()} Soup Kitchen", False
    m_apt_k = re.search(r"bếp\s+căn\s+hộ\s+của\s+([A-Za-z]+)", raw, re.I)
    if m_apt_k:
        return f"{m_apt_k.group(1).strip()}'s Apartment Kitchen", False
    m_cont = re.search(r"container\s+văn\s+phòng\s+([A-Za-z0-9\s&'-]+)", raw, re.I)
    if m_cont:
        return f"{m_cont.group(1).strip()} Site Office Trailer", False
    m_bus = re.search(r"trạm\s+xe\s+buýt.*phố\s+([A-Za-z0-9]+)", raw, re.I)
    if m_bus:
        return f"{m_bus.group(1).strip()} Street Bus Stop", True
    m_curb = re.search(r"lề\s+đường\s+phố\s+([A-Za-z0-9]+)", raw, re.I)
    if m_curb:
        return f"{m_curb.group(1).strip()} Street Curbside", True
    if "sân chuồng chợ đấu giá" in rl:
        return "Auction Stable Yard", True
    if "sân chuồng" in rl:
        return "Stable Yard", True
    if "phòng chờ cấp cứu" in rl:
        return "Emergency Waiting Room", False
    if "khu xe cứu thương" in rl:
        return "Ambulance Bay", True

    # Fallback: extract English location description from shot prompt (`IMGxx = the one location...: <desc>`)
    m_loc = re.search(r"(?:IMG|BG)\w*\s*=\s*the one location[^:]*:\s*([^,|]+)", prompt or "", re.I)
    if m_loc:
        en_loc = m_loc.group(1).strip()
        en_loc = re.sub(r"^(?:a|an|the)\s+(?:same\s+|sleek\s+|plain\s+|luxurious\s+|dark\s+|modest\s+|cramped\s+|warm\s+|freshly\s+|repaired\s+|old\s+|sagging\s+|pale-green\s+|wood-frame\s+|bare-wood\s+|muddy\s+)*", "", en_loc, flags=re.I)
        en_loc = re.sub(r"\s+(?:in the morning|in the afternoon|in the late morning|at night|at dawn|at gray dawn|at noon.*|on a saturday.*|six weeks later.*|lit only.*)$", "", en_loc, flags=re.I)
        if en_loc:
            is_ext_guess = any(k in en_loc.lower() for k in ("yard", "street", "porch", "bus stop", "curb", "outside", "park"))
            return _to_editorial_title_case(en_loc[:38].strip()), is_ext_guess

    cleaned = _strip_vietnamese_clauses(raw)
    return (_to_editorial_title_case(cleaned) if cleaned else ""), False


def _clean_scene_title_and_detail(sname: str, prompt: str = "", idx: int = 1) -> tuple[str, str]:
    raw = (sname or f"Scene {idx}").strip()
    raw = re.sub(r"^(?:SCENE|SC|S)\s*\d+(?:\s*→\s*S?\d+)?\s*[:.\-—–]?\s*", "", raw, flags=re.I)
    ie_match = re.search(r"\b(INT\./EXT\.|EXT\./INT\.|INT\.|EXT\.)\s*", raw, flags=re.I)
    is_ext = bool(ie_match and "EXT" in ie_match.group(1).upper())
    raw = re.sub(r"\b(?:INT\./EXT\.|EXT\./INT\.|INT\.|EXT\.)\s*", "", raw, flags=re.I)

    tod = ""
    for m_par in re.finditer(r"\(([^)]+)\)", raw):
        inner = m_par.group(1).strip()
        cand_tod = _translate_vi_time_of_day(inner)
        if cand_tod:
            tod = cand_tod
    raw_no_par = re.sub(r"\([^)]*\)", "", raw).strip()
    if _VI_DIACRITIC_RE.search(raw_no_par):
        title, ext_from_vi = _translate_vi_location(raw_no_par, prompt)
        is_ext = is_ext or ext_from_vi
        if not title:
            title = f"Scene {idx}"
    else:
        cleaned = _strip_vietnamese_clauses(raw_no_par)
        title = _to_editorial_title_case(cleaned) if cleaned else f"Scene {idx}"

    # Truncate overly long multi-part scene titles to 2 clauses max
    clauses = [c.strip() for c in title.split("·") if c.strip()]
    if len(clauses) > 2:
        title = f"{clauses[0]} · {clauses[1]}"
    if len(title) > 38 and "·" in title:
        title = title.split("·")[0].strip()

    if not tod:
        pl = (prompt or "").lower()
        if "night" in pl or "moonlight" in pl:
            tod = "Night"
        elif "morning" in pl or "dawn" in pl or "sunrise" in pl:
            tod = "Morning Light"
        elif "golden hour" in pl or "dusk" in pl or "sunset" in pl or "evening" in pl:
            tod = "Late Afternoon"
        else:
            tod = "Daylight"
    setting_kind = clauses[1] if len(clauses) > 1 and clauses[1] not in title else ("Exterior" if is_ext else "Interior")
    if "·" in tod:
        detail = tod
    else:
        detail = f"{tod} · {setting_kind}" if setting_kind and setting_kind.lower() != tod.lower() else tod
    return title, detail


_VI_CHAR_NAME_MAP: list[tuple[str, str]] = [
    ("tình nguyện viên nhà thờ", "Church Volunteer"),
    ("tình nguyện viên", "Volunteer"),
    ("thợ lái máy ủi", "Dozer Operator"),
    ("bảo vệ", "Security Guard"),
    ("y tá trưởng", "Head Nurse"),
    ("bác sĩ", "Doctor"),
]

_VI_CHAR_ROLE_MAP: list[tuple[str, str]] = [
    ("tỉ phú bất động sản", "Billionaire Real Estate CEO"),
    ("quản lý công trường", "Demolition Site Manager"),
    ("thanh tra nhà đất thành phố", "City Housing Inspector"),
    ("thanh tra nhà đất", "Housing Inspector"),
    ("tình nguyện viên bếp ăn từ thiện grace chapel", "Grace Chapel Soup Kitchen"),
    ("tình nguyện viên bếp ăn từ thiện", "Soup Kitchen Volunteer"),
    ("thợ lái máy ủi của haskins demolition", "Heavy Equipment · Haskins Demolition"),
    ("thợ lái máy ủi", "Heavy Equipment Operator"),
    ("mẹ terrell", "Terrell's Mother"),
    ("cha terrell", "Terrell's Father"),
    ("bác sĩ thú y", "Veterinarian"),
    ("bác sĩ cấp cứu", "Emergency Physician"),
    ("y tá trưởng ca", "Head ER Nurse"),
    ("trưởng ban giám khảo", "Head Judge"),
    ("bà đầu bếp nướng thịt", "Master Pitmaster"),
    ("chú rể", "The Groom"),
    ("cô dâu", "The Bride"),
    ("mẹ chú rể", "Mother of the Groom"),
    ("mẹ cô dâu", "Mother of the Bride"),
]


def _clean_char_title_and_detail(label: str, desc: str = "") -> tuple[str, str]:
    raw_lbl = (label or "").strip()
    # Strip leading CHAR1a / AL1 / ★ prefix BEFORE splitting on dashes
    raw_lbl = re.sub(r"^(?:★\s*)?(?:CHAR|AL)\d+[A-Za-z]*\s*[—–\-:.]?\s*", "", raw_lbl, flags=re.I).strip()

    age_str = ""
    m_age = re.search(
        r"\((\d{1,2}s?)\)|\b(\d{1,2})\s*(?:yo|years?\s*old|tuổi)\b|ngoài\s+(\d{2})",
        raw_lbl + " " + (desc or ""),
        re.I,
    )
    if m_age:
        age_str = m_age.group(1) or m_age.group(2) or (f"{m_age.group(3)}s" if m_age.group(3) else "")

    parts = [p.strip() for p in re.split(r"\s*[—–·]\s*", raw_lbl) if p.strip()]
    name_part = re.sub(r"\([^)]*\)", "", parts[0] if parts else raw_lbl).strip()
    name_part = re.sub(r"^(?:CHAR|AL)\d+[A-Za-z]*\s*[:.\-—–]?\s*", "", name_part, flags=re.I).strip()

    if _VI_DIACRITIC_RE.search(name_part):
        nl = name_part.lower()
        translated_name = ""
        for vi_k, en_v in _VI_CHAR_NAME_MAP:
            if vi_k in nl:
                translated_name = en_v
                break
        name_tc = translated_name or "Featured Character"
    else:
        name_tc = _to_editorial_title_case(name_part)

    title = f"{name_tc}, {age_str}" if (age_str and age_str not in name_tc) else name_tc

    role_candidates = [
        p for p in parts[1:]
        if not _VI_DIACRITIC_RE.search(p)
        and not re.match(r"^\d+\s*tuổi$", p, re.I)
        and p.lower() != name_part.lower()
    ]
    role = _to_editorial_title_case(" · ".join(role_candidates[:2])) if role_candidates else ""
    if not role and desc:
        first_line = desc.splitlines()[0]
        if not _VI_DIACRITIC_RE.search(first_line):
            role = _to_editorial_title_case(first_line[:42].strip(" ,.;—-"))
        else:
            blob_l = (raw_lbl + " " + first_line).lower()
            for vi_rk, en_rv in _VI_CHAR_ROLE_MAP:
                if vi_rk in blob_l:
                    role = en_rv
                    break
            if role and "freeman development" in blob_l and "Freeman" not in role:
                role = f"{role} · Freeman Development"
            elif role and "haskins demolition" in blob_l and "Haskins" not in role:
                role = f"{role} · Haskins Demolition"
    if not role:
        role = "Featured Character"
    return title, role


def _locate_sf_board_path(
    video_segs: list[VideoSegment],
    subs: list[dict[str, Any]] | None = None,
    screenplay_path: str | Path | None = None,
) -> Path | None:
    if screenplay_path:
        sp_cand = Path(os.path.expanduser(str(screenplay_path)))
        if sp_cand.is_dir() and (sp_cand / "sf-board.json").exists():
            return (sp_cand / "sf-board.json").resolve()
        if sp_cand.is_file() and sp_cand.exists():
            return sp_cand.resolve()

    for seg in video_segs:
        if not seg.path:
            continue
        p = Path(seg.path)
        for parent in (p.parent, p.parent.parent, p.parent.parent.parent):
            cand = parent / "sf-board.json"
            if cand.exists():
                return cand

    if subs:
        sub_blob = " ".join(c.get("text", "") for c in subs[:40]).lower()
        sub_words = _norm_words(sub_blob)
        if sub_words:
            search_roots: list[Path] = []
            for r_cand in (
                Path.cwd(),
                Path(__file__).resolve().parents[4],
                Path.home() / "Documents" / "SF Board",
                Path.home() / "Long",
                Path.home() / "Documents",
                Path.home() / "Desktop",
                Path.home() / "Downloads",
            ):
                if r_cand.exists() and r_cand not in search_roots:
                    search_roots.append(r_cand)
            cands: list[Path] = []
            for sr in search_roots:
                if (sr / "sf-board.json").exists():
                    cands.append(sr / "sf-board.json")
                cands.extend(sr.glob("*.project/sf-board.json"))
            if cands:
                min_hits = max(6, int(len(sub_words) * 0.35))

                def _score_cand(cand: Path) -> tuple[int, Path]:
                    try:
                        raw = cand.read_text(encoding="utf-8")[:60000].lower()
                        return sum(1 for w in sub_words if w in raw), cand
                    except Exception:
                        return 0, cand

                with ThreadPoolExecutor(max_workers=min(DEFAULT_MAX_WORKERS, len(cands))) as pool:
                    scored = list(pool.map(_score_cand, cands))
                best_score, best_cand = max(scored, key=lambda x: x[0])
                if best_score >= min_hits:
                    return best_cand
    return None


def _detect_cold_open_hook_end_s(video_segs: list[VideoSegment]) -> float:
    """
    Detect if the timeline starts with a Cold-Open Hook teaser (e.g. V-021..V-023 from S9 placed at 0.0-58.1s
    before chronological clip V-001 / V-S1 at 58.1s). Returns the timeline timestamp where V-001 begins.
    """
    if not video_segs:
        return 0.0
    for idx_s, seg in enumerate(video_segs[:25]):
        stem = Path(seg.clip_name).stem
        m_sc = re.match(r"^V-S(\d+)", stem, re.I)
        m_v1 = re.match(r"^(?:V-?0*1|0*1)$", stem, re.I)
        is_first_chron = (m_sc and int(m_sc.group(1)) <= 2) or bool(m_v1)
        if not is_first_chron:
            continue
        if idx_s == 0:
            return 0.0
        # Verify that preceding segments are later clips (clip num >= 3) or appear again later on the timeline
        later_stems = {Path(s.clip_name).stem for s in video_segs[idx_s + 1 :]}
        prev_are_hook = True
        for prev_seg in video_segs[:idx_s]:
            p_stem = Path(prev_seg.clip_name).stem
            m_pnum = re.search(r"(\d+)$", p_stem)
            if p_stem in later_stems or (m_pnum and int(m_pnum.group(1)) >= 3):
                continue
            prev_are_hook = False
            break
        if prev_are_hook:
            return round(seg.timeline_start_s, 3)
        return 0.0
    return 0.0


def _expand_dung_clip_ids(desc_text: str, clip_ranges: dict[str, tuple[float, float]]) -> list[str]:
    """
    Parse Vietnamese `Dùng: 001–005 · 018–032 · 045` clip usage lines inside `scenes[0].sfs[].desc`
    and return matching clip IDs present in `clip_ranges`.
    """
    if not desc_text or not clip_ranges:
        return []
    m_dung = re.search(r"(?:Dùng|Dung|Used\s*in)\s*:\s*([^\n(]+)", desc_text, re.I)
    if not m_dung:
        return []
    spec = m_dung.group(1)
    nums: list[int] = []
    for m_rng in re.finditer(r"(\d{1,4})\s*[–—\-]\s*(\d{1,4})", spec):
        a, b = int(m_rng.group(1)), int(m_rng.group(2))
        if 0 < a <= b and (b - a) <= 200:
            nums.extend(range(a, b + 1))
    spec_no_rng = re.sub(r"\d{1,4}\s*[–—\-]\s*\d{1,4}", " ", spec)
    for m_single in re.finditer(r"\b(\d{1,4})\b", spec_no_rng):
        nums.append(int(m_single.group(1)))

    matched: list[str] = []
    for n in nums:
        for cand in (f"V-{n:03d}", f"V-{n:02d}", f"V-{n}", f"{n:03d}", f"{n}"):
            if cand in clip_ranges and cand not in matched:
                matched.append(cand)
                break
    return matched


_TURN_STOP_WORDS: set[str] = {
    "the", "and", "you", "your", "for", "not", "are", "was", "this", "that",
    "with", "have", "from", "what", "who", "how", "yes", "yeah", "sir", "ma'am",
    "they", "them", "their", "his", "her", "him", "she", "all", "one", "out",
}


def _align_speaker_turns_with_subtitles(
    dialogue_text: str,
    clip_lo: float,
    clip_hi: float,
    subs: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """
    Split `sh['text']` into `(SPEAKER, line)` turns and align each turn monotonically to contiguous
    CapCut subtitle `[start_s, end_s]` intervals inside `[clip_lo, clip_hi]`.
    """
    if not dialogue_text:
        return []
    matches = list(re.finditer(r"(?:^|\n|\s)([A-Z][A-Z0-9_\s'/&-]{1,22}):\s*", dialogue_text))
    if not matches:
        return []
    raw_turns: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        spk = m.group(1).strip()
        if spk.upper() in ("REF", "SCENE", "SHOT", "VO", "SFX", "BGM", "NOTE", "NOTES"):
            continue
        start_pos = m.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(dialogue_text)
        line = " ".join(dialogue_text[start_pos:end_pos].split()).strip()
        if line:
            raw_turns.append((spk, line))
    if not raw_turns:
        return []

    local_subs = [
        c
        for c in (subs or [])
        if float(c.get("end_s", 0.0)) >= clip_lo - 0.6 and float(c.get("start_s", 0.0)) <= clip_hi + 0.6
    ]
    turns_out: list[dict[str, Any]] = []
    search_start_idx = 0

    for idx_t, (spk, line) in enumerate(raw_turns):
        lw = _norm_words(line)
        lw_content = lw - _TURN_STOP_WORDS
        matched_cues: list[dict[str, Any]] = []
        last_matched_idx = -1
        if local_subs and lw:
            for c_i in range(search_start_idx, len(local_subs)):
                cue = local_subs[c_i]
                cue_txt = str(cue.get("text") or "")
                cw = _norm_words(cue_txt)
                if not cw:
                    continue
                cw_content = cw - _TURN_STOP_WORDS
                sim = difflib.SequenceMatcher(None, line.lower(), cue_txt.lower()).ratio()
                if not matched_cues:
                    # Guard against jumping far ahead over remaining turns unless match is strong
                    ahead_gap = c_i - search_start_idx
                    rem_turns = len(raw_turns) - idx_t - 1
                    if rem_turns > 0 and ahead_gap > max(2, len(local_subs) - search_start_idx - rem_turns):
                        break
                    ov_c = len(lw_content & cw_content)
                    is_match = (
                        (lw_content and ov_c >= max(1, min(2, len(lw_content))))
                        or (not lw_content and len(lw & cw) >= len(lw))
                        or sim >= 0.48
                    )
                    if ahead_gap >= 3 and not (ov_c >= 2 or sim >= 0.56):
                        is_match = False
                    if is_match:
                        matched_cues.append(cue)
                        last_matched_idx = c_i
                        if sum(len(str(mc.get("text") or "")) for mc in matched_cues) >= len(line) * 0.72:
                            break
                else:
                    # Extension across multiple cues MUST be strictly contiguous in index and time
                    if (
                        c_i != last_matched_idx + 1
                        or float(cue.get("start_s", 0.0)) - float(matched_cues[-1].get("end_s", 0.0)) > 1.8
                    ):
                        break
                    ov_ext = len(lw_content & cw_content) if cw_content else len(lw & cw)
                    if ov_ext >= 1 or sim >= 0.42:
                        matched_cues.append(cue)
                        last_matched_idx = c_i
                        if sum(len(str(mc.get("text") or "")) for mc in matched_cues) >= len(line) * 0.72:
                            break
                    else:
                        break

        if matched_cues:
            search_start_idx = last_matched_idx + 1
            t_lo: float | None = round(float(matched_cues[0]["start_s"]), 2)
            t_hi: float | None = round(float(matched_cues[-1]["end_s"]), 2)
        else:
            t_lo = None
            t_hi = None
        turns_out.append(
            {
                "speaker": spk,
                "start_s": t_lo,
                "end_s": t_hi,
                "text": line[:140],
            }
        )

    # Pass 2: Monotonically interpolate any unmatched turns between surrounding matched bounds
    n_turns = len(turns_out)
    idx = 0
    while idx < n_turns:
        if turns_out[idx]["start_s"] is not None:
            idx += 1
            continue
        run_end = idx
        while run_end < n_turns and turns_out[run_end]["start_s"] is None:
            run_end += 1
        lo_bound = float(turns_out[idx - 1]["end_s"]) + 0.10 if idx > 0 else clip_lo
        hi_bound = float(turns_out[run_end]["start_s"]) - 0.10 if run_end < n_turns else clip_hi
        if hi_bound <= lo_bound + 0.4:
            hi_bound = max(lo_bound + 1.2 * (run_end - idx), min(clip_hi, lo_bound + 2.5))
        run_cnt = run_end - idx
        step = (hi_bound - lo_bound) / max(1, run_cnt)
        for k in range(run_cnt):
            s_t = round(lo_bound + k * step, 2)
            e_t = round(min(hi_bound, s_t + max(1.0, step - 0.12)), 2)
            if e_t <= s_t:
                e_t = round(s_t + 1.0, 2)
            turns_out[idx + k]["start_s"] = s_t
            turns_out[idx + k]["end_s"] = e_t
        idx = run_end

    return turns_out


def extract_screenplay_ground_truth(
    video_segs_or_sf: list[VideoSegment] | dict[str, Any],
    subs_or_vsegs: list[dict[str, Any]] | list[VideoSegment] | None = None,
    *,
    screenplay_path: str | Path | None = None,
    subtitles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Automatically locate `sf-board.json` from video segment paths (or accept `sf_data` dict directly),
    detect any Cold-Open Hook teaser (`hook_window_s`), and map story scenes (`S01..SNN`),
    character appearances (`CHAR1..CHARN`, `AL1..ALN`, `all_scene_appearances`), and speaker-aligned
    subtitle turns (`speaker_turns`) to exact edited CapCut timeline timestamps.
    """
    if isinstance(video_segs_or_sf, dict):
        sb = video_segs_or_sf
        video_segs = list(subs_or_vsegs or [])  # type: ignore[arg-type]
        subs = subtitles
        sf_board_path = Path(str(screenplay_path)) if screenplay_path else Path("/tmp/sf-board.json")
    else:
        video_segs = list(video_segs_or_sf or [])
        subs = subtitles if subtitles is not None else (subs_or_vsegs if isinstance(subs_or_vsegs, list) else None)  # type: ignore[assignment]
        sf_board_path = _locate_sf_board_path(video_segs, subs, screenplay_path=screenplay_path)
        if not sf_board_path:
            return {}
        try:
            with sf_board_path.open("r", encoding="utf-8") as fh:
                sb = json.load(fh)
        except Exception:
            return {}

    hook_end_s = _detect_cold_open_hook_end_s(video_segs)
    hook_window_s = [0.0, hook_end_s] if hook_end_s > 0.0 else None

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
                clean_goc = re.sub(
                    r"^Scene\s+\d+\s*:.*?widescreen\s+16:9\s+frame\.?\s*",
                    "",
                    mapped_goc.strip(),
                    flags=re.I | re.S,
                )
                clean_goc = " | ".join(line.strip() for line in clean_goc.splitlines() if line.strip())
                kept_slices_str = ", ".join(
                    f"TL {s.timeline_start_s:.2f}-{s.timeline_end_s:.2f}s (src {s.source_start_s:.1f}-{s.source_start_s + s.source_dur_s:.1f}s)"
                    for s in clip_segs.get(cid, [])
                )
                c_lo_hi = clip_ranges.get(cid, (0.0, 0.0))
                spk_turns = _align_speaker_turns_with_subtitles(
                    str(sh.get("text") or ""), c_lo_hi[0], c_lo_hi[1], subs
                )
                clip_info[cid] = {
                    "scene_id": sid,
                    "scene_name": sname,
                    "sf": sh.get("sf", ""),
                    "prompt": sh.get("prompt", ""),
                    "raw_goc": raw_goc,
                    "notes": " ".join((sh.get("notes") or "").split()),
                    "dialogue": " ".join((sh.get("text") or "").split()),
                    "shot_breakdown": clean_goc,
                    "kept_segments": kept_slices_str,
                    "speaker_turns": spk_turns,
                }
        if sc_clips:
            first_c = sc_clips[0]
            last_c = sc_clips[-1]
            s_start = clip_ranges[first_c][0]
            s_end = clip_ranges[last_c][1]
            fc_lo, fc_hi = clip_ranges[first_c]
            fc_info = clip_info.get(first_c, {})
            story_scenes.append(
                {
                    "scene_id": sid,
                    "scene_name": sname,
                    "start_s": s_start,
                    "end_s": s_end,
                    "first_clip": first_c,
                    "first_clip_window_s": f"{fc_lo:.2f}-{fc_hi:.2f}s",
                    "first_clip_kept_segments": fc_info.get("kept_segments", ""),
                    "first_clip_shots": fc_info.get("shot_breakdown", ""),
                    "first_clip_prompt": fc_info.get("prompt", ""),
                    "first_clip_speaker_turns": fc_info.get("speaker_turns", []),
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

        # 1. Start with explicit usedBy
        used: list[str] = [
            c for c in (ref.get("usedBy") or [])
            if c in clip_ranges and (clip_ranges[c][1] - clip_ranges[c][0]) >= 1.2
        ]
        # 2. Expand Vietnamese `Dùng: 001–005 · 018–032` in ref["desc"]
        for c_dung in _expand_dung_clip_ids(str(ref.get("desc") or ""), clip_ranges):
            if c_dung not in used and (clip_ranges[c_dung][1] - clip_ranges[c_dung][0]) >= 1.2:
                used.append(c_dung)
        # 3. Scan clip_info (sf_char_refs, notes, prompt, raw_goc) for exact ref ID (`CHAR1a`, `CHAR1b`, `REF_WES_1`)
        rid_pat = re.compile(rf"\b{re.escape(rid)}\b", re.I)
        base_pat = re.compile(rf"\b{re.escape(base_id)}[a-z]?\b", re.I)
        for cid, ci in clip_info.items():
            if cid in used or cid not in clip_ranges or (clip_ranges[cid][1] - clip_ranges[cid][0]) < 1.2:
                continue
            sf_refs = sf_char_refs.get(ci.get("sf", ""), [])
            blob = f"{ci.get('notes', '')}\n{ci.get('prompt', '')}\n{ci.get('raw_goc', '')}"
            if rid in sf_refs or rid_pat.search(blob):
                used.append(cid)
            elif m_named and any(r.startswith(f"REF_{base_id}_") for r in sf_refs):
                used.append(cid)
            elif not used and base_pat.search(blob):
                used.append(cid)

        lbl_str = str(ref.get("label") or "").strip()
        raw_desc = str(ref.get("desc") or "").strip()
        desc_first = raw_desc.splitlines()[0].strip() if raw_desc else ""
        full_label = f"{lbl_str} — {desc_first}".strip(" —") if (lbl_str or desc_first) else rid
        entry = char_groups.setdefault(
            base_id,
            {
                "id": base_id,
                "label": full_label,
                "raw_label": lbl_str,
                "desc": raw_desc,
                "clips": [],
            },
        )
        # Prefer the primary `a` variant's full description if available
        if rid.lower().endswith("a") and raw_desc:
            entry["label"] = full_label
            entry["raw_label"] = lbl_str
            entry["desc"] = raw_desc
        for c in used:
            if c not in entry["clips"]:
                entry["clips"].append(c)

    char_appearances: list[dict[str, Any]] = []
    for base_id, info in sorted(char_groups.items()):
        clips_sorted = sorted(info["clips"], key=lambda c: clip_ranges[c][0])
        if not clips_sorted:
            continue

        # Extract character name tokens (including aliases separated by `/` and translated Vietnamese roles) to filter speaker_turns
        raw_head = info["raw_label"].split("—")[-1] if info["raw_label"].upper().startswith(base_id) else info["raw_label"].split("—")[0]
        raw_head = raw_head.split("·")[0].split("(")[0].strip()
        en_title_guess, _ = _clean_char_title_and_detail(info["label"], info["desc"])
        name_tokens = {
            w.lower()
            for w in re.findall(r"[A-Za-z]{3,}", raw_head + " " + info["label"].split("—")[0] + " " + en_title_guess)
            if w.lower() not in {"char", "tuổi", "nam", "nữ", "featured", "character"}
        }

        first_clips = []
        char_speaker_turns: list[dict[str, Any]] = []
        for idx_c_clip, c in enumerate(clips_sorted[:2]):
            c_lo, c_hi = clip_ranges[c]
            ci = clip_info.get(c, {})
            first_clips.append(
                {
                    "clip": c,
                    "scene_id": ci.get("scene_id", ""),
                    "window_s": f"{c_lo:.2f}-{c_hi:.2f}s",
                    "kept_segments": ci.get("kept_segments", ""),
                    "notes": ci.get("notes", ""),
                    "dialogue": ci.get("dialogue", ""),
                    "shot_breakdown": ci.get("shot_breakdown", ""),
                    "prompt": ci.get("prompt", ""),
                    "speaker_turns": ci.get("speaker_turns", []),
                }
            )
            if idx_c_clip == 0:
                probe_windows.append(f"{int(c_lo)}-{int(min(c_hi, c_lo + 14.0)) + 1}")

        # Build `all_scene_appearances` across the entire film for this character
        all_scene_apps: list[dict[str, Any]] = []
        seen_scenes: dict[str, dict[str, Any]] = {}
        for c in clips_sorted:
            c_lo, c_hi = clip_ranges[c]
            ci = clip_info.get(c, {})
            sid = ci.get("scene_id") or "S?"
            for st_turn in ci.get("speaker_turns", []):
                spk_words = {w.lower() for w in re.findall(r"[A-Za-z]{3,}", st_turn["speaker"])}
                if (name_tokens & spk_words) and len(char_speaker_turns) < 8:
                    char_speaker_turns.append({**st_turn, "clip": c, "scene_id": sid})
            if sid not in seen_scenes:
                sc_entry = {
                    "scene_id": sid,
                    "scene_name": ci.get("scene_name", sid),
                    "first_clip_id": c,
                    "start_s": c_lo,
                    "end_s": c_hi,
                    "clip_count": 1,
                    "shot_breakdown": ci.get("shot_breakdown", ""),
                    "dialogue": ci.get("dialogue", "")[:160],
                }
                seen_scenes[sid] = sc_entry
                all_scene_apps.append(sc_entry)
            else:
                seen_scenes[sid]["end_s"] = max(seen_scenes[sid]["end_s"], c_hi)
                seen_scenes[sid]["clip_count"] += 1

        first_s = clip_ranges[clips_sorted[0]][0]
        char_appearances.append(
            {
                "character_id": base_id,
                "char_group": base_id,
                "label": info["label"],
                "desc": info["desc"],
                "first_appearance_s": first_s,
                "first_timeline_s": first_s,
                "speaker_turns": char_speaker_turns,
                "first_clips": first_clips,
                "all_scene_appearances": all_scene_apps,
            }
        )

    char_appearances.sort(key=lambda x: x["first_appearance_s"])
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
        "hook_window_s": hook_window_s,
        "scene_count": len(story_scenes),
        "character_count": len(char_appearances),
        "recommended_style": rec_style,
        "story_scenes": story_scenes,
        "character_appearances": char_appearances,
        "recommended_probe_windows": ",".join(f"{a}-{b}" for a, b in merged_wins),
        "_clip_info": clip_info,
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
            "philanthropic_real_estate_heritage",
            {"mulberry", "ebony rise", "bulldozer", "bulldoze", "childhood home", "vance holdings", "freeman development", "haskins demolition", "philanthrop", "community land trust", "historic preservation", "deed"},
            {
                "archetype": "philanthropic_real_estate_heritage",
                "title_font": "Cinzel-Bold",
                "detail_font": "CormorantGaramond-BoldItalic",
                "scene_title_font": "PlayfairDisplay-Bold",
                "scene_detail_font": "CormorantGaramond-BoldItalic",
                "end_title_font": "Cinzel-Bold",
                "end_detail_font": "CormorantGaramond-BoldItalic",
                "title_size": 6.8,
                "detail_size": 5.0,
                "scene_title_size": 6.6,
                "scene_detail_size": 5.0,
                "end_title_size": 8.2,
                "end_detail_size": 5.1,
                "detail_uppercase": False,
                "char_title_color": "#F0C76E",
                "char_detail_color": "#F7F1E5",
                "detail_accent_color": "#E8B954",
                "time_title_color": "#FBF6EC",
                "time_detail_color": "#EDE0C8",
                "scene_accent_color": "#F0C76E",
                "flanker_color": "#D4A856",
                "stroke_color": "#0A0C10",
                "stroke_width": 0.022,
                "shadow_color": "#05070A",
                "shadow_alpha": 0.92,
                "shadow_smoothing": 0.36,
                "shadow_distance": 2.4,
                "flankers": "—",
                "scene_flankers": "·",
                "stagger_sec": 0.10,
                "align": "center",
                "order": "title-first",
                "scene_order": "detail-first",
                "line_gap": 0.16,
            },
        ),
        (
            "coastal_lifeguard_rescue",
            {"lifeguard", "beach", "ocean", "surf", "shoreline", "pier", "bay", "tide", "coral", "marina", "boathouse", "jetty", "coast"},
            {
                "archetype": "coastal_lifeguard_rescue",
                "title_font": "Cinzel-Bold",
                "detail_font": "Lora-BoldItalic",
                "scene_title_font": "Optima-ExtraBlack",
                "scene_detail_font": "Lora-BoldItalic",
                "end_title_font": "Cinzel-Bold",
                "end_detail_font": "Lora-BoldItalic",
                "title_size": 6.8,
                "detail_size": 5.0,
                "scene_title_size": 6.6,
                "scene_detail_size": 5.0,
                "end_title_size": 8.2,
                "end_detail_size": 5.1,
                "detail_uppercase": False,
                "char_title_color": "#F4C86A",
                "char_detail_color": "#EBF7FA",
                "detail_accent_color": "#9BE2F2",
                "time_title_color": "#F8F5EC",
                "time_detail_color": "#E2F1F6",
                "scene_accent_color": "#F4C86A",
                "flanker_color": "#7ACBE0",
                "stroke_color": "#091017",
                "stroke_width": 0.016,
                "shadow_color": "#05070A",
                "shadow_alpha": 0.94,
                "shadow_smoothing": 0.42,
                "shadow_distance": 2.4,
                "flankers": "~",
                "scene_flankers": "•",
                "stagger_sec": 0.10,
                "align": "center",
                "order": "title-first",
                "scene_order": "detail-first",
                "line_gap": 0.16,
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
                "detail_size": 5.0,
                "scene_title_size": 6.6,
                "scene_detail_size": 5.0,
                "end_title_size": 8.0,
                "end_detail_size": 5.1,
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
                "line_gap": 0.16,
            },
        ),
        (
            "legal_corporate_dynasty",
            {"courtroom", "lawyer", "attorney", "judge", "deposition", "boardroom", "ceo", "executive", "penthouse", "billionaire", "trust", "inheritance", "hospital", "surgeon", "clinic"},
            {
                "archetype": "legal_corporate_dynasty",
                "title_font": "BodoniModa-Bold",
                "detail_font": "PlayfairDisplay-BoldItalic",
                "scene_title_font": "Didot-Bold",
                "scene_detail_font": "PlayfairDisplay-BoldItalic",
                "end_title_font": "Cinzel-Bold",
                "end_detail_font": "PlayfairDisplay-BoldItalic",
                "title_size": 6.8,
                "detail_size": 5.0,
                "scene_title_size": 6.6,
                "scene_detail_size": 5.0,
                "end_title_size": 8.2,
                "end_detail_size": 5.1,
                "detail_uppercase": False,
                "char_title_color": "#EED484",
                "char_detail_color": "#F2F5F8",
                "detail_accent_color": "#E5C07B",
                "time_title_color": "#FAFBFD",
                "time_detail_color": "#E2E8F0",
                "scene_accent_color": "#EED484",
                "flanker_color": "#C9A86A",
                "stroke_color": "#0B0E14",
                "stroke_width": 0.016,
                "shadow_color": "#05070A",
                "shadow_alpha": 0.94,
                "shadow_smoothing": 0.42,
                "shadow_distance": 2.4,
                "flankers": "—",
                "scene_flankers": "◇",
                "stagger_sec": 0.10,
                "align": "center",
                "order": "title-first",
                "scene_order": "detail-first",
                "line_gap": 0.16,
            },
        ),
        (
            "military_tactical_thriller",
            {"military", "colonel", "general", "sergeant", "veteran", "tactical", "hangar", "radar", "bunker", "precinct", "detective", "federal", "swat", "convoy"},
            {
                "archetype": "military_tactical_thriller",
                "title_font": "Copperplate-Bold",
                "detail_font": "Optima-Bold",
                "scene_title_font": "Cinzel-Bold",
                "scene_detail_font": "Optima-Bold",
                "end_title_font": "Cinzel-Bold",
                "end_detail_font": "Optima-Bold",
                "title_size": 6.8,
                "detail_size": 5.0,
                "scene_title_size": 6.6,
                "scene_detail_size": 5.0,
                "end_title_size": 8.2,
                "end_detail_size": 5.1,
                "detail_uppercase": False,
                "char_title_color": "#EBF0F5",
                "char_detail_color": "#D8E6F0",
                "detail_accent_color": "#F2C45A",
                "time_title_color": "#F5F8FA",
                "time_detail_color": "#D0DFE8",
                "scene_accent_color": "#F2C45A",
                "flanker_color": "#94B8CE",
                "stroke_color": "#080B0E",
                "stroke_width": 0.016,
                "shadow_color": "#040608",
                "shadow_alpha": 0.94,
                "shadow_smoothing": 0.42,
                "shadow_distance": 2.4,
                "flankers": "—",
                "scene_flankers": "•",
                "stagger_sec": 0.10,
                "align": "center",
                "order": "title-first",
                "scene_order": "detail-first",
                "line_gap": 0.16,
            },
        ),
        (
            "high_society_gala_drama",
            {"gala", "ballroom", "symphony", "violin", "piano", "opera", "couture", "auction", "gallery", "chandelier", "conservatory", "banquet"},
            {
                "archetype": "high_society_gala_drama",
                "title_font": "DMSerifDisplay-Regular",
                "detail_font": "PlayfairDisplay-BoldItalic",
                "scene_title_font": "BodoniModa-Bold",
                "scene_detail_font": "PlayfairDisplay-BoldItalic",
                "end_title_font": "Cinzel-Bold",
                "end_detail_font": "PlayfairDisplay-BoldItalic",
                "title_size": 6.8,
                "detail_size": 5.0,
                "scene_title_size": 6.6,
                "scene_detail_size": 5.0,
                "end_title_size": 8.2,
                "end_detail_size": 5.1,
                "detail_uppercase": False,
                "char_title_color": "#F5D38C",
                "char_detail_color": "#FAF5FF",
                "detail_accent_color": "#F7DF9E",
                "time_title_color": "#FDFBF7",
                "time_detail_color": "#F2E8FA",
                "scene_accent_color": "#F5D38C",
                "flanker_color": "#DFB86C",
                "stroke_color": "#0E0C14",
                "stroke_width": 0.015,
                "shadow_color": "#050408",
                "shadow_alpha": 0.94,
                "shadow_smoothing": 0.42,
                "shadow_distance": 2.4,
                "flankers": "« »",
                "scene_flankers": "◇",
                "stagger_sec": 0.10,
                "align": "center",
                "order": "title-first",
                "scene_order": "detail-first",
                "line_gap": 0.16,
            },
        ),
        (
            "rustic_heartland_americana",
            {"diner", "farmhouse", "tractor", "sheriff", "county", "porch", "bakery", "orchard", "harvest", "mill", "workshop", "mechanic", "truck", "cafe", "ribs", "smoker", "pitmaster", "barbecue"},
            {
                "archetype": "rustic_heartland_americana",
                "title_font": "Fraunces-Bold",
                "detail_font": "Lora-BoldItalic",
                "scene_title_font": "Bitter-Bold",
                "scene_detail_font": "Lora-BoldItalic",
                "end_title_font": "Fraunces-Bold",
                "end_detail_font": "Lora-BoldItalic",
                "title_size": 6.8,
                "detail_size": 5.0,
                "scene_title_size": 6.6,
                "scene_detail_size": 5.0,
                "end_title_size": 8.2,
                "end_detail_size": 5.1,
                "detail_uppercase": False,
                "char_title_color": "#F5B85C",
                "char_detail_color": "#FAF3E6",
                "detail_accent_color": "#FFD485",
                "time_title_color": "#FDF8EE",
                "time_detail_color": "#F3E6D0",
                "scene_accent_color": "#F5B85C",
                "flanker_color": "#E0944A",
                "stroke_color": "#100B07",
                "stroke_width": 0.016,
                "shadow_color": "#050403",
                "shadow_alpha": 0.94,
                "shadow_smoothing": 0.42,
                "shadow_distance": 2.4,
                "flankers": "—",
                "scene_flankers": "•",
                "stagger_sec": 0.10,
                "align": "center",
                "order": "title-first",
                "scene_order": "detail-first",
                "line_gap": 0.16,
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
        "title_font": "LibreBaskerville-Bold",
        "detail_font": "Lora-BoldItalic",
        "scene_title_font": "LibreBaskerville-Bold",
        "scene_detail_font": "Lora-BoldItalic",
        "end_title_font": "Cinzel-Bold",
        "end_detail_font": "Lora-BoldItalic",
        "title_size": 6.8,
        "detail_size": 5.0,
        "scene_title_size": 6.6,
        "scene_detail_size": 5.0,
        "end_title_size": 8.2,
        "end_detail_size": 5.1,
        "detail_uppercase": False,
        "char_title_color": "#F2CC76",
        "char_detail_color": "#F5F2EB",
        "detail_accent_color": "#F7DC94",
        "time_title_color": "#FAF8F2",
        "time_detail_color": "#EBE4D5",
        "scene_accent_color": "#F2CC76",
        "flanker_color": "#D4B062",
        "stroke_color": "#0C0F14",
        "stroke_width": 0.016,
        "shadow_color": "#05070A",
        "shadow_alpha": 0.94,
        "shadow_smoothing": 0.42,
        "shadow_distance": 2.4,
        "flankers": "—",
        "scene_flankers": "•",
        "stagger_sec": 0.10,
        "align": "center",
        "order": "title-first",
        "scene_order": "detail-first",
        "line_gap": 0.16,
    }


def build_screenplay_subtitle_context(
    video_segs: list[VideoSegment],
    subs: list[dict[str, Any]] | None = None,
    *,
    screenplay_path: str | Path | None = None,
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
    sf_board_path = _locate_sf_board_path(video_segs, subs, screenplay_path=screenplay_path)
    if not sf_board_path:
        return {}

    try:
        sb = json.loads(sf_board_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    hook_end_s = _detect_cold_open_hook_end_s(video_segs)
    clip_ranges: dict[str, list[tuple[float, float]]] = {}
    for seg in video_segs:
        if hook_end_s > 0.0 and seg.timeline_end_s <= hook_end_s + 0.05:
            continue
        cid = Path(seg.clip_name).stem
        clip_ranges.setdefault(cid, []).append((seg.timeline_start_s, seg.timeline_end_s))

    shot_windows: list[tuple[float, float, str]] = []
    char_proper_nouns: dict[str, str] = {}
    mid_sentence_proper_nouns: dict[str, str] = {}
    lowercase_seen: set[str] = set()
    valid_lower_vocab: set[str] = set()
    phrase_candidates: set[str] = set()

    hyphenated_compounds: set[tuple[str, str]] = set()

    def _harvest_dialogue_or_notes(txt: str) -> None:
        if not txt:
            return
        words_seq = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", txt)
        for idx_w, w in enumerate(words_seq):
            wl = w.lower()
            valid_lower_vocab.add(wl)
            if "'" in wl:
                valid_lower_vocab.add(wl.split("'")[0])
            if "-" in wl:
                for hp in wl.split("-"):
                    if hp:
                        valid_lower_vocab.add(hp)
                valid_lower_vocab.add(wl.replace("-", ""))
            if w.islower():
                lowercase_seen.add(wl)
                lowercase_seen.add(wl.rstrip("s"))
            if idx_w + 1 < len(words_seq):
                w_next_l = words_seq[idx_w + 1].lower()
                if len(wl) >= 3 and len(w_next_l) >= 3 and "'" not in wl and "'" not in w_next_l:
                    valid_lower_vocab.add(wl + w_next_l)
        # Harvest hyphenated compounds (e.g. Hand-welded, Mid-cook, hand-built, turn-ins, Hand-fired)
        for m_hyp in re.finditer(r"\b([A-Za-z]{2,})-([A-Za-z]{2,})\b", txt):
            hw1, hw2 = m_hyp.group(1), m_hyp.group(2)
            if not _VI_DIACRITIC_RE.search(hw1 + hw2):
                hyphenated_compounds.add((hw1.lower(), hw2.lower()))
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

    for hw1, hw2 in sorted(hyphenated_compounds):
        canonical_phrases.append(
            (re.compile(rf"\b{re.escape(hw1)}[\s-]+(?:to\s+)?{re.escape(hw2)}(?:\s+to(?=\s+[A-Za-z]))?\b", re.I), f"{hw1}-{hw2}")
        )
        if (hw1, hw2) == ("eighty", "five"):
            canonical_phrases.append(
                (re.compile(r"\b(?:user\s+)?85\b", re.I), "Eighty-five")
            )

    rec_style = recommend_style_for_screenplay(sb, str(sf_board_path.parent.name))
    return {
        "shot_windows": shot_windows,
        "proper_nouns": proper_nouns,
        "valid_lower_vocab": valid_lower_vocab,
        "canonical_phrases": canonical_phrases,
        "recommended_style": rec_style,
    }


def extract_subtitle_review_candidates(
    subs: list[dict[str, Any]],
    sp_ctx: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Run automatic screenplay-grounded normalization across all subtitle cues and return ONLY
    the cues that still contain any word missing from the overlapping local shot dialogue (`sh["text"]`)
    or global screenplay vocabulary, so the AI can audit 100% of remaining ASR anomalies in < 20 lines.
    """
    if not subs or not sp_ctx or not sp_ctx.get("valid_lower_vocab"):
        return []
    from native_text import _normalize_cue_with_screenplay, _apply_sentence_case_and_tokens

    valid_vocab = sp_ctx["valid_lower_vocab"]
    proper_nouns = sp_ctx.get("proper_nouns") or {}
    shot_windows = sp_ctx.get("shot_windows") or []
    review_cands: list[dict[str, Any]] = []

    for c in subs:
        st_s = float(c.get("start_s", 0.0))
        en_s = float(c.get("end_s", st_s + 2.0))
        norm = _normalize_cue_with_screenplay(str(c.get("text") or ""), st_s, en_s, sp_ctx)
        norm = _apply_sentence_case_and_tokens(norm)
        local_dlgs = [
            " ".join(d.split())
            for lo, hi, d in shot_windows
            if not (hi < st_s - 2.5 or lo > en_s + 2.5) and d
        ]
        local_vocab: set[str] = set()
        if local_dlgs:
            local_seq = re.findall(r"[a-z0-9'-]+", " ".join(local_dlgs).lower())
            for idx_lw, lw in enumerate(local_seq):
                local_vocab.add(lw)
                if "'" in lw:
                    local_vocab.add(lw.split("'")[0])
                if "-" in lw:
                    local_vocab.update(lw.split("-"))
                    local_vocab.add(lw.replace("-", ""))
                if idx_lw + 1 < len(local_seq):
                    local_vocab.add(lw + local_seq[idx_lw + 1])

        words = [m.group(0) for m in re.finditer(r"(?<![0-9'])[A-Za-z][A-Za-z'-]*", norm)]
        unknown: list[str] = []
        for w in words:
            wl = w.lower().rstrip(".")
            if len(wl) < 3 or wl in ("the", "and", "but", "for", "you", "not", "yes", "yeah", "well"):
                continue
            if wl in proper_nouns:
                continue
            in_global = wl in valid_vocab or wl.rstrip("s") in valid_vocab
            in_local = (not local_vocab) or (wl in local_vocab or wl.rstrip("s") in local_vocab)
            if not in_global or not in_local:
                unknown.append(w)

        if unknown:
            review_cands.append(
                {
                    "cue_index": c.get("index"),
                    "time_s": f"{st_s:.2f}-{en_s:.2f}s",
                    "subtitle_after_auto": norm,
                    "unmatched_words": unknown,
                    "screenplay_dialogue": " | ".join(local_dlgs[:2])[:220],
                }
            )
    return review_cands


def _detect_two_shot_char_side_anchor(
    base_id: str,
    prompt_text: str,
    turn_text: str = "",
) -> str | None:
    """
    When a character card lands on a multi-character shot (two-shot / wide / medium shot),
    inspect the clip's screenplay `prompt` for explicit left/right blocking of `base_id`
    (e.g. `CHAR6a ... on the left` -> `'lower-left'`, `CHAR7a ... on the right` -> `'lower-right'`)
    so the character card is anchored under the correct actor instead of whichever side is darker.
    Returns `None` if the shot containing `turn_text` is a solo `close-up on CHAR...`.
    """
    if not base_id or not prompt_text:
        return None
    distinct_chars = {m.group(1).upper() for m in re.finditer(r"\b((?:CHAR|AL)\d+)[a-z]?\b", prompt_text, re.I)}
    if len(distinct_chars) < 2:
        return None

    # Check if the specific shot containing `turn_text` is a solo close-up
    if turn_text:
        snippet = turn_text[:28].strip().lower()
        for clause in prompt_text.split("|"):
            cl_low = clause.lower()
            if snippet and snippet in cl_low:
                is_solo_cu = bool(
                    re.search(rf"\bclose-up\s+on\s+{re.escape(base_id)}[a-z]?\b", cl_low, re.I)
                    and not re.search(r"\bmedium\s+shot\s+of\b", cl_low, re.I)
                )
                if is_solo_cu:
                    return None
                break

    pat = re.compile(
        rf"\b{re.escape(base_id)}[a-z]?\b[^|.;:]*?\b(left|right)\b(?:\s+(?:end|side|of|at|in|from|behind|on))?",
        re.I,
    )
    left_hits = 0
    right_hits = 0
    for m in pat.finditer(prompt_text):
        side = m.group(1).lower()
        if side == "left":
            left_hits += 1
        elif side == "right":
            right_hits += 1
    if left_hits > right_hits:
        return "lower-left"
    if right_hits > left_hits:
        return "lower-right"
    return None


def generate_starter_plan(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Build a ready-to-refine `/tmp/plan_<project>.json` starter plan from `inspect` ground truth,
    locking scene cards to the opening sub-shot of each story scene and character cards to their
    first speaking turn or first sub-shot appearance (with automatic two-shot left/right side detection).
    """
    style = dict(payload.get("recommended_style") or {})
    story_scenes = payload.get("story_scenes") or []
    char_apps = payload.get("character_appearances") or []
    dur_s = float(payload.get("duration_sec") or 0.0)
    global_ctx = " ".join(
        [str(payload.get("screenplay_source") or "")]
        + [str(s.get("scene_name") or "") for s in story_scenes]
    )

    starter_cards: list[dict[str, Any]] = []
    for idx_sc, sc in enumerate(story_scenes, start=1):
        s_lo = float(sc.get("start_s", sc.get("start_sec", 0.0)))
        s_hi = float(sc.get("end_s", sc.get("end_sec", s_lo + 10.0)))
        if s_hi - s_lo < 2.2:
            continue
        c_start = round(s_lo + 0.35, 2)
        c_end = round(min(s_hi - 0.15, c_start + 3.65), 2)
        m_tl = re.search(r"TL\s+(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)s", str(sc.get("first_clip_shots") or ""))
        if m_tl:
            tl_a, tl_b = float(m_tl.group(1)), float(m_tl.group(2))
            if tl_b - tl_a >= 2.0:
                c_start = round(tl_a + 0.25, 2)
                c_end = round(min(tl_b - 0.12, c_start + 3.65), 2)
        s_title, s_detail = _clean_scene_title_and_detail(
            str(sc.get("scene_name") or sc.get("scene_id") or f"Scene {idx_sc}"),
            str(sc.get("first_clip_prompt") or sc.get("first_clip_shots") or "") + " " + global_ctx,
            idx_sc,
        )
        if (
            starter_cards
            and starter_cards[-1].get("kind") == "scene"
            and starter_cards[-1].get("title") == s_title
            and s_detail.startswith("Moments Later")
            and "Intercut" not in s_detail
        ):
            continue
        starter_cards.append(
            {
                "kind": "scene",
                "scene_id": sc.get("scene_id"),
                "start": c_start,
                "end": c_end,
                "title": s_title,
                "detail": s_detail,
                "anchor": "auto",
            }
        )

    for ch in char_apps:
        f_s = float(ch.get("first_appearance_s", ch.get("first_timeline_s", 0.0)))
        c_start = round(f_s + 0.45, 2)
        c_end = round(c_start + 3.60, 2)
        spk_turns = ch.get("speaker_turns") or []
        f_clips = ch.get("first_clips") or []
        first_clip_hi = f_s + 18.0
        if f_clips and "-" in str(f_clips[0].get("window_s") or ""):
            try:
                first_clip_hi = float(str(f_clips[0]["window_s"]).rstrip("s").split("-")[1])
            except Exception:
                pass
        early_turns = [t for t in spk_turns if float(t.get("start_s", 0.0)) <= first_clip_hi + 22.0]
        chosen_turn_end = c_end
        chosen_turn_text = ""
        if early_turns:
            substantial = [
                t for t in early_turns
                if (float(t.get("end_s", 0.0)) - float(t.get("start_s", 0.0))) >= 2.0
            ]
            t0 = substantial[0] if substantial else early_turns[0]
            c_start = round(max(f_s + 0.2, float(t0["start_s"])), 2)
            c_end = round(max(c_start + 2.8, min(float(t0["end_s"]) + 1.2, c_start + 3.85)), 2)
            chosen_turn_end = float(t0.get("end_s", c_end))
            chosen_turn_text = str(t0.get("text") or "")

        c_title, c_detail = _clean_char_title_and_detail(
            str(ch.get("label") or ch.get("character_id") or "Character"),
            str(ch.get("desc") or ""),
        )
        starter_cards.append(
            {
                "kind": "char",
                "character_id": ch.get("character_id"),
                "start": c_start,
                "end": c_end,
                "title": c_title,
                "detail": c_detail,
                "anchor": "auto",
                "_turns": early_turns,
                "_turn_end": chosen_turn_end,
                "_turn_text": chosen_turn_text,
                "_prompts": [str(fc.get("prompt") or "") for fc in f_clips if fc.get("prompt")],
            }
        )

    starter_cards.sort(key=lambda c: (float(c["start"]), 0 if c["kind"] == "scene" else 1))
    # Prevent accidental temporal collisions between scene cards and character cards in the starter plan
    idx_c = 1
    while idx_c < len(starter_cards):
        prev_c = starter_cards[idx_c - 1]
        curr_c = starter_cards[idx_c]
        p_st, p_en = float(prev_c["start"]), float(prev_c["end"])
        c_st, c_en = float(curr_c["start"]), float(curr_c["end"])
        if c_st < p_en + 0.25:
            if prev_c["kind"] == "scene" and curr_c["kind"] == "char" and (p_en - p_st) > 3.0:
                p_en = round(p_st + 3.0, 2)
                prev_c["end"] = p_en
            c_dur = max(2.8, min(3.5, c_en - c_st))
            shifted_st = round(p_en + 0.25, 2)
            cur_turn_end = float(curr_c.get("_turn_end", 0.0))
            later_turns = [
                t for t in (curr_c.get("_turns") or [])
                if float(t.get("start_s", 0.0)) >= p_en + 0.20
                and float(t.get("start_s", 0.0)) <= p_en + 16.0
            ]
            # If shifting start to `p_en + 0.25` still overlaps the current spoken turn by >= 1.6s, stay in this turn
            if cur_turn_end - shifted_st >= 1.6 or not later_turns:
                curr_c["start"] = shifted_st
                curr_c["end"] = round(shifted_st + c_dur, 2)
            else:
                lt = later_turns[0]
                curr_c["start"] = round(float(lt["start_s"]), 2)
                curr_c["end"] = round(max(curr_c["start"] + 2.8, min(float(lt["end_s"]) + 1.0, curr_c["start"] + 3.6)), 2)
                curr_c["_turn_end"] = float(lt.get("end_s", curr_c["end"]))
                curr_c["_turn_text"] = str(lt.get("text") or "")
                # Re-sort if jumping to `later_turns[0]` moved `curr_c` past a subsequent card
                if idx_c + 1 < len(starter_cards) and curr_c["start"] > float(starter_cards[idx_c + 1]["start"]):
                    starter_cards.sort(key=lambda c: (float(c["start"]), 0 if c["kind"] == "scene" else 1))
                    continue
        idx_c += 1

    for c_item in starter_cards:
        if c_item.get("kind") == "char":
            side_anc = _detect_two_shot_char_side_anchor(
                str(c_item.get("character_id") or ""),
                " ".join(c_item.get("_prompts") or []),
                str(c_item.get("_turn_text") or ""),
            )
            if side_anc:
                c_item["anchor"] = side_anc
                c_item["auto_avoid_glare"] = False
        c_item.pop("_turns", None)
        c_item.pop("_turn_end", None)
        c_item.pop("_turn_text", None)
        c_item.pop("_prompts", None)
    if dur_s > 6.0:
        starter_cards.append(
            {
                "kind": "end",
                "start": round(max(0.0, dur_s - 4.5), 2),
                "end": round(dur_s, 2),
                "title": "THE END",
                "detail": "",
                "anchor": "center",
                "hold_to_end": True,
            }
        )

    return {
        "style": style,
        "cards": starter_cards,
        "subtitles": {
            "style_in_place": True,
            "normalize_with_screenplay": True,
            "sentence_case": True,
        },
    }


def write_timeline_cheat_sheet(
    out_txt: Path,
    payload: dict[str, Any],
    video_segs: list[VideoSegment],
    subs: list[dict[str, Any]],
    clip_info: dict[str, dict[str, Any]],
) -> str:
    """
    Write a compact, human/LLM-readable 1-line-per-clip and 1-line-per-subtitle cheat sheet
    (`/tmp/inspect_<project>_timeline.txt`) so agents can read any time range with `read_file`
    in 0.1s and NEVER need to run `python3 -c` ad-hoc scripts.
    """
    lines: list[str] = []
    lines.append(f"# TIMELINE & SUBTITLE CHEAT SHEET — Project: {payload.get('project')} (Duration: {payload.get('duration_sec')}s)")
    if payload.get("hook_window_s"):
        hw = payload["hook_window_s"]
        lines.append(f"# COLD-OPEN HOOK TEASER: {hw[0]:.2f}s - {hw[1]:.2f}s (Do NOT place chronological Scene 1/2 cards inside Hook unless requested)")
    lines.append("")
    lines.append("## 1. STORY SCENES")
    for sc in payload.get("story_scenes") or []:
        lines.append(
            f"- {sc.get('scene_id', 'S?')}: {sc.get('start_s', 0.0):.2f}-{sc.get('end_s', 0.0):.2f}s | "
            f"first_clip={sc.get('first_clip', '')} ({sc.get('first_clip_window_s', '')}) | {sc.get('scene_name', '')}"
        )
    lines.append("")
    lines.append("## 2. CHARACTER APPEARANCES (ALL SCENES & SPEAKER TURNS)")
    for ch in payload.get("character_appearances") or []:
        apps_str = ", ".join(
            f"{a['scene_id']}({a['first_clip_id']}:{a['start_s']:.1f}-{a['end_s']:.1f}s)"
            for a in (ch.get("all_scene_appearances") or [])
        )
        turns_str = "; ".join(
            f"{t['speaker']}@{t['start_s']:.1f}-{t['end_s']:.1f}s"
            for t in (ch.get("speaker_turns") or [])[:5]
        )
        lines.append(
            f"- {ch.get('character_id')} | first={ch.get('first_appearance_s', 0.0):.2f}s | {ch.get('label')} | "
            f"scenes=[{apps_str}] | speaker_turns=[{turns_str}]"
        )
    lines.append("")
    lines.append("## 3. VIDEO SEGMENTS ON TIMELINE")
    for seg in video_segs:
        cid = Path(seg.clip_name).stem
        ci = clip_info.get(cid, {})
        sid = ci.get("scene_id", "")
        goc = (ci.get("shot_breakdown") or "")[:110]
        dlg = (ci.get("dialogue") or "")[:110]
        lines.append(
            f"[{seg.index:03d}] {seg.timeline_start_s:7.2f}-{seg.timeline_end_s:7.2f}s (src {seg.source_start_s:.1f}-{seg.source_start_s+seg.source_dur_s:.1f}s) | "
            f"{seg.clip_name} | {sid} | {goc} || {dlg}"
        )
    lines.append("")
    lines.append("## 4. SUBTITLE CUES")
    for c in subs:
        txt_one = " ".join(str(c.get("text") or "").split())
        lines.append(f"#{c.get('index', 0):03d} [{float(c.get('start_s', 0.0)):7.2f}-{float(c.get('end_s', 0.0)):7.2f}s] {txt_one}")

    out_txt.parent.mkdir(parents=True, exist_ok=True)
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out_txt)


def cmd_inspect(args: argparse.Namespace) -> int:
    project_dir = resolve_project_dir(args.project)
    draft = load_draft(project_dir)
    sp_arg = getattr(args, "screenplay", None)
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_vsegs = pool.submit(load_video_timeline, draft)
        f_subs = pool.submit(extract_subtitles, draft)
        f_cards = pool.submit(extract_existing_cards, draft)
        video_segs = f_vsegs.result()
        subs = f_subs.result()
        cards = f_cards.result()
        f_scenes = pool.submit(group_scene_boundaries, video_segs)
        f_gt = pool.submit(extract_screenplay_ground_truth, video_segs, subs, screenplay_path=sp_arg)
        f_sp_ctx = pool.submit(build_screenplay_subtitle_context, video_segs, subs, screenplay_path=sp_arg)
        scenes = f_scenes.result()
        gt = f_gt.result()
        sp_ctx = f_sp_ctx.result()

    clip_info = gt.pop("_clip_info", {}) if isinstance(gt, dict) else {}
    sub_status = (
        "ready"
        if subs
        else "none_in_draft_do_not_search_other_files (auto-captions not generated in CapCut yet)"
    )
    duration_sec = (
        video_segs[-1].timeline_end_s
        if video_segs
        else round(float(draft.get("duration", 0)) / 1e6, 3)
    )
    story_scenes = gt.get("story_scenes") or scenes
    char_appearances = gt.get("character_appearances", [])
    rec_style = gt.get("recommended_style", {})
    sub_review_cands = extract_subtitle_review_candidates(subs, sp_ctx) if subs else []

    out_path = (
        Path(os.path.expanduser(args.out))
        if getattr(args, "out", None)
        else Path(f"/tmp/inspect_{project_dir.name}.json")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cheat_sheet_path = out_path.parent / f"{out_path.stem}_timeline.txt"
    starter_plan_path = Path(f"/tmp/plan_{project_dir.name}.json")
    starter_plan_alias = Path(f"/tmp/starter_plan_{project_dir.name}.json")

    payload: dict[str, Any] = {
        "project": project_dir.name,
        "project_dir": str(project_dir),
        "duration_sec": duration_sec,
        "hook_window_s": gt.get("hook_window_s"),
        "video_segment_count": len(video_segs),
        "scene_count": len(story_scenes),
        "character_count": len(char_appearances),
        "recommended_style": rec_style,
        "recommended_probe_windows": gt.get("recommended_probe_windows", ""),
        "screenplay_source": gt.get("screenplay_source"),
        "starter_plan_path": str(starter_plan_path),
        "timeline_cheat_sheet": str(cheat_sheet_path),
        "existing_card_segment_count": len(cards),
        "subtitle_cue_count": len(subs),
        "subtitle_status": sub_status,
        "subtitle_review_candidate_count": len(sub_review_cands),
        "subtitle_review_candidates": sub_review_cands,
        "story_scenes": story_scenes,
        "character_appearances": char_appearances,
    }
    if getattr(args, "full", False):
        payload["video_segments"] = [
            {
                "index": s.index,
                "start_s": s.timeline_start_s,
                "end_s": s.timeline_end_s,
                "dur_s": s.timeline_dur_s,
                "src_start_s": s.source_start_s,
                "clip": s.clip_name,
            }
            for s in video_segs
        ]
        payload["existing_cards"] = cards
        payload["subtitles"] = subs

    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    starter_plan = generate_starter_plan(payload)
    starter_json = json.dumps(starter_plan, ensure_ascii=False, indent=2)
    starter_plan_path.write_text(starter_json, encoding="utf-8")
    starter_plan_alias.write_text(starter_json, encoding="utf-8")
    write_timeline_cheat_sheet(cheat_sheet_path, payload, video_segs, subs, clip_info)

    print(
        json.dumps(
            {
                "project": payload["project"],
                "duration_sec": payload["duration_sec"],
                "hook_window_s": payload.get("hook_window_s"),
                "video_segment_count": payload["video_segment_count"],
                "scene_count": payload["scene_count"],
                "character_count": payload["character_count"],
                "screenplay_source": payload.get("screenplay_source"),
                "recommended_style_archetype": (payload.get("recommended_style") or {}).get("archetype"),
                "recommended_probe_windows": payload.get("recommended_probe_windows", ""),
                "starter_plan_path": str(starter_plan_path),
                "timeline_cheat_sheet": str(cheat_sheet_path),
                "existing_card_segment_count": payload["existing_card_segment_count"],
                "subtitle_cue_count": payload["subtitle_cue_count"],
                "subtitle_review_candidate_count": len(sub_review_cands),
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

    # Phase 1: Compute window cuts across all windows in parallel.
    # Automatically enable cached ffmpeg scdet when `--scdet` is set OR when a window has a span > 4.5s
    # without internal `goc` sub-shot timestamps (e.g. arrow-separated `goc` descriptions).
    def _compute_window_cuts(item: tuple[int, tuple[float, float]]) -> dict[str, Any]:
        w_idx, (w_start, w_end) = item
        win_fast = [c for c in fast_cuts if w_start + 0.15 < c < w_end - 0.15]
        fast_bounds = [w_start] + win_fast + [w_end]
        max_unsplit_span = max((fast_bounds[i + 1] - fast_bounds[i] for i in range(len(fast_bounds) - 1)), default=0.0)
        need_scdet = bool(getattr(args, "scdet", False) or len(fast_cuts) <= 2 or max_unsplit_span > 4.5)
        if need_scdet:
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

    # Phase 3: Build ONLY 4x6 overview batch sheets (probe_batch_01..NN.jpg) and compact report
    report_windows: list[dict[str, Any]] = []
    all_frame_items: list[tuple[float, str, Path]] = []
    sheet_jobs: list[tuple[list[tuple[float, str, Path]], Path, int]] = []
    all_probed_shots: list[dict[str, Any]] = []

    for wm in win_metas:
        w_idx = wm["w_idx"]
        w_start, w_end = wm["w_start"], wm["w_end"]
        w_items = by_win.get(w_idx, [])
        sub_shots: list[dict[str, Any]] = []
        for a, b, mid_t, f_jpg, ok, cname, best_anc in w_items:
            if ok:
                all_frame_items.append((mid_t, f"{a:.1f}-{b:.1f}s ({best_anc})", f_jpg))
            shot_obj = {
                "start_s": a,
                "end_s": b,
                "dur_s": round(b - a, 2),
                "best_anchor": best_anc,
            }
            sub_shots.append(shot_obj)
            all_probed_shots.append(shot_obj)
        report_windows.append(
            {
                "window": f"{w_start:.1f}-{w_end:.1f}s",
                "sub_shots": [f"{s['start_s']:.1f}-{s['end_s']:.1f}s ({s['best_anchor']})" for s in sub_shots],
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

    # Automatically update /tmp/plan_<project>.json with probed best_anchor if it exists
    starter_plan_path = Path(f"/tmp/plan_{project_dir.name}.json")
    if starter_plan_path.exists() and all_probed_shots:
        try:
            sp_data = json.loads(starter_plan_path.read_text(encoding="utf-8"))
            for c in sp_data.get("cards", []):
                if c.get("kind") == "end":
                    continue
                cs = float(c.get("start", 0.0))
                ce = float(c.get("end", cs + 3.5))
                mid_c = (cs + ce) * 0.5
                for ps in all_probed_shots:
                    if ps["start_s"] - 0.3 <= mid_c <= ps["end_s"] + 0.3:
                        if str(c.get("anchor") or "auto") == "auto":
                            c["anchor"] = ps["best_anchor"]
                        break
            starter_plan_path.write_text(json.dumps(sp_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    report_path = out_dir / "probe_report.json"
    out_payload = {
        "project": project_dir.name,
        "report": str(report_path),
        "starter_plan_path": str(starter_plan_path) if starter_plan_path.exists() else None,
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
                "starter_plan_path": str(starter_plan_path) if starter_plan_path.exists() else None,
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
        screenplay_path=getattr(args, "screenplay", None),
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
    p_ins.add_argument("--screenplay", help="Optional explicit path to sf-board.json or .project directory")
    p_ins.add_argument("--full", action="store_true", help="Include raw video_segments, existing_cards, and subtitles arrays")
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
    p_app.add_argument("--screenplay", help="Optional explicit path to sf-board.json or .project directory")
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
