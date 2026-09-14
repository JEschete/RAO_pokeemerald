"""Region-wide Match Call rematch dashboard.

The save keeps one readiness byte per REMATCH table entry; the knowledge file
maps each entry to its trainer name and (normalized) map. This dashboard
lists every ready rematch across Hoenn, not just the ones on the current map.
"""

import re

from retroarch_overlay.models import PanelAction, PanelRow, PanelSection


def _display_map(normalized: str) -> str:
    spaced = re.sub(
        r"(?<=[A-Z0-9])(?=[A-Z][a-z])|(?<=[a-z])(?=[A-Z0-9])",
        " ",
        normalized.title(),
    ).replace("_", " ")
    return re.sub(r"\s+", " ", spaced).strip()


class MatchCallDashboard:
    def __init__(
        self, rematches_by_map: dict[str, tuple[tuple[int, str], ...]]
    ) -> None:
        # Flatten to (rematch index, trainer name, display map).
        self._entries = tuple(
            (index, name, _display_map(map_name))
            for map_name, rows in sorted(rematches_by_map.items())
            for index, name in rows
        )

    def ready_rematches(
        self, rematch_bytes: bytes
    ) -> tuple[tuple[str, str], ...]:
        return tuple(
            (name, map_label)
            for index, name, map_label in self._entries
            if index < len(rematch_bytes) and rematch_bytes[index]
        )

    def section(self, rematch_bytes: bytes) -> PanelSection | None:
        ready = self.ready_rematches(rematch_bytes)
        if not ready:
            return None
        rows = tuple(
            PanelRow(f"{name} · {map_label}") for name, map_label in ready
        )
        details = (PanelRow("READY REMATCHES"),) + rows
        return PanelSection(
            f"Match Call · {len(ready)} ready",
            rows,
            preview_limit=3,
            actions=(
                PanelAction(
                    "OPEN MATCH CALL",
                    "Ready Rematches",
                    details,
                    key="match-call-details",
                ),
            ),
            priority=42,
            role="goals",
            compact_rows=(PanelRow(f"{len(ready)} rematches ready"),),
            key="match-call",
        )
