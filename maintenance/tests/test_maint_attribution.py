"""Credit and metadata: the MIT notice must stay with the code, and this fork's maintainer is named next to it."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_license_keeps_upstreams_notice_and_adds_the_maintainers():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License\n")
    assert "Copyright (c) 2026 Sam Wolfs" in text  # the MIT condition: the original notice stays
    assert "Copyright (c) 2026 PhantomThreads" in text
    assert text.index("Sam Wolfs") < text.index("PhantomThreads")
    assert "Permission is hereby granted, free of charge" in text and "THE SOFTWARE IS PROVIDED \"AS IS\"" in text


def test_the_package_metadata_names_the_original_author_and_the_maintainer():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert any("wolfs" in a["name"].lower() for a in project["authors"])
    assert {"name": "PhantomThreads"} in project["maintainers"]
    assert project["license"] == "MIT"


def test_the_package_links_point_at_this_fork_and_credit_upstream_without_using_its_site():
    urls = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["urls"]
    assert urls["Homepage"] == urls["Source"] == "https://github.com/FlyPhantomFly/Function_2_C_Decompiler"
    assert urls["Upstream"] == "https://github.com/i12bp8/decomp.wtf"  # credit, not a download
    assert not any("decomp.wtf" in v and "github.com/i12bp8" not in v for v in urls.values())
