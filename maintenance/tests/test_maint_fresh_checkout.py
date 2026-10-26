"""A fresh clone has no `projects/demo/target/`: the .o files are gitignored and git keeps no empty directories.

`import_project` used to run the project's `build` command without creating the directory its output goes in, so
every test (and a first import) on a fresh checkout died inside gcc with "can't create target/game.o". Found by the
0.10.7 baseline: 21 of the 23 non-passing items on a fresh checkout were this one bug.
"""

import shutil
import sys
from pathlib import Path

import pytest

from decompnet.network import Network
from decompnet.project import import_project

DEMO = Path(__file__).resolve().parents[2] / "projects" / "demo"
HOST_GCC = sys.platform != "win32" and shutil.which("gcc") is not None

pytestmark = pytest.mark.skipif(not HOST_GCC, reason="projects/demo needs a Linux gcc (x86-64 ELF)")


def _fresh_copy(tmp_path: Path) -> Path:
    """The demo project as git hands it out: sources only, no target/ directory."""
    root = tmp_path / "demo"
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns("target"))
    assert not (root / "target").exists()
    return root


def test_import_builds_the_target_objects_in_a_directory_that_does_not_exist_yet(tmp_path):
    root = _fresh_copy(tmp_path)
    net = Network(tmp_path / "test.db")
    import_project(net.store, root, log=lambda *_: None)
    assert (root / "target" / "game.o").stat().st_size > 0
    assert net.store.one("SELECT COUNT(*) AS n FROM functions")["n"] > 0  # and the functions were really read from it


def test_a_second_import_reuses_the_objects_without_rebuilding(tmp_path):
    root = _fresh_copy(tmp_path)
    net = Network(tmp_path / "test.db")
    import_project(net.store, root, log=lambda *_: None)
    built = (root / "target" / "game.o").stat().st_mtime_ns
    said = []
    import_project(net.store, root, log=said.append)
    assert (root / "target" / "game.o").stat().st_mtime_ns == built
    assert not any("building target objects" in line for line in said)
