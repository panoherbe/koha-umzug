from __future__ import annotations

import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL))


@pytest.fixture(scope="package")
def beispiel(tmp_path_factory):
    """The sample export built from the committed DNB data, and its conversion (once per test run)."""
    from daten import nachbilden
    from umzug.umwandeln import umwandeln

    tmp = tmp_path_factory.mktemp("beispiel")
    export, ziel = tmp / "export", tmp / "koha"
    nachbilden.main(["--ziel", str(export)])
    prot = umwandeln(export, ziel, WURZEL / "beispiel" / "freigaben.json", "http://opac", "http://dienst")
    return export, ziel, prot
