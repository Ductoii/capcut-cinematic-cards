import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "skills" / "capcut-cinematic-cards" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import cards
import native_text


class CinematicCardsEngineTest(unittest.TestCase):
    def test_multi_span_rich_text_hierarchy_and_colors(self):
        style = native_text.resolve_style(
            {
                "title_font": "Baskerville-Bold",
                "detail_font": "Baskerville-SemiBoldItalic",
                "char_title_color": "#F3CA6E",
                "char_detail_color": "#F6EFE2",
                "detail_accent_color": "#F2CE7E",
                "flanker_color": "#D8B268",
            }
        )
        title_spans = native_text.compute_rich_text_spans(
            "Dr. Josie Calder", style.character_title, is_title=True
        )
        self.assertEqual(len(title_spans), 2)
        self.assertEqual(title_spans[0][2], "#F6EFE2")
        self.assertEqual(title_spans[0][3], style.character_title.font_size)
        self.assertEqual(title_spans[1][2], "#F3CA6E")

        detail_text = native_text.format_detail_with_flankers(
            "Stable Hand · Former Master Horseman", "—"
        )
        detail_spans = native_text.compute_rich_text_spans(
            detail_text, style.character_detail, is_title=False
        )
        self.assertGreaterEqual(len(detail_spans), 5)
        self.assertEqual(detail_spans[0][3], style.character_detail.font_size)
        payload = json.loads(
            native_text.build_rich_text_content(
                detail_text, style.character_detail, is_title=False
            )
        )
        self.assertEqual(payload["text"], detail_text)
        self.assertEqual(len(payload["styles"]), len(detail_spans))
        self.assertEqual(payload["styles"][0]["size"], style.character_detail.font_size)

    def test_centered_axis_symmetry_and_outer_edge_bounds(self):
        x_t, x_d, y_t, y_d, sc = native_text.resolve_card_position(
            {
                "kind": "char",
                "title": "Tamarack",
                "detail": "«  $5M Champion · Thoroughbred Stallion  »",
                "anchor": "lower-right",
            },
            title_font="Baskerville-Bold",
            detail_font="Baskerville-SemiBoldItalic",
            title_size=6.8,
            detail_size=4.3,
            align="center",
            order="title-first",
        )
        self.assertEqual(x_t, x_d)
        self.assertGreater(x_t, 0.30)
        self.assertLess(x_t, 0.80)
        self.assertGreater(y_t, y_d)

    def test_native_fade_in_out_resource_ids_and_out_start_offset(self):
        preset = native_text.resolve_style({"stagger_sec": 0.10})
        pair = native_text.build_card_pair(
            card_id="test_01",
            kind="char",
            title_text="Elijah Fairley",
            detail_text="—  Stable Hand · Former Master Horseman  —",
            start_us=8_000_000,
            duration_us=3_500_000,
            x=0.45,
            y_title=-0.32,
            preset=preset,
        )
        t_anims = pair.title_animation["animations"]
        self.assertEqual(len(t_anims), 2)
        self.assertEqual(t_anims[0]["id"], "6724916044072227332")
        self.assertEqual(t_anims[0]["category_id"], "ruchang")
        self.assertEqual(t_anims[0]["start"], 0)
        self.assertEqual(t_anims[1]["id"], "6724919382104871427")
        self.assertEqual(t_anims[1]["category_id"], "chuchang")
        self.assertEqual(
            t_anims[1]["start"],
            pair.title_segment["target_timerange"]["duration"] - t_anims[1]["duration"],
        )
        self.assertGreater(
            pair.detail_segment["target_timerange"]["start"],
            pair.title_segment["target_timerange"]["start"],
        )

    def test_compound_clip_trim_immune_unwrapping_and_apply_plan(self):
        draft = {
            "duration": 20_000_000,
            "materials": {
                "videos": [],
                "texts": [],
                "material_animations": [],
                "drafts": [
                    {
                        "id": "sub_1",
                        "draft": {
                            "materials": {
                                "videos": [
                                    {"id": "v1", "path": "/tmp/V-001.mp4"},
                                    {"id": "v2", "path": "/tmp/V-002.mp4"},
                                ]
                            },
                            "tracks": [
                                {
                                    "type": "video",
                                    "segments": [
                                        {
                                            "material_id": "v1",
                                            "target_timerange": {"start": 0, "duration": 10_000_000},
                                            "source_timerange": {"start": 0, "duration": 10_000_000},
                                        },
                                        {
                                            "material_id": "v2",
                                            "target_timerange": {"start": 10_000_000, "duration": 10_000_000},
                                            "source_timerange": {"start": 0, "duration": 10_000_000},
                                        },
                                    ],
                                }
                            ],
                        },
                    }
                ],
            },
            "tracks": [
                {
                    "type": "video",
                    "segments": [
                        {
                            "material_id": "sub_1",
                            "target_timerange": {"start": 0, "duration": 12_000_000},
                            "source_timerange": {"start": 4_000_000, "duration": 12_000_000},
                        }
                    ],
                }
            ],
        }
        segs = cards.load_video_timeline(draft)
        self.assertEqual(len(segs), 2)
        self.assertAlmostEqual(segs[0].source_start_s, 4.0)
        self.assertAlmostEqual(segs[0].timeline_dur_s, 6.0)
        self.assertAlmostEqual(segs[1].source_start_s, 0.0)
        self.assertAlmostEqual(segs[1].timeline_dur_s, 6.0)

        summary = cards.apply_plan_to_draft(
            draft,
            {
                "style": {
                    "title_font": "Baskerville-Bold",
                    "detail_font": "Baskerville-SemiBoldItalic",
                    "flankers": "—",
                },
                "cards": [
                    {
                        "kind": "char",
                        "start": 1.0,
                        "end": 4.5,
                        "title": "Elijah Fairley",
                        "detail": "Stable Hand · Former Master Horseman",
                        "anchor": "lower-right",
                    }
                ],
            },
            snap_to_cuts=False,
        )
        self.assertEqual(summary["cards_applied"], 1)
        self.assertEqual(len(draft["materials"]["texts"]), 2)
        self.assertEqual(len(draft["materials"]["material_animations"]), 2)

    def test_screenplay_grounded_subtitle_normalization_and_default_yellow_style(self):
        import re

        sp_ctx = {
            "shot_windows": [
                (10.0, 18.0, "You are a lifeguard on Coral Reach, Wes."),
                (20.0, 28.0, "Under Clause 9, you must vacate this shack immediately!"),
            ],
            "proper_nouns": {"wes": "Wes", "lenora": "Lenora", "alford": "Alford", "wexler": "Wexler"},
            "valid_lower_vocab": {"you", "are", "lifeguard", "coral", "reach", "under", "clause", "must", "vacate", "this", "shack"},
            "canonical_phrases": [
                (re.compile(r"\b(?:clause|claws|close|clothes|claus)\s+9\b", re.I), "Clause 9"),
                (re.compile(r"\bCoral\s+Ree[a-z]+\b", re.I), "Coral Reach"),
            ],
        }
        c1 = native_text._normalize_cue_with_screenplay("you are a life Lord on Coral Reef, wes", 11.0, 15.0, sp_ctx)
        c1 = native_text._apply_sentence_case_and_tokens(c1)
        self.assertEqual(c1, "You are a lifeguard on Coral Reach, Wes")

        c2 = native_text._normalize_cue_with_screenplay(
            "under claws 9 you must vacate this Jack with lanira and alford", 21.0, 26.0, sp_ctx
        )
        c2 = native_text._apply_sentence_case_and_tokens(c2)
        self.assertEqual(c2, "Under Clause 9 you must vacate this shack with Lenora and Alford")

        rec = cards.recommend_style_for_screenplay(
            {"scenes": [{"name": "LIFEGUARD TOWER AT CORAL REACH BEACH", "sfs": [{"label": "WES — SENIOR OCEAN LIFEGUARD"}]}]},
            "LIFEGUARD-TEST",
        )
        self.assertEqual(rec["archetype"], "coastal_lifeguard_rescue")
        self.assertEqual(rec["align"], "center")
        self.assertEqual(rec["title_font"], "Cinzel-Bold")
        self.assertEqual(rec["detail_font"], "Lora-BoldItalic")
        self.assertEqual(rec["detail_size"], 5.0)

        rec_bbq = cards.recommend_style_for_screenplay(
            {"scenes": [{"name": "BARBECUE PAVILION AT COUNTY FAIR", "sfs": [{"label": "CLEMENTINE — MASTER PITMASTER"}]}]},
            "BBQ-TEST",
        )
        self.assertEqual(rec_bbq["archetype"], "rustic_heartland_americana")
        self.assertEqual(rec_bbq["title_font"], "Fraunces-Bold")
        self.assertEqual(rec_bbq["scene_title_font"], "Bitter-Bold")
        self.assertEqual(rec_bbq["detail_font"], "Lora-BoldItalic")
        self.assertEqual(rec_bbq["detail_size"], 5.0)
        self.assertEqual(rec_bbq["scene_detail_size"], 5.0)
        self.assertEqual(rec_bbq["align"], "center")


if __name__ == "__main__":
    unittest.main()
