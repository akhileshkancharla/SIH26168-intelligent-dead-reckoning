# Known Limitations

- Bootstrap smoke scaffolds are not navigation functionality.
- Android, C++, and Python CI do not use private data, physical devices, GPUs, or IO-VNBD downloads.
- S2 source is intentionally not imported by bootstrap.
- Project `Start date` and `Estimated effort` are intentionally unset until an issue is genuinely scheduled and estimated; no placeholder dates or effort claims were fabricated.
- Local CMake, Java, Gradle, and Android SDK tools are unavailable; C++ and Android checks were therefore verified on GitHub-hosted runners.
- Era's invitation remains pending; her issues retain intended-assignee metadata and are not falsely reported as assigned. Faisal, Zeeshan, Likhitha, and Junaid have active Write access.
- GitHub milestones expose date-level due dates; the M0 description and milestone register preserve the authoritative `2026-09-03 20:00 IST` cutoff.
- The exact branch-check names were established on validation PR #129; strict protection is intentionally the final remote action after the evidence commit, so that commit cannot itself attest to the later API mutation.
