# Subtitle references and character-card separation

Read this when the user supplies a subtitle appearance reference or character introductions share the screen with captions. The card helper does not currently restyle existing subtitle tracks; the following is editorial guidance and scope control, not a new CLI capability.

## Follow the supplied visual target

Inspect the actual reference instead of replacing it with an interpretation of “cinematic.” Compare letter shape, weight, spacing, relative size, color, background opacity/padding/corners and placement within the picture. For example, a reference may call for compact white monospaced-looking text on a closely fitted translucent black box; that does not make this style the default for every film.

A screenshot alone does not establish the exact font family. Check installed fonts and actual glyph coverage; identify a visual approximation honestly. Do not claim an exact match from native JSON values or an approximate typography study. An exact-match claim needs comparison with actual playback/rendering.

Keep the user's explicit line-count preference unless they change it. A two-line reference image does not by itself revoke an earlier one-line instruction when the request concerns its appearance. Avoid unnecessary cue changes, unreadably small text and word-by-word flashing. If cue splitting is authorized, use readable phrase groups and existing word timings, then review the resulting reading time.

Do not copy a reference movie's letterbox bars, crop or grading into the project unless requested. Keep supplied images local unless the user authorizes publishing them; do not bundle reference frames, fonts, project paths or personal presets into the public skill.

## Keep character labels clear of captions

Character labels must not overlap subtitle lettering **or its background box**. Check the complete display interval, not only the cut or one still. Account for both name and role, actual font extents, stroke/shadow, background padding, transforms, captions changing underneath, camera movement and shot changes.

Prefer a stable subtitle reading band. Place the character label in another clear area near the correct person. A clear patch beside a different person fails identity association even if it avoids the caption. In a two-shot, check each person's label independently and check the labels against each other as well as the subtitle.

If no safe layout exists, shorten wording, adjust the introduction's hold within the same established scene, or defer/omit it with a recorded reason. Do not move a label toward the wrong person, cover subtitles or shrink captions to make an introduction fit. Preserve the user's manually corrected placement and timing.

## Keep edits within the authorized scope

Adding character/time/location cards does not authorize changing subtitle wording, dialect, timing or styling. A separate authorized subtitle edit should preserve unrelated tracks and existing manual title edits, stage a reviewable draft with backups, and retain editor-running and stale-input protections. Do not treat a helper limitation as permission to bypass its validation.

Structural verification establishes file preservation, not native rendering or perceptual separation. Record source/compositing limitations and review the actual rendered bounds before claiming that a layout matches the reference or has no collisions in playback.
