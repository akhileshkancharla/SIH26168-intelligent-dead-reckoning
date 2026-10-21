# WP-15.11 submission rehearsal preflight v1

Relates to #16 and #116. Attempt date: 2026-10-18 IST. **Result: `STOPPED_PREFLIGHT` for an executed presentation/video rehearsal.** The synthetic source/desk checks below ran; no spoken performance, final-video playback, integrated device run or completed rehearsal is claimed.

## Frozen input identities

| Input | Exact identity checked | Result / boundary |
| --- | --- | --- |
| [Approved presentation](../../submission/presentation/README.md) | PDF SHA-256 `00ff40f898136944ff2abadb1fda72b07e664bf32c4b7d4547cfdf5820b1df5f` | File bytes match the approved presentation record; content remains unchanged. |
| [Video script and shot list](https://github.com/akhileshkancharla/SIH26168-intelligent-dead-reckoning/blob/39a31ce03c43db5d1a7b15733a67f3c5ec4ba5e8/submission/video/SIH26168_Demo_Video_Script_and_Shot_List_v1.md) | Commit `39a31ce03c43db5d1a7b15733a67f3c5ec4ba5e8`; UTF-8 SHA-256 `14c796025179a0854b410c3aa6573dbded379b7879493c6df9ca914362b927ab` | Fourteen shots and exact Event 1–10 order checked. The script is prepared for review; no reviewer approval is inferred. |
| [Frozen synthetic plan](https://github.com/akhileshkancharla/SIH26168-intelligent-dead-reckoning/blob/c38d33b6e92391057cb1989149a2c15d319e21e7/demo/scenarios/ten_event_synthetic_evidence_plan_v1.json) | Plan SHA-256 `4171cad6d3ed983aa8028ba3c56e22867926f6c7971c42f62aea7ce65a4f294b` | Normal replay eligibility is false and every event remains NOT_EXECUTED. |
| [Canonical S1 fixture](../../contracts/fixtures/s1_acquisition_round_trip_v1_fixture.json) | File SHA-256 `44068a9b5beeade2581a7914707596e5b88b6d85cdcec5f9016752908728f2bb` | Synthetic contract example only; six observations do not supply the full demo run. |
| [Approved storyboard](../architecture/SIH26168_WP15_7_Demo_Narrative_Storyboard_v1.md) | SHA-256 `fe5042fece38d3197b3927042f91aae24f5aaeac7e6b7584edca256f80137a49` | Expected narrative, UI/evidence and truthful fallback source. |

The plan and WP-15.6 report are corrected review candidates awaiting designated approval; no approval is inferred from their immutable identities. In this repeat, the Event 3 I-07/I-08/I-16 guard and recovery-only I-15 guard passed, all frozen source hashes matched, and the refreshed WP-15.6 report pins that exact corrected plan. Its STOPPED_PREFLIGHT finding is unchanged.

## Executed desk/timing checks

The script's shots S00–S13 form contiguous positive-duration intervals from 00:00 to 03:10, with no timecode gaps/overlaps: an editorial budget of 190 seconds. This is not an asserted portal duration requirement. Events 1–10 retain their authoritative order. Mandatory source/replay/demo disclosures, simulated-outage conditions, map attribution, unavailable/architecture-preview wording and scientific/display/reference separation are specified in the script.

For the current synthetic/unavailable path, select each shot's alternative narration, using S13's shared credits wording. Tokenize English words/numbers with internal apostrophe/hyphen preservation. Observed word count: 272. A planning calculation at 120 words/min gives 136.0 seconds; at 150 words/min it gives 108.8 seconds. These are explicit estimates, not a measured read, an accessibility/readability result, a required speaking speed or proof that actual footage fits. Actual pauses, evidence holds, pronunciation and transitions must be timed during rehearsal; captions must match the finally selected wording. Do not shorten by hiding required disclosures or removing evidence holds.

The frozen presentation byte hash matched. Existing fixture round-trip and 21 focused tests passed separately. The [WP-15.6 preflight record](https://github.com/akhileshkancharla/SIH26168-intelligent-dead-reckoning/blob/65eb576d3273f0fb52db259f2b75b80547851bde/docs/operations/WP15_6_SYNTHETIC_REHEARSAL_PREFLIGHT_v1.md) documents why normal playback stopped: missing COMPLETE I-18 metadata, a source-time regression and missing integrated scientific event outputs. Source/contract tests are not a substitute for a presentation/video run.

## Incident and readiness review

| Gate / incident | Observed readiness | Action and required evidence |
| --- | --- | --- |
| Script and scenario owner review | Prepared artifacts/requests exist; current-head approval not established by this report | R5/R6 and designated reviewers approve exact script/scenario/evidence identities before an executed-demo narration path is selected. |
| Final video/media | No accepted final video was supplied or recorded in this task | WP-15.10 records/edits the exact accepted take; retain master/edit-list and final artifact hash in approved storage. |
| Eligible scientific run | Supplied fixture is diagnostic synthetic input, not normal session replay | Supply a separately reviewed eligible input and actual I-07/I-08/I-11/I-15 evidence or keep the segment explicitly unavailable. |
| Spoken delivery and captions | Only word-count arithmetic performed | Conduct and time the real read; inspect captions/pronunciation, pauses and all ten evidence holds. |
| Rendered readability and attribution | Script requirements checked; no final footage/device read performed | Verify portrait/narrow-screen labels, caption placement, legends, health HUD and full map attribution on actual output. |
| Media playback / final package | No final video codec/audio/playback or combined-package check possible | Play the actual export, verify synchronization/duration/hash, confirm current portal format and complete the separate freeze/approval workflow. |

Do not mark these gates passed from the existence of a script, a PDF hash, a desk estimate or a checklist. The synthetic alternative must remain labelled as architecture/source preparation and cannot be presented as a completed ten-event demonstration. No user-selected fixture is silently repaired or promoted to physical evidence. Issues #116/#16 remain open until actual media, eligible runtime/capture evidence, timed rehearsal, incident resolution and designated review exist.

## Reproduction and limits

Use `git show` on the immutable script commit, parse the 14 table-row time ranges, check contiguous endpoints and event order, and count the selected alternative narration as described above. Compute SHA-256 over the frozen files and compare the recorded values. Run `python ci/verify_repository.py all`; exact-head results are in the PR. Python >=3.11 suffices for these source/hash/timing calculations. This one-file documentation change needs no new dependency, Android build or graph regeneration. No raw/private recording, media binary, scientific result or claim of completed rehearsal is generated. Prepared with Codex assistance from the user-designated fixture/storyboard and verified source artifacts.
