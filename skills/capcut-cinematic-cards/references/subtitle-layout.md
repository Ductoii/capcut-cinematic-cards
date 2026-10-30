# Subtitle references and character-card separation

Read this when the user supplies a subtitle appearance reference or character introductions share the screen with captions. Adding cards alone never authorizes subtitle changes. For a separately authorized appearance change, the helper supports a reviewed native `subtitle_template`; the command reference documents its guarded transaction.

## Follow the supplied visual target

Inspect the actual reference instead of replacing it with an interpretation of “cinematic.” Compare letter shape, weight, spacing, relative size, color, background opacity/padding/corners and placement within the picture. For example, a reference may call for compact white monospaced-looking text on a closely fitted translucent black box; that does not make this style the default for every film.

A screenshot alone does not establish the exact font family. Check installed fonts and actual glyph coverage; identify a visual approximation honestly. Do not claim an exact match from native JSON values or an approximate typography study. An exact-match claim needs comparison with actual playback/rendering.

Matching font/color alone does not reproduce the reference composition. Compare typical and longest line lengths, line breaks and the box silhouette. A long single line about twice the reference line length is not a compact two-line treatment merely because the font matches. For a monospaced reference, character count can guide phrase wrapping; it still does not prove native pixel width. A tightly cropped reference may not establish relative canvas size, so keep that limit explicit and use an actual native example when available.

Keep the user's explicit line-count preference unless they change it. A two-line reference image does not by itself revoke an earlier one-line instruction when the request concerns its appearance. Avoid unnecessary cue changes, unreadably small text and word-by-word flashing. If cue splitting is authorized, use readable phrase groups and existing word timings, then review the resulting reading time.

Do not copy a reference movie's letterbox bars, crop or grading into the project unless requested. Keep supplied images local unless the user authorizes publishing them; do not bundle reference frames, fonts, project paths or personal presets into the public skill.

## Keep character labels clear of captions

Character labels must not overlap subtitle lettering **or its background box**. Check the complete display interval, not only the cut or one still. Account for both name and role, actual font extents, stroke/shadow, background padding, transforms, captions changing underneath, camera movement and shot changes.

Prefer a stable subtitle reading band. Place the character label in another clear area near the correct person. A clear patch beside a different person fails identity association even if it avoids the caption. In a two-shot, check each person's label independently and check the labels against each other as well as the subtitle.

If no safe layout exists, shorten wording, adjust the introduction's hold within the same established scene, or defer/omit it with a recorded reason. Do not move a label toward the wrong person, cover subtitles or shrink captions to make an introduction fit. Preserve the user's manually corrected placement and timing.

## Keep edits within the authorized scope

Adding character/time/location cards does not authorize changing subtitle wording, dialect, timing or styling. A separate authorized subtitle edit should preserve unrelated tracks and existing manual title edits, stage a reviewable draft with backups, and retain editor-running and stale-input protections. Do not treat a helper limitation as permission to bypass its validation.

Structural verification establishes file preservation, not native rendering or perceptual separation. Record source/compositing limitations and review the actual rendered bounds before claiming that a layout matches the reference or has no collisions in playback.

## Supported native template path

Use root `subtitle_template` with an existing local `source_project`, its fresh `source_project_sha256`, an actual subtitle `material_id` and a specific `review`. The helper pins the source draft and readable font files, copies native appearance fields (including background enable flags), and synchronizes `content`/`base_content`. It operates on top-level native subtitle cues, preserving cue words, recognition/word metadata, timing, audio and unrelated tracks; it does not open or rewrite compound clips. An optional `y` raises the captions without changing x or scale. Inspect target segment scales separately; copying a material does not calibrate arbitrary transforms.

Optional `wrap_columns` balances at most two lines at word boundaries and refuses an overlong cue instead of truncating it. It is an editorial line-break constraint, not a glyph measurement. Keep it absent when existing breaks should stay. The source template must have one reviewed text style. A template used successfully in a real render is stronger evidence than invented native values, but target native playback still needs review. `restore` retains the exact original cues and appearance. Do not write a separate private subtitle mutator or convert editable captions to image overlays.

When a character introduction is deliberately delayed past a handoff or other important action, review the subtitle appearance during that intervening action as well as the later card. Include the complete relevant cue, including any cut to an insert/macro and its tail. Use a reviewed exact-ID placement when necessary; do not let card-only preview selection hide an earlier caption collision.
