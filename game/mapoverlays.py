from hashlib import blake2b

from retroarch_overlay.models import MapOverlay, MapWaypoint

from .mapdata import (
    KIND_BERRY,
    KIND_FEEBAS,
    KIND_HIDDEN,
    KIND_ITEM,
    KIND_REMATCH,
    KIND_TRAINER,
    EmeraldMapCatalog,
    EmeraldMapEntry,
)


COMPLETED_TEXT = {
    KIND_TRAINER: ("Defeated", "Not yet battled"),
    KIND_REMATCH: ("Defeated - rematch available", "Not yet battled"),
    KIND_ITEM: ("Collected", "Still on the ground"),
    KIND_HIDDEN: ("Collected", "Still buried"),
}


def flag_is_set(flags: bytes, flag: int) -> bool:
    index = flag // 8
    if index >= len(flags):
        return False
    return bool(flags[index] & (1 << (flag % 8)))


def _waypoints(entry: EmeraldMapEntry, flags: bytes) -> tuple[MapWaypoint, ...]:
    waypoints = []
    for marker in entry.markers:
        if marker.flags:
            # A roll-up is only finished once everything inside it is.
            done = sum(1 for flag in marker.flags if flag_is_set(flags, flag))
            completed = done == len(marker.flags)
            status = f"{done} of {len(marker.flags)} collected"
        else:
            completed = marker.flag is not None and flag_is_set(flags, marker.flag)
            done_text, pending_text = COMPLETED_TEXT.get(marker.kind, ("", ""))
            status = done_text if completed else pending_text
        detail = marker.detail
        if status:
            detail = f"{status}\n{detail}" if detail else status
        waypoints.append(
            MapWaypoint(
                marker.x,
                marker.y,
                marker.title,
                detail,
                marker.kind,
                completed,
                marker.marker,
            )
        )
    return tuple(waypoints)


def feebas_waypoints(
    fishing_spots: dict[tuple[int, int], int], active: tuple[int, ...]
) -> tuple[MapWaypoint, ...]:
    """Route 119's six live Feebas tiles for the current trend seed."""
    wanted = set(active)
    return tuple(
        MapWaypoint(
            x,
            y,
            f"Feebas spot {spot}",
            "50% Feebas encounter while fishing this tile",
            KIND_FEEBAS,
            False,
            "shop",
        )
        for (x, y), spot in sorted(fishing_spots.items(), key=lambda item: item[1])
        if spot in wanted
    )


class EmeraldOverlayBuilder:
    """Turns live event flags into per-map marker overlays, cached per flag state."""

    def __init__(self, catalog: EmeraldMapCatalog) -> None:
        self._catalog = catalog
        self._digest = b""
        self._cached: tuple[MapOverlay, ...] = ()

    def overlays(
        self,
        flags: bytes,
        feebas: tuple[MapWaypoint, ...] = (),
        feebas_key: str = "",
    ) -> tuple[MapOverlay, ...]:
        digest = blake2b(flags, digest_size=16).digest()
        if digest != self._digest:
            self._digest = digest
            self._cached = tuple(
                MapOverlay(entry.key, _waypoints(entry, flags))
                for entry in self._catalog.entries
                if entry.markers
            )
        if not feebas or not feebas_key:
            return self._cached
        merged = []
        seen = False
        for overlay in self._cached:
            if overlay.layer_key == feebas_key:
                merged.append(
                    MapOverlay(overlay.layer_key, overlay.waypoints + feebas)
                )
                seen = True
            else:
                merged.append(overlay)
        if not seen:
            merged.append(MapOverlay(feebas_key, feebas))
        return tuple(merged)
