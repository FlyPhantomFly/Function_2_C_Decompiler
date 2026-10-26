# Assets

`banner.html` is the source of the README banner (`.github/assets/banner-light.png` and `banner-dark.png`). It is drawn at 1280 x 400 CSS pixels, with the app's own colors and fonts (Geist and Geist Mono,
SIL OFL, from `src/decompnet/app/static/`), and rendered at 2x. To change the banner, edit it and run:

    CHROME=/path/to/chromium python3 maintenance/tools/make_banner.py

then look at both PNGs before committing (`maintenance/tools/screenshot_ui.py` says where to get a headless Chromium). The tagline in `banner.html` and the README's `alt` text for the banner must say the same thing
(`test_maint_banner.py` checks). The code in the card is the demo ROM's `player_take_damage`; the demo is CC0.

`.github/assets/demo.webp` is a scripted playback recorded from a page on the original project's website, which is not in this repository, so it cannot be regenerated; only its title bar was repainted, by `maintenance/tools/repaint_demo_title.py` (it needs Chromium, Pillow and numpy; the docstring has the command). The title still ends with "Demo Quest 64" while the code shown is zlib's: it is an illustration of the interface, not a recording of one run.

Not covered here: `how-light.png` / `how-dark.png`, the diagram under "How it works" (it carries no product name).
