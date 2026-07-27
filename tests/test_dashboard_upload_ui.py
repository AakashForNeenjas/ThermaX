from streamlit.testing.v1 import AppTest


def _radio_with_label(app, label):
    return next(radio for radio in app.radio if radio.label == label)


def _file_uploader_labels(app):
    return {
        element.label
        for element in app.main
        if element.type == "file_uploader"
    }


def test_campaign_modes_offer_browser_uploads():
    app = AppTest.from_file("thermal_analyzer/ui/dashboard.py")
    app.run(timeout=30)

    app.sidebar.radio[0].set_value("Campaign Analysis").run(timeout=30)
    _radio_with_label(app, "Campaign files input").set_value(
        "Upload Excel files"
    ).run(timeout=30)
    assert "Campaign files" in _file_uploader_labels(app)

    app.sidebar.radio[0].set_value("Component Comparison").run(timeout=30)
    _radio_with_label(app, "Run files input").set_value(
        "Upload Excel files"
    ).run(timeout=30)
    assert "Run files" in _file_uploader_labels(app)

    app.sidebar.radio[0].set_value("Samples Comparison (A vs B)").run(timeout=30)
    _radio_with_label(app, "Sample A files input").set_value(
        "Upload Excel files"
    ).run(timeout=30)
    _radio_with_label(app, "Sample B files input").set_value(
        "Upload Excel files"
    ).run(timeout=30)
    assert {"Sample A files", "Sample B files"} <= _file_uploader_labels(app)
