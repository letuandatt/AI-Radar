import pytest

from app.prompts.builder import PromptBuilder, PromptBuildError


def test_build_with_variables():
    builder = PromptBuilder("Hello {name}, welcome to {place}.")
    builder.with_variable("name", "Alice")
    builder.with_variables({"place": "Wonderland"})
    assert builder.build() == "Hello Alice, welcome to Wonderland."


def test_build_fails_on_missing_variables():
    builder = PromptBuilder("Hello {name}.")
    with pytest.raises(PromptBuildError):
        builder.build()


def test_untrusted_data_wrapping():
    builder = PromptBuilder("Data: {untrusted_data}")
    builder.with_untrusted_data("Some <script> payload")
    result = builder.build()
    print(result)
    assert "<untrusted_data>" in result
    assert "</untrusted_data>" in result
    assert "&lt;script&gt;" in result
    assert "<script>" not in result
