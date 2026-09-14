# Pokemon Emerald Qt Migration Status

Status: Complete under the revised correctness-only migration gate

Started: 2026-09-13

## Architecture

Pokemon Emerald remains toolkit-neutral. Production code emits immutable keyed
panel and map documents and imports neither PySide6 nor Tkinter. The shared Qt
host owns all widgets, maps, detail actions, image loading, filtering, and view
state.

## Completed

- All 48 direct `PanelSection` and `PanelAction` construction sites declare
  stable feature-owned keys, enforced by an AST regression guard.
- Sections use only the shared `area`, `party`, `goals`, and `urgent` roles.
  Dynamic titles, counts, species, coordinates, and error messages no longer
  determine Qt widget identity.
- Adapter activation, deactivation, and title-screen transitions clear party,
  battle-participation, hunt-session, journal-event, Pickup, and world-overlay
  baselines while preserving Trainer-ID-scoped durable history.
- Legitimate battle-entry SaveBlock1/SaveBlock2 relocation now re-reads the
  authoritative Trainer ID and rebinds training, hunt, and journal persistence
  before rebuilding the snapshot.
- Real overworld, title, wild-battle, and maximum-density Route 119 snapshots
  render through `PanelDocumentView`. Role filtering, every action widget,
  expanded Party Details, section identity, icons, chips, progress, and live
  value updates are covered.
- Wild, trainer, double, Safari, and no-reward Frontier battle behavior remains
  covered, including runtime opponent rosters, catch odds, reward projection,
  stat-stage damage advice, switch participation, and IV comparisons. Wild IV
  verdicts include checksum-valid Pokémon from all 14 live PC boxes and identify
  the winning party or box slot; storage is read once per encounter and degrades
  to a labeled party-only comparison when unavailable.
- Every Battle Frontier facility ID is decoded and tested; Factory rental/swap
  and Pyramid state remain covered by their focused suites.
- Hunt outcomes and lifetime reload, journal JSONL/Markdown reload, Pickup
  deduplication, Trainer-ID isolation, optional-region failures, and available
  or degraded RetroAchievements account state are covered.
- Real decomp-derived Route 119 and Hoenn maps render lazily through `QtMapView`.
  Representative route, city, indoor, cave, and underwater layers switch and
  render in one view with calibrated player positions and live overlays.
- Generated map and species-icon PNGs use same-directory atomic replacement.
  Interrupted writes leave no apparently valid cache file.
- Map and icon cache directories are versioned from the pinned decomp revision
  and renderer source. Local map reuse is verified within a version.
- The toolkit-neutral species-icon path cache is LRU-bounded to 128 entries;
  missing artwork, renderer failure, and disabled renderer/state-directory paths
  degrade to text-only rows.
- Professor Oak Challenge, navigation, encounters, Feebas, roamers, repel,
  training observations, contests, daycare, RTC/berries, Match Call, legendary
  tracking, Frontier, collections, session journal, and account progress remain
  represented through the shared contracts.
- The complete plugin suite passes with 171 tests, 61 subtests, no warnings,
  and no skips.
- `tools/generate_knowledge.py --check` passes against the pinned decomp.

## Host Evidence

The complete base suite passes with 329 tests and seven waived native-only skips.
Architecture tests continue to ban PySide6, PyQt6, and Tkinter from
plugin production code.

Installer, accessibility, native-platform, and performance acceptance are not
phase gates under decisions D-010 through D-014. No copyrighted ROM data or
generated game graphics are distributed; runtime generation uses the user's
pinned decomp checkout and local plugin-state directory.