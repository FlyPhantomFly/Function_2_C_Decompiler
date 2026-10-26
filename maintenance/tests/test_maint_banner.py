"""The README banner: made for this project, from a source that can be edited, and kept in step with the README.

It used to be upstream's artwork (the old wordmark and its tagline). The new one is rendered from `maintenance/assets/banner.html` by `maintenance/tools/make_banner.py`. These tests
check the files are what the README promises (right size, both themes, not the old art), that the picture is wired the way the README's `<picture>` expects, and that the tagline in
the source and the README's alt text say the same thing, since an image's words are invisible to anyone using a screen reader and the alt text is all they get.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import struct
import sys
from pathlib import Path

import pytest

import decompnet

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / ".github" / "assets"
SOURCE = ROOT / "maintenance" / "assets" / "banner.html"
UPSTREAM_BANNER_SHA256 = {  # upstream 0.10.6's own banners, from the untouched tag: the new ones must not be these
    "banner-light.png": "649ccce12cb59993a2f466f3a98d5a9a808081f9c5a8732449d85a6e94a0e04c",
    "banner-dark.png": "d66d766be3f7f7aa95e720c32fe4dc7768222d95bcd1bb1c8b3cd0361105d1cc",
}


def _tool():
    spec = importlib.util.spec_from_file_location("make_banner", ROOT / "maintenance" / "tools" / "make_banner.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = _tool()
README = (ROOT / "README.md").read_text(encoding="utf-8")


def png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", head[16:24])


@pytest.mark.parametrize("name", ["banner-light.png", "banner-dark.png"])
def test_each_banner_is_a_png_at_twice_the_designed_size_and_light_enough_for_a_readme(name):
    assert png_size(ASSETS / name) == (2560, 800)
    assert (ASSETS / name).stat().st_size < 600 * 1024


@pytest.mark.parametrize("name", ["banner-light.png", "banner-dark.png"])
def test_it_is_not_upstreams_artwork(name):
    assert hashlib.sha256((ASSETS / name).read_bytes()).hexdigest() != UPSTREAM_BANNER_SHA256[name]


def test_the_readme_serves_the_dark_banner_to_dark_mode_and_the_light_one_otherwise():
    picture = README[README.index("<picture>"): README.index("</picture>")]
    assert 'media="(prefers-color-scheme: dark)" srcset=".github/assets/banner-dark.png"' in picture
    assert 'src=".github/assets/banner-light.png"' in picture


def test_the_alt_text_is_the_product_name_and_the_banners_own_tagline_and_not_the_old_one():
    picture = README[README.index("<picture>"): README.index("</picture>")]
    alt = re.search(r'alt="([^"]+)"', picture).group(1)
    tagline = re.sub(r"\s+", " ", re.search(r'<p class="tag">(.*?)</p>', SOURCE.read_text(encoding="utf-8"), re.S).group(1)).strip()
    assert alt == f"{decompnet.PRODUCT}. {tagline}"
    assert "What the function" not in alt and "decomp.wtf" not in alt


def test_the_source_spells_the_product_name_as_the_app_does_and_never_the_original_name():
    html = SOURCE.read_text(encoding="utf-8")
    assert f"<title>{decompnet.PRODUCT}</title>" in html
    assert '<h1><span>Function_2_C_</span><span class="g">Decompiler</span></h1>' in html  # the app's own two-tone wordmark
    assert "decomp.wtf" not in html


def test_the_fonts_the_source_loads_exist_and_are_the_apps_own():
    html = SOURCE.read_text(encoding="utf-8")
    urls = re.findall(r'url\("([^"]+\.woff2)"\)', html)
    assert len(urls) == 2
    for url in urls:
        assert (SOURCE.parent / url).resolve().exists(), url
        assert "src/decompnet/app/static/fonts/" in url


def test_the_palette_is_the_apps_palette():
    css = (ROOT / "src" / "decompnet" / "app" / "static" / "app.css").read_text(encoding="utf-8")
    html = SOURCE.read_text(encoding="utf-8")
    for token in ("#f4f2ec", "#157a49", "#0d0d0b", "#4fcf8c", "#14130f"):  # paper, match green, dark paper, dark match green, ink
        assert token in css and token in html, token


def test_the_render_command_draws_at_the_designed_size_at_twice_the_scale_and_picks_the_theme_from_the_url(tmp_path):
    dark = tool.render_command("/x/chrome", "dark", tmp_path / "d.png")
    light = tool.render_command("/x/chrome", "light", tmp_path / "l.png")
    for cmd in (dark, light):
        assert "--window-size=1280,400" in cmd and "--force-device-scale-factor=2" in cmd and "--headless=new" in cmd
    assert dark[-1].endswith("banner.html#dark") and light[-1].endswith("banner.html")


def test_it_refuses_politely_without_a_browser(monkeypatch, capsys):
    monkeypatch.delenv("CHROME", raising=False)
    assert tool.main([]) == 2 and "set CHROME" in capsys.readouterr().err


@pytest.mark.skipif(not os.environ.get("CHROME") or not Path(os.environ.get("CHROME", "")).exists(), reason="needs CHROME=<a Chromium binary>")
def test_rendering_the_source_for_real_gives_both_banners_at_the_expected_size(tmp_path):
    assert tool.main([str(tmp_path)]) == 0
    assert png_size(tmp_path / "banner-light.png") == png_size(tmp_path / "banner-dark.png") == (2560, 800)
