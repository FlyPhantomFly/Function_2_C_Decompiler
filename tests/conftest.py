import os
import shutil

# the apps the tests start never look for updates on the network (tests/test_updates.py checks that part offline)
os.environ.setdefault("DECOMP_UPDATES", "off")

# Agent-written C only compiles inside bubblewrap. A machine without it would error in every test that compiles demo
# code, so there those tests run unsandboxed (the sandbox rules have their own tests in maintenance/tests/test_maint_sandbox.py,
# which don't depend on this) and the run header says so.
NO_SANDBOX = shutil.which("bwrap") is None
if NO_SANDBOX:
    os.environ.setdefault("DECOMP_UNSAFE_NO_SANDBOX", "1")


def pytest_report_header(config):
    if NO_SANDBOX and os.environ.get("DECOMP_UNSAFE_NO_SANDBOX") == "1":
        return "bubblewrap not found: tests that compile demo code run WITHOUT the sandbox (DECOMP_UNSAFE_NO_SANDBOX=1)"
