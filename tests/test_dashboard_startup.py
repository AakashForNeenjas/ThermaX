import importlib
import subprocess
import sys

from streamlit.testing.v1 import AppTest


def test_package_importable():
    """The package must be importable in the current test environment."""
    importlib.import_module("thermal_analyzer")


def test_dashboard_module_importable():
    """The Streamlit dashboard module should be importable (not running the server).

    Importing the module is a lightweight check that essential top-level imports are
    available and will fail fast if the package isn't installed or modules are missing.
    """
    importlib.import_module("thermal_analyzer.ui.dashboard")


def test_root_streamlit_entrypoint_importable():
    importlib.import_module("streamlit_app")


def test_root_streamlit_entrypoint_renders_dashboard():
    app = AppTest.from_file("streamlit_app.py")
    app.run(timeout=30)

    assert not app.exception
    assert app.sidebar.radio[0].label == "Select Mode"


def test_streamlit_executable_available():
    """Check that running `python -m streamlit --version` succeeds in this environment."""
    res = subprocess.run([sys.executable, "-m", "streamlit", "--version"], capture_output=True, text=True)
    assert res.returncode == 0, f"streamlit returned non-zero: {res.returncode} stderr={res.stderr}"
    out = (res.stdout or "") + (res.stderr or "")
    assert "streamlit" in out.lower() or "streamlit" in (res.stdout or ""), "streamlit --version returned unexpected output"
