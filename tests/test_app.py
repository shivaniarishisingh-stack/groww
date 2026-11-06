from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.config import settings

APP_PATH = Path(__file__).resolve().parent.parent / "src" / "app.py"


def make_app():
    return AppTest.from_file(APP_PATH, default_timeout=60).run()


def test_app_renders_disclaimer_and_examples():
    app = make_app()
    assert not app.exception

    warning_text = " ".join(element.value for element in app.warning).lower()
    assert "facts-only" in warning_text
    assert "no investment advice" in warning_text

    button_labels = [button.label for button in app.button]
    for example in settings.ui.examples:
        assert example in button_labels


def test_example_button_fills_the_question_box():
    app = make_app()
    example = settings.ui.examples[0]
    app.button(key="example_0").click().run()
    assert app.text_area[0].value == example


def test_advice_question_renders_a_refusal_in_the_ui():
    app = make_app()
    app.text_area[0].set_value("Should I buy HDFC Flexi Cap?")
    app.button[-1].click().run()

    assert not app.exception
    rendered = " ".join(element.value for element in app.markdown)
    assert "investment advice" in rendered.lower()
    assert "**Source:**" in rendered
    assert all("pipeline trace" not in item.label.lower() for item in app.expander)


def test_pipeline_trace_is_not_rendered():
    app = make_app()
    assert not app.exception
    assert all("pipeline trace" not in item.label.lower() for item in app.expander)


def test_app_renders_sources_sample_qa_and_disclaimer():
    app = make_app()
    assert not app.exception

    rendered = " ".join(element.value for element in app.markdown)
    captions = " ".join(element.value for element in app.caption)

    for url in settings.urls:
        assert url in rendered
    assert "The expense ratio is 1.01%." in rendered
    assert "Disclaimer" in rendered
    assert "The minimum SIP investment is ₹100." in rendered
    assert "Mutual fund investments are subject to market risks" in captions

    expander_labels = " ".join(item.label for item in app.expander)
    assert "Sources" in expander_labels
    assert "Sample questions" in expander_labels
