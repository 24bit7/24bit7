"""Signing in to a Tidal account (for Output to Tidal): the sign-in, renewing, signing out, and failing plainly."""

import threading
import time
import urllib.parse
import urllib.request

import pytest

from conftest import free_port


def keys_on(app, **extra):
    app.set_env(TIDAL_CLIENT_ID="test-id", TIDAL_CLIENT_SECRET="test-secret", **extra)


@pytest.fixture
def port(app, monkeypatch):
    """A free port for the sign-in listener, so the test never needs 47807."""
    p = free_port()
    monkeypatch.setattr(app.engine, "TIDAL_REDIRECT_PORT", p)
    monkeypatch.setattr(app.engine, "TIDAL_REDIRECT_URI", f"http://localhost:{p}/tidal")
    app.web.tidal_login["redirect_uri"] = f"http://localhost:{p}/tidal"
    return p


def browser(app, port, answer=None, state=None):
    """
    Stands in for the browser: reads the sign-in page's address, then calls the
    listener back the way Tidal would. answer: the reply's query (default: the good code).
    """
    opened = []

    def open_page(url):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        opened.append(q)
        app.web.tidal_login["challenge"] = q["code_challenge"]
        reply = dict(answer or {"code": app.web.tidal_login["code"]}, state=state or q["state"])

        def call_back():
            time.sleep(0.2)
            back = f"http://127.0.0.1:{port}/tidal?" + urllib.parse.urlencode(reply)
            try:
                urllib.request.urlopen(back, timeout=5).read()
            except Exception:
                pass
        threading.Thread(target=call_back, daemon=True).start()
    return open_page, opened


def test_sign_in_returns_the_login_to_save(app, port):
    keys_on(app)
    open_page, opened = browser(app, port)
    login = app.engine.tidal_sign_in(open_page=open_page, wait=10)
    assert login == {"refresh_token": "fake-refresh", "user_id": "12345"}
    q = opened[0]
    assert q["client_id"] == "test-id" and q["code_challenge_method"] == "S256"
    assert q["scope"] == "playlists.read playlists.write"
    assert q["redirect_uri"] == f"http://localhost:{port}/tidal"


def test_saved_login_renews_once_and_is_reused(app, port):
    keys_on(app, TIDAL_REFRESH_TOKEN="fake-refresh", TIDAL_USER_ID="12345")
    e = app.engine
    assert e.tidal_signed_in()
    assert e.tidal_user_token() == "fake-user-token-renewed"
    assert e.tidal_user_token() == "fake-user-token-renewed"
    renewals = [c for c in app.web.calls if c[0] == "tidal" and c[1] == "/v1/oauth2/token"]
    assert len(renewals) == 1


def test_refused_renewal_says_sign_in_again(app):
    keys_on(app, TIDAL_REFRESH_TOKEN="fake-refresh")
    app.web.tidal_login["refresh_ok"] = False
    with pytest.raises(app.engine.TidalSignInError, match="Sign in to Tidal again under Settings > Keys"):
        app.engine.tidal_user_token()


def test_not_signed_in(app):
    keys_on(app)
    e = app.engine
    assert not e.tidal_signed_in()
    with pytest.raises(e.TidalSignInError, match="Not signed in to Tidal"):
        e.tidal_user_token()


def test_needs_the_client_id_and_secret_first(app, port):
    app.set_env(TIDAL_CLIENT_ID="", TIDAL_CLIENT_SECRET="")
    with pytest.raises(app.engine.TidalSignInError, match="Client ID and Client Secret"):
        app.engine.tidal_sign_in(open_page=lambda url: None, wait=1)


def test_turned_down_on_tidals_page(app, port):
    keys_on(app)
    open_page, _ = browser(app, port, answer={"error": "access_denied"})
    with pytest.raises(app.engine.TidalSignInError, match="access_denied"):
        app.engine.tidal_sign_in(open_page=open_page, wait=10)


def test_a_reply_for_another_sign_in_is_ignored(app, port):
    keys_on(app)
    open_page, _ = browser(app, port, state="someone-elses")
    with pytest.raises(app.engine.TidalSignInError, match="Nothing came back from Tidal"):
        app.engine.tidal_sign_in(open_page=open_page, wait=2)


def test_nothing_back_points_at_the_redirect_address(app, port):
    keys_on(app)
    with pytest.raises(app.engine.TidalSignInError, match=f"http://localhost:{port}/tidal"):
        app.engine.tidal_sign_in(open_page=lambda url: None, wait=1)


def test_cancel_stops_the_wait(app, port):
    keys_on(app)
    cancelled = threading.Event()
    started = time.time()
    threading.Timer(0.3, cancelled.set).start()
    with pytest.raises(app.engine.TidalSignInError, match="cancelled"):
        app.engine.tidal_sign_in(open_page=lambda url: None, wait=60, cancelled=cancelled)
    assert time.time() - started < 5


def test_port_in_use(app, port):
    import socket
    keys_on(app)
    busy = socket.socket()
    busy.bind(("127.0.0.1", port))
    busy.listen(1)
    try:
        with pytest.raises(app.engine.TidalSignInError, match="in use"):
            app.engine.tidal_sign_in(open_page=lambda url: None, wait=1)
    finally:
        busy.close()


def test_sign_out_forgets_the_login(app):
    keys_on(app, TIDAL_REFRESH_TOKEN="fake-refresh")
    e = app.engine
    e.tidal_user_token()
    e.tidal_sign_out()
    app.set_env(TIDAL_REFRESH_TOKEN="")
    assert not e.tidal_signed_in()
    with pytest.raises(e.TidalSignInError):
        e.tidal_user_token()


def test_catalogue_login_unchanged(app):
    """The Tidal source still uses the client ID and secret alone, signed in or not."""
    keys_on(app)
    assert app.engine.tidal_token() == "fake-tidal-token"


def test_saved_login_hidden_in_support_reports(app):
    line = app.engine._redact_env_line("TIDAL_REFRESH_TOKEN=abcdef")
    assert "abcdef" not in line and "set (6 chars)" in line
