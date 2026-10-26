"""The pinned-download registry: its shape is guarded here, and the checker that finds dead links is tested offline.

Every compiler this app runs is downloaded from a third-party URL pinned by sha256 in `src/decompnet/toolchains.toml`.
Links rot, and `toolchains.install` will accept an entry with no hash and "pin it on first use", which would install
unverified code. So: the registry is checked for shape on every test run, and `check_toolchains.py` (run nightly in CI)
finds a dead URL or a changed file before a user does.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("check_toolchains", ROOT / "maintenance" / "tools" / "check_toolchains.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass looks its module up here
    spec.loader.exec_module(module)
    return module


tc = _load()
BODY = b"pretend this is a compiler archive\n"
GOOD_SHA = hashlib.sha256(BODY).hexdigest()


def test_every_download_in_the_real_registry_is_https_and_pinned_by_sha256():
    parts = tc.load_parts()
    assert len(parts) >= 60  # 62 when this was written: a parse that finds nothing must not pass
    assert tc.structural_problems(parts) == []


def test_an_unpinned_or_malformed_entry_is_reported():
    P = tc.Part
    bad = [P("a", "https://x.test/a.tar.gz", ""), P("b", "https://x.test/b.tar.gz", "ABC"),
           P("c", "http://x.test/c.tar.gz", GOOD_SHA), P("d", "https://x.test/d.tar.gz", "G" * 64),
           P("e", "https://x.test/e", GOOD_SHA), P("f", "https://x.test/e", "1" * 64)]
    problems = "\n".join(tc.structural_problems(bad))
    for needle in ("a:", "b:", "not https: http://x.test/c", "d:", "two different sha256"):
        assert needle in problems, (needle, problems)
    assert tc.structural_problems([P("ok", "https://x.test/ok", GOOD_SHA)]) == []


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, with_body: bool, body: bytes = BODY):
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if with_body:
            self.wfile.write(body)

    def do_HEAD(self):
        if self.path == "/head-refused":  # some hosts answer HEAD with 405 and GET fine
            self.send_response(405)
            self.end_headers()
        elif self.path == "/missing":
            self.send_response(404)
            self.end_headers()
        else:
            self._send(False)

    def do_GET(self):
        if self.path == "/missing":
            self.send_response(404)
            self.end_headers()
        elif self.path == "/changed":
            self._send(True, b"someone replaced this file\n")
        else:
            self._send(True)


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _one(url, sha=GOOD_SHA, verify=False):
    return tc.check_url(tc.Part("t", url, sha), verify=verify, timeout=5)


def test_a_live_url_passes_and_a_404_is_a_failure(server):
    assert _one(f"{server}/ok").ok
    gone = _one(f"{server}/missing")
    assert not gone.ok and gone.kind == "http" and "404" in gone.detail


def test_a_host_that_refuses_head_is_retried_with_a_one_byte_get(server):
    assert _one(f"{server}/head-refused").ok


def test_verify_mode_catches_a_file_that_changed_under_its_pin(server):
    assert _one(f"{server}/ok", verify=True).ok
    changed = _one(f"{server}/changed", verify=True)
    assert not changed.ok and changed.kind == "sha" and GOOD_SHA in changed.detail


def test_a_host_that_does_not_resolve_is_told_apart_from_a_dead_link():
    gone = _one("https://no-such-host.invalid/x.tar.gz")
    assert not gone.ok and gone.kind == "dns"


def test_the_command_line_exits_nonzero_on_a_failure_and_zero_when_all_is_well(server, tmp_path, capsys):
    registry = tmp_path / "toolchains.toml"
    registry.write_text(f'["fake"]\nname = "x"\n[["fake".parts]]\nurl = "{server}/ok"\nsha256 = "{GOOD_SHA}"\n', encoding="utf-8")
    assert tc.main(["--registry", str(registry), "--allow-http"]) == 0
    registry.write_text(registry.read_text(encoding="utf-8").replace("/ok", "/missing"), encoding="utf-8")
    assert tc.main(["--registry", str(registry), "--allow-http"]) == 1
    assert "404" in capsys.readouterr().out
