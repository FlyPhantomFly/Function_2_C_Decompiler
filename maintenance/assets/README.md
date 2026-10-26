# Assets

`banner.html` is the source of the README banner (`.github/assets/banner-light.png` and `banner-dark.png`). It is drawn at 1280 x 400 CSS pixels, with the app's own colors and fonts (Geist and Geist Mono,
SIL OFL, from `src/decompnet/app/static/`), and rendered at 2x. To change the banner, edit it and run:

    CHROME=/path/to/chromium python3 maintenance/tools/make_banner.py

then look at both PNGs before committing (`maintenance/tools/screenshot_ui.py` says where to get a headless Chromium). The tagline in `banner.html` and the README's `alt` text for the banner must say the same thing
(`test_maint_banner.py` checks). The code in the card is the demo ROM's `player_take_damage`; the demo is CC0.

Not covered here: `.github/assets/demo.webp`, an animation recorded from the app, and `how-light.png` / `how-dark.png`, the diagram under "How it works" (it carries no product name).
