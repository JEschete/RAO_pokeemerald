# Rights and Provenance Audit

Audit date: 2026-09-01

This is a technical inventory, not legal advice.

## Locally Authored Plugin Code

The Python adapter, tests, manifest, and documentation were migrated from `JEschete/RetroArchOverlay`, where they were committed by JEschete. Locally authored plugin code is available under the MIT License. That license does not grant rights to third-party game material, patches, trademarks, or decompilation content.

## `decomp_reference/pokeemerald`

- Source: <https://github.com/pret/pokeemerald>
- Integration: pinned Git submodule, not copied source
- Pinned commit at migration: `5eff78649e7170a877b961ef0b3da13b81a16038`
- Upstream describes the project as a decompilation of Pokemon Emerald.
- No `LICENSE` or `COPYING` file was found at the pinned commit.
- The tracked tree contains reconstructed code, graphics, audio/data, and binary map/layout assets capable of rebuilding a matching ROM when combined with required user-supplied inputs.
- No base ROM is included by this plugin. Plugin ignore rules exclude `baserom.gba`, generated ROMs, saves, and emulator states.

Risk classification: **high copyright/DMCA uncertainty**. Keeping this as a pinned upstream submodule preserves provenance and avoids copying its contents into this repository, but does not eliminate redistribution or contributory-risk questions. Review upstream policy and obtain legal advice before public distribution if risk tolerance is low.

## Professor Oak Challenge BPS Patch

- Path: `game/assets/patches/professor_oak_challenge/Pokemon - Emerald Version [Subset - Professor Oak Challenge].bps`
- Size: 33 bytes
- Introduced by JEschete in the original core repository commit `a2b5f6101165d815e5dda2f447faa21c6dea1c06`.
- The accompanying readme identifies the required clean-ROM hashes but provides no patch author, source URL, license, or redistribution permission.
- The file is a binary patch, not a ROM image. Its very small size substantially limits embedded expression, but provenance and permission remain unresolved.

Risk classification: **unresolved provenance**. Do not represent this patch as licensed or endorsed. Replace it with a documented upstream download reference or written permission when available.

## Trademarks and User-Supplied Content

Pokemon, Nintendo, Game Freak, and related names are identifiers for compatibility. No affiliation or endorsement is claimed. Users are responsible for lawfully obtaining any ROM used with RetroArch or the decompilation workflow.

## Release Gate

Before tagging a public release:

1. Choose and add a license covering only locally authored plugin code.
2. Decide whether the `pret/pokeemerald` submodule is acceptable under the project's legal risk policy.
3. Resolve or remove the BPS patch's missing provenance.
4. Verify `git ls-files` contains no ROM, save, state, generated ROM, secret, or credential.
5. Re-run this audit whenever the submodule commit or binary assets change.
