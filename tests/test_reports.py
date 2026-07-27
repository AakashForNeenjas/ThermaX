import pandas as pd

from thermal_analyzer.reporting.html_report import (
    generate_html_report_for_run,
    generate_section_html_report,
)


def test_report_escapes_uploaded_text_and_includes_provenance(thermal_run_factory):
    run = thermal_run_factory(run_id="<script>alert(1)</script>")
    run.metadata = {"label": "<img src=x onerror=alert(1)>"}
    run.notes = "<b>unsafe</b>"
    stats = pd.DataFrame({"component": ["<svg>"], "max_temp": [40.0]})
    limits = pd.DataFrame(
        {"component": ["<svg>"], "status": ["<script>"], "max_temp": [40.0]}
    )
    report = generate_html_report_for_run(
        run,
        stats,
        limits,
        {"steady": True},
        provenance={"source_sha256": "abc123"},
    )

    assert "<script>alert(1)</script>" not in report
    assert "<img src=x onerror=alert(1)>" not in report
    assert "<b>unsafe</b>" not in report
    assert "&lt;script&gt;" in report
    assert "abc123" in report
    assert "THERMAX_VERSION" in report


def test_section_report_escapes_title_content_and_table():
    report = generate_section_html_report(
        "<script>title</script>",
        [
            {
                "header": "<b>header</b>",
                "content": "<img src=x>",
                "dataframe": pd.DataFrame({"value": ["<svg>"]}),
            }
        ],
    )

    assert "<script>title</script>" not in report
    assert "<b>header</b>" not in report
    assert "<img src=x>" not in report
    assert "<svg>" not in report
