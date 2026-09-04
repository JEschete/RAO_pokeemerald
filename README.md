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

### Party and Battle

- Clickable party inspection with HP, status, nature, Gen III ability, held item, friendship, original/traded status, moves, PP, EVs, IVs, and Pokerus.
- Wild catch probabilities for every carried supported ball.
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
- Collection totals for HMs, flutes, berries, Secret Base furniture, dolls, and placed decorations.

## Accuracy Boundaries

- The Professor Oak Challenge gate counts and order are the plugin's RA-aligned rules. The acquisition list is generated from the pinned decomp's encounters, gifts, static battles, and non-trade evolutions; it is guidance, not a reproduction of private RetroAchievements trigger definitions.
- Route experience is labeled `base solo XP`. Per-Pokemon Lucky Egg, traded, and passive Exp. Share adjustments are estimates for repeated encounters. Live battle rewards use observed participants and the exact Gen III split/bonus order.
- Battle advice is explicitly type-based. It does not claim a complete damage simulation for abilities, AI choices, random damage rolls, or every temporary field effect.
- Opponent teams come from runtime memory. A trainer or Frontier opponent is not exposed until the game has generated and loaded that roster.
- RTC details report save-backed world-event state. `Last processed` is the last game time-event update, not a direct read of the host hardware clock.
- Egg steps are an upper-bound estimate from remaining cycles and the shared step counter.

## Generated Knowledge

Runtime construction loads `game/data/emerald_knowledge.json`. It contains versioned indexes generated from the exact pinned decomp revision: maps and connections, encounters, species mechanics, items, moves, trainers, route completion, static acquisitions, evolution edges, Feebas tiles, and the Gen III type chart.

Regenerate and verify it after intentionally updating the pinned decomp:

```powershell
python tools\generate_knowledge.py
python tools\generate_knowledge.py --check
```

The generator is deterministic. CI fails when the checked-in artifact is stale or generated from a different recorded revision.

## Local State

Best training areas are cached per player Trainer ID under `%LOCALAPPDATA%/RetroArchOverlay/plugin-state/org.jeschete.retroarch-overlay.pokeemerald/`. A second save no longer inherits routes observed by another playthrough.

Optional feature reads are isolated. If one memory region is temporarily unavailable, its section reports the failure while location, encounter, and other independent sections continue updating. Full tracebacks are available in the host rotating log.

## Troubleshooting

- Enable RetroArch's network command interface and use the configured UDP port, normally `55355`.
- If the plugin reports an incomplete source, run `git submodule update --init --recursive` in this repository.
- If the generated artifact is stale, confirm the submodule is at the revision in `plugin.toml`, then run the generator commands above.
- If party or facility data appears unavailable during a transition, wait for the next stable snapshot. Save block pointers and active content are checked before and after each document to reject mixed state.
- Use the host log at `%LOCALAPPDATA%/RetroArchOverlay/logs/retroarch-overlay.log` for plugin load, polling, and feature tracebacks.

Locally authored plugin code is available under the MIT License. That license does not cover the decomp reference, game assets, patches, or trademarks; see the provenance report for their separate status.

## Test

From a checkout nested under `RetroArchOverlay/plugins`:

```powershell
$env:PYTHONPATH = "..\..\src;."
..\..\.venv\Scripts\python.exe -m pytest -q tests
..\..\.venv\Scripts\python.exe tools\generate_knowledge.py --check
```

See [RIGHTS_AND_PROVENANCE.md](RIGHTS_AND_PROVENANCE.md) before redistributing this repository.
