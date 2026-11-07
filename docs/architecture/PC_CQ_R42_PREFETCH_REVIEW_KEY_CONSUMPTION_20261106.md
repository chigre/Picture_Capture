# R4.2 Review prefetch key consumption — synthetic E2 audit (2026-11-06)

The prefetch producer stores a `review_key` capturing settings, zoom, view scale and canvas width. Previously `_take_prefetched_page` validated project root and file signature but did not validate this rendering identity. A stale page could therefore be consumed after visual configuration changed.

Five synthetic tests: unchanged key positive hit and four stale-key rejections. Test-only RED commit `33950be0d83d0f89a9aec292cebd28bd4c62a389`, CI #42153524993 Ubuntu3.13: 4 failed / 5738 passed / 3 skipped. Minimal production commit `96068259c2dd3502057a18d264fa062c298e9a12` adds `payload.get("review_key") != self._review_prefetch_key()` rejection before cache return; project-root and file-signature checks are preserved. A legacy synthetic fixture omitted the new key; test-only fixture correction `71c75c724db56904fc22735c3f36e175ad385742` restores a valid positive case without weakening the stale-file-signature negative case.

Source/test exact HEAD `71c75c724db56904fc22735c3f36e175ad385742`: CI #42166033872 six matrices and Risk tier/gate SUCCESS, Ubuntu3.13 5742 passed / 3 skipped; OCR #42166033871 3/3 SUCCESS; dynamic CodeQL #42166029968 Python/Actions 2/2 SUCCESS. Documentation architecture check SKIPPED. Documentation commit has a distinct SHA and needs its own checks.

Scope: pure synthetic E2, no real PDIC/PPP/SECTION/Profile/OCR or original images, no human E3, no performance or accuracy claims, no persistence schema/transaction/XY changes. All previously deferred human and real-scan work remains deferred.
