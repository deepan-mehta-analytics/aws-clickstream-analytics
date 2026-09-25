# ── Package smoke test ────────────────────────────────────────
import clickstream                                   # the package under test


def test_package_has_version():                      # the package must import and expose a version
    assert clickstream.__version__ == "0.1.0"        # version string set in __init__.py
