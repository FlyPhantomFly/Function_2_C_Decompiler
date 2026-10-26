# GUI screenshots

`desktop.png` (1280x800) and `phone.png` (420x860): the app's first screen, as of the version in `maintenance/CHANGELOG.md` they were made for
(0.10.37), written by `maintenance/tools/screenshot_ui.py` with a headless Chromium. They exist to show that the product name **Function_2_C_Decompiler**
(23 characters, where the old name had 10) fits the 248 px sidebar and the narrow-screen header. Regenerate them after a UI change and look at them:

    CHROME=/path/to/chrome python3 maintenance/tools/screenshot_ui.py

The browser used was the portable `ungoogled-chromium` 155.0.8059.84-1 (x86_64) from GitHub releases, run only on the app's own localhost page; the file's
sha256 was compared with the digest GitHub shows for the release asset before it was run.
