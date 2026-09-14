import ast
from pathlib import Path

from game.adapter import BATTLE_MON_SIZE, POKEMON_SIZE, EmeraldAdapter
from game.feebas import feebas_spot_ids
from retroarch_overlay.core.contracts import GameContext
from retroarch_overlay.core.retroachievements import RAProgress
from retroarch_overlay.infrastructure.plugin_discovery import (
    DiscoveredPluginRepository,
    parse_plugin_manifest,
)
from retroarch_overlay.infrastructure.plugin_loader import RepositoryAdapter
from retroarch_overlay.presentation.qt import (
    PanelDocumentUpdate,
    PanelDocumentView,
    QtMapView,
)

from test_emerald import FakeMemory, POKEEMERALD_ROOT


ROOT = Path(__file__).resolve().parents[1]


def _loaded_adapter(
    tmp_path: Path,
    progress: RAProgress | None = None,
) -> EmeraldAdapter:
    repository = DiscoveredPluginRepository(ROOT, parse_plugin_manifest(ROOT))
    return RepositoryAdapter(
        repository,
        GameContext(
            repository_root=ROOT,
            state_directory=tmp_path,
            ra_progress_provider=(lambda _game_id: progress) if progress else None,
        ),
    )._load_adapter()


def _party_mon(
    adapter: EmeraldAdapter,
    *,
    hp: int = 10,
    level: int = 12,
) -> bytes:
    personality = 0
    trainer_id = 0x12345678
    secure = bytearray(48)
    secure[0:2] = adapter._species_ids["SPECIES_TREECKO"].to_bytes(2, "little")
    secure[4:8] = (1_000).to_bytes(4, "little")
    checksum = sum(
        int.from_bytes(secure[offset : offset + 2], "little")
        for offset in range(0, len(secure), 2)
    ) & 0xFFFF
    encrypted = b"".join(
        (int.from_bytes(secure[offset : offset + 4], "little") ^ trainer_id).to_bytes(
            4,
            "little",
        )
        for offset in range(0, len(secure), 4)
    )
    pokemon = bytearray(POKEMON_SIZE)
    pokemon[4:8] = trainer_id.to_bytes(4, "little")
    pokemon[0x1C:0x1E] = checksum.to_bytes(2, "little")
    pokemon[0x20:0x50] = encrypted
    pokemon[0x54] = level
    pokemon[0x56:0x58] = hp.to_bytes(2, "little")
    pokemon[0x58:0x5A] = (10).to_bytes(2, "little")
    return bytes(pokemon)


def _wild_battle_mons(adapter: EmeraldAdapter) -> bytes:
    battle_mons = bytearray(BATTLE_MON_SIZE * 2)
    offset = BATTLE_MON_SIZE
    species_id = adapter._species_ids["SPECIES_ZIGZAGOON"]
    battle_mons[offset : offset + 2] = species_id.to_bytes(2, "little")
    battle_mons[offset + 0x28 : offset + 0x2A] = (5).to_bytes(2, "little")
    battle_mons[offset + 0x2A] = 4
    battle_mons[offset + 0x2C : offset + 0x2E] = (12).to_bytes(2, "little")
    return bytes(battle_mons)


def test_every_panel_section_and_action_declares_a_stable_key() -> None:
    missing = []
    constructors = 0
    for path in sorted((ROOT / "game").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in {"PanelSection", "PanelAction"}:
                continue
            constructors += 1
            if not any(keyword.arg == "key" for keyword in node.keywords):
                missing.append((path.name, node.func.id, node.lineno))

    assert constructors > 0
    assert missing == []


def test_overworld_snapshot_has_unique_shared_qt_roles_and_identities() -> None:
    adapter = EmeraldAdapter(POKEEMERALD_ROOT)
    memory = FakeMemory(
        *adapter.map_ids["MAP_ROUTE101"],
        party=_party_mon(adapter),
    )

    snapshot = adapter.snapshot(memory)

    section_keys = [section.key for section in snapshot.sections]
    assert len(section_keys) == len(set(section_keys))
    assert all(section_keys)
    assert all(
        action.key
        for section in snapshot.sections
        for action in section.actions
    )
    assert {section.role for section in snapshot.sections} <= {
        "area",
        "party",
        "goals",
        "urgent",
    }
    assert {section.key for section in snapshot.sections if section.role == "party"} >= {
        "party",
    }


def test_party_details_remain_expanded_across_live_value_updates(qtbot) -> None:
    adapter = EmeraldAdapter(POKEEMERALD_ROOT)
    memory = FakeMemory(
        *adapter.map_ids["MAP_ROUTE101"],
        party=_party_mon(adapter),
    )
    view = PanelDocumentView()
    view.resize(460, 780)
    qtbot.addWidget(view)
    view.show()
    view.set_snapshot(adapter.snapshot(memory), content_scope="emerald-test-rom")
    view.set_active_role("party")

    party = next(
        section for section in view.state.section_views if section.section.key == "party"
    )
    party_widget = view.section_widget(party.identity)
    assert party_widget is not None
    action_widget = party_widget.action_widget(party.actions[0].identity)
    assert action_widget is not None
    action_widget.toggle_button.click()

    memory.party = _party_mon(adapter, hp=6)
    update = view.set_snapshot(
        adapter.snapshot(memory),
        content_scope="emerald-test-rom",
    )
    updated_party = next(
        section for section in view.state.section_views if section.section.key == "party"
    )

    assert update == PanelDocumentUpdate.VALUES
    assert view.section_widget(updated_party.identity) is party_widget
    assert updated_party.actions[0].expanded
    assert "HP 6/10" in updated_party.rows[0].text


def test_wild_battle_snapshot_materializes_only_keyed_urgent_sections(qtbot) -> None:
    adapter = EmeraldAdapter(POKEEMERALD_ROOT)
    memory = FakeMemory(
        *adapter.map_ids["MAP_ROUTE101"],
        battle_mons=_wild_battle_mons(adapter),
        party=_party_mon(adapter),
        balls={4: 5},
    )
    snapshot = adapter.snapshot(memory)
    view = PanelDocumentView()
    qtbot.addWidget(view)
    view.show()

    view.set_snapshot(snapshot, content_scope="emerald-battle")

    keys = [section.section.key for section in view.state.section_views]
    assert keys[0] == "battle"
    assert "wild-ivs" in keys
    assert "catch-chances-0" in keys
    assert len(keys) == len(set(keys))
    assert all(section.section.role == "urgent" for section in view.state.section_views)
    assert all(
        view.section_widget(section.identity) is not None
        for section in view.state.section_views
    )


def test_title_screen_snapshot_has_stable_status_identity(qtbot) -> None:
    adapter = EmeraldAdapter(POKEEMERALD_ROOT)
    memory = FakeMemory(0, 0)
    memory.save_block_1 = 0
    snapshot = adapter.snapshot(memory)
    view = PanelDocumentView()
    qtbot.addWidget(view)

    view.set_snapshot(snapshot, content_scope="emerald-title")

    assert [section.section.key for section in view.state.section_views] == ["status"]
    assert view.state.section_views[0].section.role == "goals"


def test_real_route_and_hoenn_maps_render_through_qt(
    qtbot,
    tmp_path: Path,
) -> None:
    adapter = _loaded_adapter(tmp_path)
    memory = FakeMemory(
        *adapter.map_ids["MAP_ROUTE119"],
        player_position=(5, 5),
        feebas_position=bytes(9),
    )

    snapshot = adapter.snapshot(memory)
    assert snapshot.map_document is not None
    assert snapshot.map_position is not None
    view = QtMapView(snapshot.map_document)
    qtbot.addWidget(view)
    view.show()
    view.update_map(snapshot.map_position, snapshot.map_overlays)
    for kind in view.available_overlay_kinds:
        view.set_overlay_visible(kind, True)

    assert view.layer_key == "route119"
    assert view.image_item_count == 1
    assert view.player_scene_positions == ((88.0, 88.0),)
    assert view.visible_waypoints()
    route_layer = next(
        layer for layer in snapshot.map_document.layers if layer.key == "route119"
    )
    assert route_layer.image_path.is_file()
    assert route_layer.image_path.is_relative_to(tmp_path / "generated-assets")

    assert view.set_layer("hoenn")
    assert view.layer_key == "hoenn"
    assert view.image_item_count == 1
    hoenn_layer = next(
        layer for layer in snapshot.map_document.layers if layer.key == "hoenn"
    )
    assert hoenn_layer.image_path.is_file()
    assert hoenn_layer.image_path.parent == route_layer.image_path.parent


def test_representative_map_families_switch_and_render_in_one_qt_view(
    qtbot,
    tmp_path: Path,
) -> None:
    adapter = _loaded_adapter(tmp_path)
    assert adapter._map_catalog is not None
    entries = {
        entry.map_id: entry
        for entry in adapter._map_catalog.entries
    }
    map_ids = (
        "MAP_ROUTE101",
        "MAP_PETALBURG_CITY",
        "MAP_LITTLEROOT_TOWN_BRENDANS_HOUSE_1F",
        "MAP_METEOR_FALLS_1F_1R",
        "MAP_UNDERWATER_ROUTE124",
    )
    first = entries[map_ids[0]]
    snapshot = adapter.snapshot(
        FakeMemory(first.group, first.number, player_position=(1, 1))
    )
    assert snapshot.map_document is not None
    view = QtMapView(snapshot.map_document)
    qtbot.addWidget(view)
    view.show()

    rendered = []
    for map_id in map_ids:
        entry = entries[map_id]
        snapshot = adapter.snapshot(
            FakeMemory(entry.group, entry.number, player_position=(1, 1))
        )
        assert snapshot.map_position is not None
        view.update_map(snapshot.map_position, snapshot.map_overlays)
        assert view.layer_key == entry.key
        assert view.image_item_count == 1
        assert view.player_scene_positions == ((24.0, 24.0),)
        layer = next(
            layer for layer in snapshot.map_document.layers if layer.key == entry.key
        )
        assert layer.image_path.is_file()
        rendered.append(layer.key)

    assert len(rendered) == len(set(rendered)) == 5


def test_dense_route_snapshot_materializes_every_qt_role_and_action(
    qtbot,
    tmp_path: Path,
) -> None:
    adapter = _loaded_adapter(
        tmp_path,
        RAProgress("EmeraldTester", frozenset()),
    )
    map_group, map_number = adapter.map_ids["MAP_ROUTE119"]
    seed = 12345
    spot = feebas_spot_ids(seed)[0]
    target_x, target_y = next(
        coordinates
        for coordinates, candidate in adapter._route119_fishing_spots.items()
        if candidate == spot
    )
    position = bytearray(9)
    position[0:2] = (target_x + 7).to_bytes(2, "little")
    position[2:4] = (target_y + 8).to_bytes(2, "little")
    position[8] = 2
    snapshot = adapter.snapshot(
        FakeMemory(
            map_group,
            map_number,
            party=_party_mon(adapter),
            feebas_position=bytes(position),
            feebas_seed=seed,
        )
    )
    view = PanelDocumentView()
    view.resize(360, 720)
    qtbot.addWidget(view)
    view.show()
    view.set_snapshot(snapshot, content_scope="emerald-dense")

    assert len(snapshot.sections) >= 15
    assert {section.role for section in snapshot.sections} == {
        "area",
        "party",
        "goals",
        "urgent",
    }
    party = next(section for section in snapshot.sections if section.key == "party")
    assert party.rows[0].icon
    assert Path(party.rows[0].icon).is_file()
    assert Path(party.rows[0].icon).is_relative_to(tmp_path / "generated-assets")
    for role in ("area", "party", "goals", "urgent"):
        view.set_active_role(role)
        assert view.state.section_views
        for section in view.state.section_views:
            widget = view.section_widget(section.identity)
            assert widget is not None
            for action in section.actions:
                assert widget.action_widget(action.identity) is not None
    view.resize(900, 800)