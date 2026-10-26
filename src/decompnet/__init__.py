"""DecompNet: collaborative matching decompilation for AI agents."""

import sys

__version__ = "0.10.34"

# Where this build of Function_2_C_Decompiler comes from and is installed from, and the project it is a maintained fork of. What the app
# writes into other people's projects (READMEs, build scripts) links the first; the second is a credit.
HOME_URL = "https://github.com/FlyPhantomFly/Function_2_C_Decompiler"
PRODUCT = "Function_2_C_Decompiler"  # the name people see; the package stays `decompnet` and the command `decomp` (see ARCHITECTURE, "Names")
# The identity of commits the app makes when git has none set up. `.invalid` can never resolve (RFC 2606), so no address at a
# domain this project does not own ends up in anyone's history.
NOREPLY_EMAIL = "noreply@function-2-c-decompiler.invalid"
UPSTREAM_URL = "https://github.com/i12bp8/decomp.wtf"


def utf8_output() -> None:
    """Windows: output into a pipe or file is written in the ANSI code page there, where printing a "→" or a user name
    with letters outside it crashes. Write UTF-8 instead (a console window shows everything anyway)."""
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if stream is not None and not stream.isatty():
                stream.reconfigure(encoding="utf-8", errors="replace")


if sys.platform == "win32":
    # Python only trusts the root certificates Windows has already cached, and Windows fetches the others the first
    # time a browser needs them: downloads from some hosts (developer.arm.com) fail with CERTIFICATE_VERIFY_FAILED.
    # Verify through Windows itself instead, like every other program there does.
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass
