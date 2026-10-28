# Release review and decisions

One fresh, read-only whole-branch review identified four release blockers. All entered a single regression-driven fix pass:

- **Staging snapshot:** a save after loading could become the accepted baseline. Staging now binds canonical bytes, mirror membership, backups and before hashes to the analyzed inventory and rechecks it. A save during loading and a new mirror after review are covered by failing-then-passing regressions.
- **Queued revision:** Apply checked freshness only at dispatch. Execution now holds the same registry lock used by revision creation, checks the latest revision again, and rejects obsolete queued work. A blocked-worker regression proves it never reaches the writer.
- **Crash recovery:** a hard exit could leave the shared project lock. Harness transactions reclaim only a positively dead numeric owner, serialize competing recoveries with an OS lock and preserve live/uncertain owners. A real subprocess hard exit after the second write in an indexed multi-mirror transaction is recovered through service restart/Retry and exact Undo.
- **Quality evidence:** LUFS-target misses did not describe VAD uncertainty, near-full-scale source samples or limiting. The report/UI now separates those measured flags. Actual VAD, hot-source and rendered-limiter regressions cover the evidence. Scores are not calibrated confidence, near-full-scale samples do not prove historical distortion, and music-vocal classification is explicitly unassessed.

All reproductions failed before their fixes and passed afterward. Final suite: 66 tests; browser A/B/guards/Apply/Undo and responsive checks also passed. No minor findings were deferred. Native editor rendering was not claimed.

## Rulings made during execution

- The native worktree API could not attach this nested repository under the chat root. A Git worktree provided isolation instead. Cost: it had no native app worktree attachment; code and commits remained reviewable in Git.
- The plan's final task includes publication and depends on its own review. Implementation was committed/reviewed before publication, and task completion waits for public installation verification. Cost: publication waits for any required fixes.

## Review scope decisions

- Native CapCut playback/export remains unverified, as allowed by the approved design; file verification and source-reconstructed audio do not establish it. Cost: the user must assess actual editor playback after an authorized Apply.
- Public-tag installation is evaluated after publication, when that source exists. Cost: a release problem would need a corrective release rather than pretending a pre-publication check was public evidence.
- Automated singer/speaker identification is outside this VAD capability. Honest uncertainty is required and is reported. Cost: vocals/false detections need listening review and exclusions.
