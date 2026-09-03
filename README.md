# SIH26168 — Intelligent Dead Reckoning

Private development monorepo for the SIH26168 submission and its evidence-bounded post-submission engineering program.

Architecture Revision 3 is authoritative and has status `ARCH3-READY-FOR-REPOSITORY-BOOTSTRAP`. Repository bootstrap does not claim completion of S1, S3, S4, runtime map matching, model promotion, live-field validation, or final scientific validation.

Project execution is tracked in the private [SIH26168 Development Roadmap](https://github.com/users/akhileshkancharla/projects/4), which contains all 128 governed repository issues.

## Deadline boundary

- Internal immutable submission freeze: **2026-09-15 (IST)**
- SIH portal deadline: **2026-09-20 (IST)**
- September 16–19 is a correction/upload contingency buffer, not feature-development time.

## Bootstrap smoke checks

- Python: `python -m unittest discover -s tools/bootstrap/tests`
- C++: `cmake -S . -B build && cmake --build build && ctest --test-dir build`
- Android: `gradle -p android testDebugUnitTest lintDebug assembleDebug`
- Full policy verification: `python ci/verify_repository.py all`

The Android application may use deterministic local replay for the submission demonstration. Every replayed screen must display `REPLAY` unmistakably.

## Licence

No software licence has been approved. This private repository is all-rights-reserved pending an explicit owner decision. No `LICENSE` file is intentionally present.
