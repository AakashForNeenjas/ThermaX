import os
import sys
from streamlit.web import cli as stcli

def p(*parts):
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, *parts)

if __name__ == "__main__":
    # Force production frontend in packaged builds.
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    os.environ["STREAMLIT_DEVELOPMENT_MODE"] = "false"

    app = p("thermal_analyzer", "ui", "dashboard.py")
    sys.argv = [
        "streamlit",
        "run",
        app,
        "--server.headless=false",
        "--server.address=127.0.0.1",
        "--server.port=8501",
        "--global.developmentMode=false",
        "--browser.gatherUsageStats=false",
    ]
    raise SystemExit(stcli.main())
