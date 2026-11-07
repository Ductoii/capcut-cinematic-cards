#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from native_text import (
    FilmCardStyle,
    build_card_pair,
    ensure_capcut_font,
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
    """Write draft_info.json, sync to draft_content.json and Timelines/*/draft_info.json, and clear stale patches."""
    main_path = project_dir / "draft_info.json"
    tmp_path = project_dir / "draft_info.json.tmp"
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(draft, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp_path, main_path)

    synced = [str(main_path)]
    dc_path = project_dir / "draft_content.json"
    if dc_path.exists():
        shutil.copy2(main_path, dc_path)
        synced.append(str(dc_path))

    for tl_di in sorted(glob.glob(str(project_dir / "Timelines" / "*" / "draft_info.json"))):
        shutil.copy2(main_path, tl_di)
        synced.append(tl_di)

    for patch_file in sorted(
        glob.glob(str(project_dir / "Timelines" / "*" / "attachment" / "patch" / "patch.json"))
    ):
        try:
            with open(patch_file, "w", encoding="utf-8") as pfh:
                pfh.write('{"patch_list":[]}')
        except Exception:
            pass
    for mini_file in sorted(
        glob.glob(str(project_dir / "Timelines" / "*" / "attachment" / "patch" / "mini_draft.json"))
    ):
        try:
            os.remove(mini_file)
        except Exception:
            pass
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
            segs = [s for s in tr.get("segments", []) if s.get("material_id") in sv]
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
                items.append((eff_t_start, eff_t_dur, eff_s_start, eff_s_dur, eff_spd, sv[s["material_id"]]))
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
            if mid in top_videos:
                raw_items.append((t_start, t_dur, s_start, s_dur, spd, top_videos[mid]))
            elif mid in draft_mats:
                raw_items.extend(_unwrap_sub(draft_mats[mid], t_start, s_start, s_dur, spd))
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
    """Return both edit-segment boundaries and internal ffmpeg scdet camera cuts inside [win_start, win_end]."""
    seg_cuts: list[float] = []
    scdet_cuts: list[float] = []

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
        for m in re.findall(r"lavfi\.scd\.time=([0-9.]+)", res.stderr):
            tl_cut = round(ov_start + float(m) / max(seg.speed, 1e-6), 2)
            if win_start + 0.15 < tl_cut < win_end - 0.15:
                scdet_cuts.append(tl_cut)

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
    """Extract a single frame at timeline second `t_sec`, optionally annotated with composition zones."""
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
    return out_jpg.exists(), target_seg.clip_name


def build_contact_sheet(
    frame_items: list[tuple[float, str, Path]],
    out_sheet: Path,
    cols: int = 3,
) -> bool:
    """Assemble extracted frame JPEGs into a labeled contact sheet using PIL."""
    if not frame_items:
        return False
    try:
        from PIL import Image, ImageDraw, ImageFont

        cell_w, cell_h = 640, 360
        rows = (len(frame_items) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (12, 14, 18))
        draw = ImageDraw.Draw(sheet)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 18)
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
            draw.rectangle([x0 + 6, y0 + 6, x0 + 6 + len(label) * 11, y0 + 32], fill=(0, 0, 0))
            draw.text((x0 + 8, y0 + 9), label, fill=(255, 230, 110), font=font)

        out_sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out_sheet, quality=88)
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
    - Optional in-place subtitle styling with check_flag=47 drop shadow
    """
    preset: StylePreset = resolve_style(plan.get("style"))
    ensure_capcut_font(preset.character_title.font_postscript)
    ensure_capcut_font(preset.character_detail.font_postscript)
    ensure_capcut_font(preset.time_title.font_postscript)
    ensure_capcut_font(preset.time_detail.font_postscript)

    video_segs = load_video_timeline(draft)
    cut_times = sorted(
        {seg.timeline_start_s for seg in video_segs} | {seg.timeline_end_s for seg in video_segs}
    )
    film_duration_s = (
        video_segs[-1].timeline_end_s
        if video_segs
        else round(float(draft.get("duration", 0)) / 1e6, 3)
    )

    sub_cues = extract_subtitles(draft)

    # Strip old card tracks first
    strip_card_tracks(draft)

    raw_cards: list[dict[str, Any]] = list(plan.get("cards") or [])
    raw_cards.sort(key=lambda c: (float(c.get("start", 0.0)), str(c.get("kind", ""))))

    # Track pairs: each pair holds [title_segments, detail_segments, last_end_us]
    track_pairs: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = []
    pair_end_us: list[int] = []

    mats = draft.setdefault("materials", {})
    texts_list = mats.setdefault("texts", [])
    anims_list = mats.setdefault("material_animations", [])

    applied_cards: list[dict[str, Any]] = []

    for idx, card in enumerate(raw_cards, start=1):
        kind = str(card.get("kind") or card.get("type") or "char").lower()
        if kind in ("character", "char"):
            kind_norm = "char"
        elif kind in ("end", "ending"):
            kind_norm = "end"
        else:
            kind_norm = "time"

        t_style, d_style, card_align, card_order = resolve_card_styles(card, preset)

        start_s = float(card.get("start", card.get("start_s", 0.0)))
        end_s = float(card.get("end", card.get("end_s", start_s + 4.0)))
        if kind_norm == "end" and card.get("hold_to_end", False) and film_duration_s > start_s:
            end_s = film_duration_s

        # Full Sub-Shot Boundary Locking:
        # Detect all camera cuts (segment boundaries + internal scdet cuts) around [start_s - 0.6s, end_s + 0.6s]
        # and lock both start_s (>= shot_lo + 0.15s) and end_s (<= shot_hi - 0.08s) inside the dominant continuous shot.
        if (
            snap_to_cuts
            and kind_norm != "end"
            and card.get("snap_to_cut", True)
            and video_segs
        ):
            probe_lo = max(0.0, round(start_s - 0.6, 2))
            probe_hi = min(film_duration_s, round(end_s + 0.6, 2))
            if probe_hi > probe_lo:
                cuts = detect_window_cuts(video_segs, probe_lo, probe_hi)["all_cuts"]
                bounds = [probe_lo] + [c for c in cuts if probe_lo + 0.05 < c < probe_hi - 0.05] + [probe_hi]
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
        card_flankers = str(
            card.get("flankers")
            if card.get("flankers") is not None
            else (preset.flankers if kind_norm in ("char", "end") else preset.scene_flankers)
        ).strip()
        detail_text = format_detail_with_flankers(
            raw_detail_text, card_flankers, font_postscript=d_style.font_postscript
        )
        card_for_pos = dict(card, title=title_text, detail=detail_text)

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

        texts_list.append(pair_res.title_material)
        anims_list.append(pair_res.title_animation)
        if detail_text:
            texts_list.append(pair_res.detail_material)
            anims_list.append(pair_res.detail_animation)

        # Allocate to the first non-overlapping track pair, or create a new track pair for simultaneous cards
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
                "index": idx,
                "kind": kind_norm,
                "track_pair": allocated_pair_idx + 1,
                "start_s": round(start_s, 2),
                "end_s": round(start_s + dur_s, 2),
                "x": x_title,
                "x_detail": x_detail,
                "y_main": y_main,
                "y_detail": y_detail,
                "scale": scale,
                "align": card_align,
                "order": card_order,
                "title": title_text,
                "detail": detail_text,
                "_raw_card": card,
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
            sub_report = style_subtitle_track_in_place(draft, sub_spec)

    return {
        "title_font": preset.character_title.font_postscript,
        "detail_font": preset.character_detail.font_postscript,
        "title_size": preset.character_title.font_size,
        "detail_size": preset.character_detail.font_size,
        "cards_applied": len(applied_cards),
        "track_pairs_created": len(track_pairs),
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

    # Fallback when video is a flat exported MP4 without V-NNN filenames: match subtitle lines against workspace sf-board.json
    if not sf_board_path and subs:
        sub_blob = " ".join(c.get("text", "") for c in subs[:40]).lower()
        sub_words = _norm_words(sub_blob)
        best_score = 0
        ws_root = Path("/Users/daho100/Documents/SF Board")
        if ws_root.exists() and sub_words:
            for cand in ws_root.glob("*.project/sf-board.json"):
                try:
                    raw = cand.read_text(encoding="utf-8")[:60000].lower()
                    score = sum(1 for w in sub_words if w in raw)
                    if score > best_score and score >= max(6, int(len(sub_words) * 0.35)):
                        best_score = score
                        sf_board_path = cand
                except Exception:
                    continue

    if not sf_board_path:
        return {}

    try:
        with sf_board_path.open("r", encoding="utf-8") as fh:
            sb = json.load(fh)
    except Exception:
        return {}

    clip_segs: dict[str, list[VideoSegment]] = {}
    clip_ranges: dict[str, tuple[float, float]] = {}
    for seg in video_segs:
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
    story_scenes: list[dict[str, Any]] = []
    probe_windows: list[str] = []

    for sc in sb.get("scenes", [])[1:]:
        sid = sc.get("id", "")
        sname = sc.get("name", sid)
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
        m = re.match(r"^((?:CHAR|AL)\d+)", rid)
        if not m:
            continue
        base_id = m.group(1)
        # Only include clips that survive on the timeline with >= 1.2s duration
        used = [
            c for c in (ref.get("usedBy") or [])
            if c in clip_ranges and (clip_ranges[c][1] - clip_ranges[c][0]) >= 1.2
        ]
        entry = char_groups.setdefault(
            base_id,
            {
                "id": base_id,
                "label": ref.get("label") or ref.get("desc") or rid,
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
        for c in clips_sorted[:3]:
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
            probe_windows.append(f"{int(c_lo)}-{int(c_hi) + 1}")
        char_appearances.append(
            {
                "character_id": base_id,
                "label": info["label"],
                "first_appearance_s": clip_ranges[clips_sorted[0]][0],
                "first_clips": first_clips,
            }
        )

    char_appearances.sort(key=lambda x: x["first_appearance_s"])
    return {
        "screenplay_source": str(sf_board_path),
        "story_scenes": story_scenes,
        "character_appearances": char_appearances,
        "recommended_probe_windows": ",".join(dict.fromkeys(probe_windows)),
    }


def cmd_inspect(args: argparse.Namespace) -> int:
    project_dir = resolve_project_dir(args.project)
    draft = load_draft(project_dir)
    video_segs = load_video_timeline(draft)
    scenes = group_scene_boundaries(video_segs)
    subs = extract_subtitles(draft)
    cards = extract_existing_cards(draft)
    gt = extract_screenplay_ground_truth(video_segs, subs)

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
        "subtitles": subs,
    }

    if args.out:
        out_path = Path(os.path.expanduser(args.out))
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
                    "recommended_probe_windows": payload.get("recommended_probe_windows", ""),
                    "existing_card_segment_count": payload["existing_card_segment_count"],
                    "subtitle_cue_count": payload["subtitle_cue_count"],
                    "saved_to": str(out_path),
                },
                indent=2,
            )
        )
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    project_dir = resolve_project_dir(args.project)
    draft = load_draft(project_dir)
    video_segs = load_video_timeline(draft)
    if not video_segs:
        raise RuntimeError(f"No video segments found in {project_dir}")

    out_dir = Path(os.path.expanduser(args.out))
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / "frames"
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

    report_windows: list[dict[str, Any]] = []
    for w_idx, (w_start, w_end) in enumerate(windows, start=1):
        cuts_info = detect_window_cuts(video_segs, w_start, w_end)
        all_cuts = cuts_info["all_cuts"]
        # Sample timestamps: start + every sub-shot midpoint + regular step
        boundaries = [w_start] + [c for c in all_cuts if w_start < c < w_end] + [w_end]
        sample_times: list[float] = []
        for i in range(len(boundaries) - 1):
            a, b = boundaries[i], boundaries[i + 1]
            if b - a < 0.35:
                continue
            sample_times.append(round(a + 0.35, 2))
            if b - a >= 2.5:
                sample_times.append(round((a + b) / 2.0, 2))
            if b - a >= 4.5:
                sample_times.append(round(b - 0.5, 2))
        sample_times = sorted(set(sample_times))

        frame_items: list[tuple[float, str, Path]] = []
        for t_sec in sample_times:
            f_jpg = frames_dir / f"w{w_idx:02d}_{int(round(t_sec*100)):06d}.jpg"
            ok, cname = extract_frame_at_timeline_sec(video_segs, t_sec, f_jpg)
            if ok:
                frame_items.append((t_sec, cname, f_jpg))

        sheet_path = out_dir / f"sheet_{w_idx:02d}_{int(w_start):04d}_{int(w_end):04d}.jpg"
        build_contact_sheet(frame_items, sheet_path)

        # Build clean sub-shots list bounded by cuts
        sub_shots = []
        for i in range(len(boundaries) - 1):
            a, b = round(boundaries[i], 2), round(boundaries[i + 1], 2)
            if b - a >= 0.3:
                sub_shots.append({"start_s": a, "end_s": b, "dur_s": round(b - a, 2)})

        report_windows.append(
            {
                "window": f"{w_start:.2f}-{w_end:.2f}s",
                "segment_cuts": cuts_info["segment_cuts"],
                "scdet_cuts": cuts_info["scdet_cuts"],
                "all_cuts": all_cuts,
                "sub_shots": sub_shots,
                "contact_sheet": str(sheet_path) if sheet_path.exists() else None,
            }
        )

    report_path = out_dir / "probe_report.json"
    with report_path.open("w", encoding="utf-8") as fh:
        json.dump({"project": project_dir.name, "windows": report_windows}, fh, indent=2)
    print(json.dumps({"project": project_dir.name, "report": str(report_path), "windows": report_windows}, indent=2))
    return 0


def render_preview_sheet(
    draft: dict[str, Any],
    applied_cards: list[dict[str, Any]],
    preset: FilmCardStyle,
    out_sheet_path: Path,
) -> str | None:
    video_segs = load_video_timeline(draft)
    if not video_segs or not applied_cards:
        return None
    tmp_dir = out_sheet_path.parent / f"_preview_frames_{out_sheet_path.stem}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    rendered_items: list[Path] = []
    for c in applied_cards:
        mid_t = round((float(c["start_s"]) + float(c["end_s"])) * 0.5, 2)
        raw_jpg = tmp_dir / f"raw_{c['index']:02d}.jpg"
        comp_jpg = tmp_dir / f"comp_{c['index']:02d}.jpg"
        ok, cname = extract_frame_at_timeline_sec(
            video_segs, mid_t, raw_jpg, width=960, height=540, include_guides=False
        )
        if not ok:
            continue
        raw_c = c.pop("_raw_card", None) or c
        t_st, d_st, _, _ = resolve_card_styles(raw_c, preset)
        lbl = f"#{c['index']:02d} {c['start_s']:.1f}-{c['end_s']:.1f}s | x={c['x']:+.2f} y={c['y_main']:+.2f} sc={c['scale']:.2f}"
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
            rendered_items.append(comp_jpg)

    if not rendered_items:
        return None

    from PIL import Image
    cols = 3
    rows = (len(rendered_items) + cols - 1) // cols
    tw, th = 640, 360
    sheet = Image.new("RGB", (cols * tw, rows * th), (12, 14, 18))
    for i, p in enumerate(rendered_items):
        try:
            im = Image.open(p).resize((tw, th))
            sheet.paste(im, ((i % cols) * tw, (i // cols) * th))
        except Exception:
            pass
    out_sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_sheet_path, quality=88)
    return str(out_sheet_path)


def cmd_apply(args: argparse.Namespace) -> int:
    project_dir = resolve_project_dir(args.project)
    plan_path = Path(os.path.expanduser(args.plan))
    with plan_path.open("r", encoding="utf-8") as fh:
        plan = json.load(fh)

    draft = load_draft(project_dir)
    summary = apply_plan_to_draft(
        draft,
        plan,
        snap_to_cuts=not bool(args.no_snap_cuts),
    )
    preset = summary.pop("_preset")

    if not args.dry_run:
        synced = save_and_sync_draft(project_dir, draft)
        summary["synced_files"] = synced
    else:
        summary["dry_run"] = True

    preview_target = (
        Path(os.path.expanduser(args.preview))
        if getattr(args, "preview", None)
        else plan_path.parent / f"preview_{plan_path.stem}.jpg"
    )
    preview_sheet = render_preview_sheet(draft, summary["cards"], preset, preview_target)
    if preview_sheet:
        summary["preview_sheet"] = preview_sheet

    print(json.dumps(summary, ensure_ascii=False, indent=2))
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
    p_prb.set_defaults(func=cmd_probe)

    p_app = sub.add_parser("apply", help="Apply card + subtitle plan.json directly to CapCut project and render WYSIWYG preview sheet.")
    p_app.add_argument("project", help="CapCut project name or path")
    p_app.add_argument("--plan", required=True, help="Path to plan.json")
    p_app.add_argument("--preview", help="Optional path for WYSIWYG preview contact sheet (.jpg)")
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
                    {sp: ensure_capcut_font(sp) for sp in a.specs},
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
