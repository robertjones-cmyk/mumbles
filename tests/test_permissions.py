import sys

from mumbles import permissions


def test_translocation_is_detected_from_the_executable_path(monkeypatch):
    monkeypatch.setattr(
        sys, "executable",
        "/private/var/folders/30/T/AppTranslocation/B7E7/d/mumbles.app"
        "/Contents/MacOS/mumbles")
    assert permissions.is_translocated()
    # The remedy must point at the real app, not the throwaway copy.
    assert "/Applications/mumbles.app" in permissions.quarantine_fix_command()


def test_a_normal_install_is_not_translocated(monkeypatch):
    monkeypatch.setattr(sys, "executable",
                        "/Applications/mumbles.app/Contents/MacOS/mumbles")
    assert not permissions.is_translocated()
    assert permissions.bundle_path() == "/Applications/mumbles.app"


def test_bundle_path_is_empty_when_running_from_source(monkeypatch):
    monkeypatch.setattr(sys, "executable", "/usr/local/bin/python3")
    assert permissions.bundle_path() == ""


def test_problems_reports_translocation_and_accessibility(monkeypatch):
    monkeypatch.setattr(permissions, "is_translocated", lambda: True)
    monkeypatch.setattr(permissions, "accessibility_trusted", lambda: False)
    labels = [p[0] for p in permissions.problems()]
    assert len(labels) == 2
    # Translocation first: granting Accessibility is pointless until it is
    # fixed, because the grant will not survive the next launch.
    assert "quarantined" in labels[0]
    assert "Accessibility" in labels[1]


def test_no_problems_when_everything_is_granted(monkeypatch):
    monkeypatch.setattr(permissions, "is_translocated", lambda: False)
    monkeypatch.setattr(permissions, "accessibility_trusted", lambda: True)
    assert permissions.problems() == []


def test_accessibility_check_never_cries_wolf_when_it_cannot_tell(monkeypatch):
    monkeypatch.setattr(permissions, "is_mac", lambda: True)
    import ctypes

    def boom(_path):
        raise OSError("framework missing")

    monkeypatch.setattr(ctypes.cdll, "LoadLibrary", boom)
    assert permissions.accessibility_trusted() is True
