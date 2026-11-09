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

        sp_ctx_local = {
            "shot_windows": [
                (100.0, 110.0, "CLERK: You after stall nine? I'm after the card first."),
                (120.0, 130.0, "LOOMIS: Entered and occupied. Authority? Lessee of record. Millbank."),
                (140.0, 150.0, "CLEMENTINE: Mr. Millbank. Where second judges sign. When I set it down in the judges' back room."),
            ],
            "proper_nouns": {"millbank": "Millbank"},
            "valid_lower_vocab": {"you", "after", "stall", "nine", "authority", "lessee", "of", "record", "millbank", "where", "second", "judges", "sign", "when", "set", "down", "back", "room"},
            "canonical_phrases": [],
        }
        self.assertEqual(
            native_text._apply_sentence_case_and_tokens(
                native_text._normalize_cue_with_screenplay("You have to stall nine", 102.0, 105.0, sp_ctx_local)
            ),
            "You after stall nine",
        )
        self.assertEqual(
            native_text._apply_sentence_case_and_tokens(
                native_text._normalize_cue_with_screenplay("Authority let's see a record Millbank", 122.0, 126.0, sp_ctx_local)
            ),
            "Authority Lessee of record Millbank",
        )
        self.assertEqual(
            native_text._apply_sentence_case_and_tokens(
                native_text._normalize_cue_with_screenplay("Where second judge is signed", 142.0, 145.0, sp_ctx_local)
            ),
            "Where second judges sign",
        )
        self.assertEqual(
            native_text._apply_sentence_case_and_tokens(
                native_text._normalize_cue_with_screenplay("Master Millbank", 141.0, 143.0, sp_ctx_local)
            ),
            "Mr. Millbank",
        )
        self.assertEqual(
            native_text._apply_sentence_case_and_tokens(
                native_text._normalize_cue_with_screenplay("When I set it down in the judge's back room", 145.0, 148.0, sp_ctx_local)
            ),
            "When I set it down in the judges' back room",
        )

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

    def test_char_appearances_when_usedBy_is_empty_and_cold_open_hook_present(self):
        vsegs = [
            cards.VideoSegment(0, 0.0, 20.0, 20.0, 0.0, 20.0, 1.0, "/tmp/V-021.mp4", "V-021.mp4"),
            cards.VideoSegment(1, 20.0, 38.0, 18.0, 0.0, 18.0, 1.0, "/tmp/V-022.mp4", "V-022.mp4"),
            cards.VideoSegment(2, 38.0, 58.1, 20.1, 0.0, 20.1, 1.0, "/tmp/V-023.mp4", "V-023.mp4"),
            cards.VideoSegment(3, 58.1, 78.1, 20.0, 0.0, 20.0, 1.0, "/tmp/V-001.mp4", "V-001.mp4"),
            cards.VideoSegment(4, 78.1, 98.1, 20.0, 0.0, 20.0, 1.0, "/tmp/V-002.mp4", "V-002.mp4"),
            cards.VideoSegment(5, 481.77, 507.63, 25.86, 0.0, 25.86, 1.0, "/tmp/V-021.mp4", "V-021.mp4"),
            cards.VideoSegment(6, 931.57, 954.50, 22.93, 0.0, 22.93, 1.0, "/tmp/V-036.mp4", "V-036.mp4"),
        ]
        sf_data = {
            "scenes": [
                {
                    "id": "S1",
                    "name": "REF",
                    "sfs": [
                        {
                            "id": "CHAR1a",
                            "label": "TERRELL VANCE — SUIT HIỆN ĐẠI (38 TUỔI)",
                            "desc": "Nam da màu 38 tuổi, tỷ phú địa ốc.\nDùng: 001–006 · 021–023.",
                            "usedBy": [],
                        },
                        {
                            "id": "CHAR2a",
                            "label": "TUCKER REID — CỐ VẤN PHÁP LÝ (42 TUỔI)",
                            "desc": "Nam da trắng 42 tuổi, cố vấn pháp lý tập đoàn.\nDùng: 001–002 · 021.",
                            "usedBy": [],
                        },
                        {
                            "id": "CHAR3a",
                            "label": "ABNER / SILAS FREEMAN — NGƯỜI GIỮ KHO (76 TUỔI)",
                            "desc": "Ông lão da màu 76 tuổi, đầu tiên xưng tên Abner, sau lộ diện là Silas Freeman.\nDùng: 002 · 036.",
                            "usedBy": [],
                        },
                    ],
                },
                {
                    "id": "S2",
                    "name": "CỔNG RÀO & HIÊN NHÀ 414",
                    "sfs": [
                        {
                            "id": "V-001",
                            "goc": "4 shot: toàn mở TERRELL+TUCKER → trung cận TUCKER nói → cận TERRELL",
                            "notes": "REF (3): IMG1a CHAR1a CHAR2a",
                            "prompt": "Scene 001: REF IMG1a, CHAR1a, CHAR2a: ...",
                            "text": "TUCKER: Twenty-two minutes on the clock, Terrell.\nTERRELL: Keep the bulldozer idling at the curb.",
                        },
                        {
                            "id": "V-002",
                            "goc": "4 shot: toàn hiên nhà ABNER bước ra → cận ABNER nói",
                            "notes": "REF (3): IMG1a CHAR1a CHAR3a",
                            "prompt": "Scene 002: REF IMG1a, CHAR1a, CHAR3a: ...",
                            "text": "ABNER: Name's Abner. I watch the porch when the rain comes.",
                        },
                    ],
                },
                {
                    "id": "S9",
                    "name": "PHÒNG KHÁCH NHÀ 414 — ĐỐI ĐẦU",
                    "sfs": [
                        {
                            "id": "V-021",
                            "goc": "4 shot: toàn phòng khách → cận TERRELL",
                            "notes": "REF (3): IMG4a CHAR1a CHAR2a",
                            "prompt": "Scene 021: REF IMG4a, CHAR1a, CHAR2a: ...",
                            "text": "TERRELL: Nobody touches a single beam in this house.",
                        }
                    ],
                },
                {
                    "id": "S14",
                    "name": "KHO LƯU TRỮ — LỘ DIỆN SILAS FREEMAN",
                    "sfs": [
                        {
                            "id": "V-036",
                            "goc": "4 shot: cận SILAS mở sổ cái → cận TERRELL sững sờ",
                            "notes": "REF (2): CHAR1a CHAR3a",
                            "prompt": "Scene 036: REF CHAR1a, CHAR3a: ...",
                            "text": "SILAS: My middle name is Abner. My legal name on the deed is Silas Freeman.",
                        }
                    ],
                },
            ]
        }
        subtitles = [
            {"index": 1, "start_s": 59.5, "end_s": 64.2, "text": "Twenty-two minutes on the clock, Terrell."},
            {"index": 2, "start_s": 65.0, "end_s": 69.1, "text": "Keep the bulldozer idling at the curb."},
            {"index": 3, "start_s": 80.2, "end_s": 85.4, "text": "Name's Abner. I watch the porch when the rain comes."},
            {"index": 4, "start_s": 935.0, "end_s": 942.5, "text": "My middle name is Abner. My legal name on the deed is Silas Freeman."},
        ]

        gt = cards.extract_screenplay_ground_truth(sf_data, vsegs, subtitles=subtitles)
        self.assertEqual(gt["hook_window_s"], [0.0, 58.1])
        scenes_by_id = {s["scene_id"]: s for s in gt["story_scenes"]}
        self.assertAlmostEqual(scenes_by_id["S2"]["start_s"], 58.1, places=1)
        self.assertAlmostEqual(scenes_by_id["S9"]["start_s"], 481.77, places=1)
        self.assertEqual(gt["character_count"], 3)

        chars_by_id = {c["char_group"]: c for c in gt["character_appearances"]}
        self.assertIn("CHAR1", chars_by_id)
        self.assertIn("CHAR2", chars_by_id)
        self.assertIn("CHAR3", chars_by_id)
        self.assertAlmostEqual(chars_by_id["CHAR1"]["first_timeline_s"], 58.1, places=1)
        self.assertGreaterEqual(len(chars_by_id["CHAR3"]["all_scene_appearances"]), 2)
        self.assertEqual(chars_by_id["CHAR3"]["all_scene_appearances"][0]["scene_id"], "S2")
        self.assertEqual(chars_by_id["CHAR3"]["all_scene_appearances"][1]["scene_id"], "S14")
        self.assertTrue(len(chars_by_id["CHAR2"].get("speaker_turns", [])) >= 1)
        self.assertAlmostEqual(chars_by_id["CHAR2"]["speaker_turns"][0]["start_s"], 59.5, places=1)

        # Verify CHAR1a prefix stripping & Vietnamese role/scene translation
        c_title, c_detail = cards._clean_char_title_and_detail(
            "CHAR1a — TERRELL FREEMAN (38) · áo len cashmere navy (thứ Bảy)",
            "Chính diện · 38 tuổi · tỉ phú bất động sản, mua trọn phố Mulberry",
        )
        self.assertEqual(c_title, "Terrell Freeman, 38")
        self.assertEqual(c_detail, "Billionaire Real Estate CEO")

        v_title, v_detail = cards._clean_char_title_and_detail(
            "CHAR6a — TÌNH NGUYỆN VIÊN NHÀ THỜ (60s) · tạp dề hoa",
            "Vai phụ · ngoài 60 · tình nguyện viên bếp ăn từ thiện Grace Chapel",
        )
        self.assertEqual(v_title, "Church Volunteer, 60s")
        self.assertEqual(v_detail, "Grace Chapel Soup Kitchen")

        s_title, s_detail = cards._clean_scene_title_and_detail(
            "S2 — Phòng họp Freeman Development (sáng thứ Sáu)",
            "IMG2a = the one location: a sleek glass-walled downtown boardroom in the morning",
            1,
        )
        self.assertEqual(s_title, "Freeman Development Boardroom")
        self.assertEqual(s_detail, "Friday Morning · Interior")

        starter = cards.generate_starter_plan({**gt, "duration_sec": 960.0})
        for idx_sc in range(1, len(starter["cards"]) - 1):
            self.assertGreaterEqual(
                starter["cards"][idx_sc]["start"],
                starter["cards"][idx_sc - 1]["end"] + 0.2,
            )

    def test_upper_sky_glare_avoidance_and_adaptive_daylight_contrast(self):
        import tempfile
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmpdir:
            sky_frame = pathlib.Path(tmpdir) / "sky_frame.jpg"
            img = Image.new("RGB", (640, 360), (24, 28, 30))
            for y in range(0, 160):
                for x in range(0, 640):
                    img.putpixel((x, y), (248, 248, 252))
            img.save(sky_frame, quality=95)

            zones = cards.score_frame_negative_space(sky_frame)
            self.assertGreater(zones["upper-right"]["p90_luma"], 220.0)
            self.assertLess(zones["lower-left"]["p90_luma"], 60.0)

            flipped_anchor, reason = cards.resolve_glare_safe_anchor("upper-right", zones, is_scene_card=True)
            self.assertIn(flipped_anchor, ("lower-left", "lower-right"))
            self.assertIn("glare", reason)

            bright_frame = pathlib.Path(tmpdir) / "bright_daylight.jpg"
            Image.new("RGB", (640, 360), (228, 232, 238)).save(bright_frame, quality=95)
            bright_zones = cards.score_frame_negative_space(bright_frame)
            preset = native_text.resolve_style({"stroke_width": 0.015, "shadow_alpha": 0.45, "shadow_smoothing": 0.10})
            t_st, d_st, _, _ = native_text.resolve_card_styles({"kind": "scene", "title": "414 Mulberry"}, preset)
            t_st_boosted, d_st_boosted, boosted = cards.apply_daylight_contrast_guard(
                t_st, d_st, bright_zones["upper-right"]
            )
            self.assertTrue(boosted)
            self.assertGreaterEqual(t_st_boosted.stroke_width, 0.028)
            self.assertGreaterEqual(t_st_boosted.shadow_alpha, 0.82)

        rec_ebony = cards.recommend_style_for_screenplay(
            {
                "scenes": [
                    {
                        "name": "CỔNG RÀO & HIÊN NHÀ 414 MULBERRY",
                        "sfs": [{"label": "TERRELL VANCE — TỶ PHÚ ĐỊA ỐC VANCE HOLDINGS"}],
                    }
                ]
            },
            "64-Ebony Rise-Billionaire Came Back to Bulldoze His Childhood Home",
        )
        self.assertEqual(rec_ebony["archetype"], "philanthropic_real_estate_heritage")
        self.assertEqual(rec_ebony["align"], "center")

    def test_outro_black_sec_and_api_aliases(self):
        seg = cards.VideoSegment(0, 0.0, 12.5, 12.5, 0.0, 12.5, 1.0, "/tmp/V-001.mp4", "V-001.mp4")
        self.assertAlmostEqual(seg.duration_s, 12.5)
        self.assertEqual(seg.material_path, "/tmp/V-001.mp4")
        self.assertIs(cards.extract_video_segments, cards.load_video_timeline)
        self.assertEqual(cards.extract_video_segments({"tracks": [], "materials": {}}), [])

        cuts_res = cards.detect_window_cuts([seg], 0.0, 12.5, threshold=12.0, enable_scdet=False)
        self.assertIn("fast_cuts", cuts_res)

        parser = cards.build_parser()
        ns_inspect = parser.parse_args(["inspect", "1109", "--screenplay", "/tmp/sf-board.json"])
        self.assertEqual(ns_inspect.screenplay, "/tmp/sf-board.json")
        ns_apply = parser.parse_args(["apply", "1109", "--plan", "/tmp/plan.json", "--screenplay", "/tmp/sf-board.json"])
        self.assertEqual(ns_apply.screenplay, "/tmp/sf-board.json")

        # Verify monotonic & contiguous _align_speaker_turns_with_subtitles
        dlg = (
            "TERRELL: I'm not going to hurt you.\n"
            "ABNER: I know you won't.\n"
            "TERRELL: How long have you been up here?\n"
            "ABNER: Two winters.\n"
            "TERRELL: Did you know the family that lived here?"
        )
        cues = [
            {"start_s": 612.9, "end_s": 615.0, "text": "I'm not going to hurt you."},
            {"start_s": 618.6, "end_s": 620.8, "text": "How long have you been up here?"},
            {"start_s": 621.2, "end_s": 622.6, "text": "Two winters."},
            {"start_s": 625.2, "end_s": 627.2, "text": "Did you know the family that lived here?"},
        ]
        turns = cards._align_speaker_turns_with_subtitles(dlg, 606.1, 635.5, cues)
        self.assertEqual(len(turns), 5)
        for i in range(1, len(turns)):
            self.assertGreaterEqual(turns[i]["start_s"], turns[i - 1]["end_s"] - 0.05)

        # Verify two-shot character side detection from screenplay prompt
        prompt_v015 = (
            "wide shot of IMG5a, CHAR5a sitting alone at the right end of a long folding table, "
            "CHAR6a walking over from the serving window on the left | "
            "shot 4: medium shot of CHAR5a and CHAR6a, VO: \"You could knock on his door, Abner.\" | "
            "shot 5: close-up on CHAR5a, head and shoulders, VO: \"He told the whole city I don't exist.\""
        )
        self.assertEqual(
            cards._detect_two_shot_char_side_anchor("CHAR6", prompt_v015, "You could knock on his door, Abner."),
            "lower-left",
        )
        self.assertIsNone(
            cards._detect_two_shot_char_side_anchor("CHAR5", prompt_v015, "He told the whole city I don't exist."),
        )


if __name__ == "__main__":
    unittest.main()
