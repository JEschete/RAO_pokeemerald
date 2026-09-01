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

The plugin reads game state through RetroArch's read-only network command interface. It does not include a Pokemon Emerald ROM. The pinned `pret/pokeemerald` checkout under `vendor/pokeemerald` supplies structural data used by the adapter.

## Test

From a checkout nested under `RetroArchOverlay/plugins`:

```powershell
$env:PYTHONPATH = "..\..\src;."
..\..\.venv\Scripts\python.exe -m pytest -q tests
```

See [RIGHTS_AND_PROVENANCE.md](RIGHTS_AND_PROVENANCE.md) before redistributing this repository.
