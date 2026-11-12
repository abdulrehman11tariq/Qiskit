"""Smoke test: the whole Streamlit page renders without raising."""
from streamlit.testing.v1 import AppTest


def test_app_renders_and_recommends_a_plan():
    app = AppTest.from_file("../app.py", default_timeout=180).run()
    assert not app.exception
    assert any("Recommended: stock" in s.value for s in app.subheader)
    assert len(app.metric) >= 12          # 4 headline + 8 quantum metrics
