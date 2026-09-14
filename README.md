# RAO pokeemerald Plugin

Pokemon Emerald integration for the RetroArch Overlay core harness.

## Checkout

```powershell
git clone --recurse-submodules https://github.com/JEschete/RAO_pokeemerald.git
```

If the repository was cloned without submodules:

```powershell
git submodule update --init --recursive
```

The plugin reads game state through RetroArch's read-only network command interface. It does not include a Pokemon Emerald ROM. The pinned `pret/pokeemerald` checkout under `decomp_reference/pokeemerald` supplies structural data used by the adapter.

## Features

The main rail is divided into Area, Party, and Goals views. Urgent battle, missable, Feebas, and roaming-Pokemon notices remain visible regardless of the selected view.

### Area

- Wild species, levels, encounter rates, and caught status for land, water, Rock Smash, and each fishing rod.
- Route trainers, visible and hidden items, nearby objectives, ready rematches, and player-relative item ordering.
- Gym and Trick House missable alerts.
- Route 119 Feebas tile planning everywhere on the route, promoted to an alert when the facing tile is active.
- Base solo experience estimates and the best training areas observed in the current playthrough.
- A repel planner: with a repel active it lists which species can still appear at the lead Pokémon's level; without one it shows what the current lead would isolate.
- Persistent hunt statistics per playthrough: encounters this session plus lifetime seen/caught/KO/fled counts per species, classified from observable battle outcomes.

### Party and Battle

- Clickable party inspection with HP, status, nature, Gen III ability, held item, friendship, original/traded status, moves, PP, EVs, IVs, and Pokerus.
- Wild catch probabilities for every carried supported ball, live against current HP and status, with the best ball marked and a hint for what sleep would add.
- Wild Pokémon IV readouts with an upgrade verdict against the best party or
	boxed Pokémon in the same evolution line. All 14 live PC boxes are decoded
	once per wild encounter; invalid checksums are ignored and unavailable storage
	falls back to a labeled party-only comparison.
- Gen III integer damage estimates for the best party move against each opponent and the worst incoming threat, using live stats and stat stages.
- A Pickup dashboard that lists holders and reports freshly picked-up items.
- Switch-aware experience participation across a battle.
- Projected per-member experience including Exp. Share, Lucky Egg, trainer-battle, and traded-Pokemon modifiers in the game's integer operation order.
- Projected EV gains including Exp. Share recipients, Pokerus, Macho Brace, per-stat limits, and the 510 total limit.
- Type-based battle advice using current party moves and the actual loaded enemy party.
- Clickable complete opponent rosters from runtime memory. This reads generated Battle Frontier and Battle Pyramid teams after the game creates them instead of trying to predict facility RNG.

### Goals

- RetroAchievements account progress and nearby curated achievements.
- Professor Oak Challenge gate order and counts: Roxanne 39, Wattson 66, Flannery 90, Brawly 101, Norman 101, Tate and Liza 156, Juan 167, Winona 171, and final 212.
- A generated acquisition guide ranked by current progression and location.
- A completion- and map-proximity-aware main-story/sidequest navigator.
- A vanilla solo-play legendary dashboard for Rayquaza, Groudon, Kyogre, Regirock, Regice, Registeel, and the chosen roaming Latios or Latias. Event-ticket species are intentionally excluded.
- Berry-tree stages, timers, watering, mass outbreaks, Mirage Island party match, Lilycove lottery number, Shoal Cave tide, and daily reward state.
- Contest conditions, sheen, named ribbons, Feebas's 170 Beauty target, and complete Pokeblock flavor/feel details.
- Daycare deposits, projected levels, exact compatibility category, pending egg state, and party egg-cycle estimates with Flame Body/Magma Armor support.
- Battle Frontier BP, all symbols, Level 50/Open Level streaks, active facility/challenge, selected slots, Factory rentals, and Pyramid floor/trainer/bag/light state.
- Battle Factory rental details (species, moves, item, nature, IVs from the rental records) and swap advice scored by type coverage against shared weaknesses, using the decomp's facility Pokémon table.
- A region-wide Match Call dashboard listing every ready rematch and where it is.
- A per-playthrough session journal: catches, level-ups, evolutions, badges, symbols, and Pickup finds, kept as JSONL with a Markdown copy under the plugin state directory.
- Collection totals for HMs, flutes, berries, Secret Base furniture, dolls, and placed decorations.

## Accuracy Boundaries

- The Professor Oak Challenge gate counts and order are the plugin's RA-aligned rules. The acquisition list is generated from the pinned decomp's encounters, gifts, static battles, and non-trade evolutions; it is guidance, not a reproduction of private RetroAchievements trigger definitions.
- Route experience is labeled `base solo XP`. The party-to-next-level projection uses the current map's land, water (surfing or diving), or fishing table based on the live player avatar; fishing stays selected between casts until the player leaves that tile. Maps without encounters for that activity fall back to the best area seen. Per-Pokemon Lucky Egg, traded, and passive Exp. Share adjustments are estimates for repeated encounters. Live battle rewards use observed participants and the exact Gen III split/bonus order.
- Battle advice uses the Gen III integer damage formula with live stats, stat stages, burn, STAB, and the type chart, and shows the 85-100% roll spread. It does not model abilities, held items, screens, weather, crits, or AI choices.
- Hunt outcome classification is observational: a catch that goes straight to a PC box for an already-registered species cannot be distinguished from an escape and counts as fled.
- Factory swap advice scores type coverage and shared weaknesses only; rental abilities and movesets beyond typing are not simulated.
- Opponent teams come from runtime memory. A trainer or Frontier opponent is not exposed until the game has generated and loaded that roster.
- RTC details report save-backed world-event state. `Last processed` is the last game time-event update, not a direct read of the host hardware clock.
- Egg steps are an upper-bound estimate from remaining cycles and the shared step counter.

## Generated Knowledge

Runtime construction loads `game/data/emerald_knowledge.json`. It contains versioned indexes generated from the exact pinned decomp revision: maps and connections, encounters, species mechanics, items, moves, trainers, route completion, static acquisitions, evolution edges, Feebas tiles, the Gen III type chart, and the Battle Frontier facility Pokémon table used to decode Factory rentals.

Regenerate and verify it after intentionally updating the pinned decomp:

```powershell
python tools\generate_knowledge.py
python tools\generate_knowledge.py --check
```

The generator is deterministic. CI fails when the checked-in artifact is stale or generated from a different recorded revision.

## Local State

Best training areas, hunt statistics (`hunt-<trainer>.json`), the session journal (`journal-<trainer>.jsonl` plus a Markdown copy), and rendered species icons are cached per player Trainer ID under `%LOCALAPPDATA%/RetroArchOverlay/plugin-state/org.jeschete.retroarch-overlay.pokeemerald/`. A second save no longer inherits routes observed by another playthrough.

Optional feature reads are isolated. If one memory region is temporarily unavailable, its section reports the failure while location, encounter, and other independent sections continue updating. Full tracebacks are available in the host rotating log.

## Troubleshooting

- Enable RetroArch's network command interface and use the configured UDP port, normally `55355`.
- If the plugin reports an incomplete source, run `git submodule update --init --recursive` in this repository.
- If the generated artifact is stale, confirm the submodule is at the revision in `plugin.toml`, then run the generator commands above.
- If party or facility data appears unavailable during a transition, wait for the next stable snapshot. Save block pointers and active content are checked before and after each document to reject mixed state.
- Use the host log at `%LOCALAPPDATA%/RetroArchOverlay/logs/retroarch-overlay.log` for plugin load, polling, and feature tracebacks.

## Qt host integration

The plugin is UI-toolkit neutral and emits immutable keyed panel and map
documents. The default PySide6 host preserves expanded details and native widget
identity across live value updates, provides Area, Party, Goals, and Urgent
views, and renders the same route, city, indoor, cave, underwater, and Hoenn map
layers.

Generated map and species-icon PNGs are committed with atomic replacement. Their
cache directories are keyed by the pinned decomp revision and renderer source,
so renderer changes cannot silently reuse stale images. The in-memory species
icon path cache is LRU-bounded to 128 entries.

Locally authored plugin code is available under the MIT License. That license does not cover the decomp reference, game assets, patches, or trademarks; see the provenance report for their separate status.

## Test

From a checkout nested under `RetroArchOverlay/plugins`:

```powershell
$env:PYTHONPATH = "..\..\src;."
..\..\.venv\Scripts\python.exe -m pytest -q tests
..\..\.venv\Scripts\python.exe tools\generate_knowledge.py --check
```

See [RIGHTS_AND_PROVENANCE.md](RIGHTS_AND_PROVENANCE.md) before redistributing this repository.

The Qt migration acceptance suite currently passes 171 tests plus 61 subtests.
