"""Tests for Hugging Face Parser implementation."""

import logging
from datetime import datetime

import pytest

from app.fetchers.huggingface import HuggingFaceParser
from app.models.source import HFSource, HFSourceType


@pytest.fixture
def parser():
    """Provide a HuggingFaceParser instance."""
    return HuggingFaceParser()


@pytest.fixture
def mock_dataset_source():
    """Provide a mock Hugging Face dataset source."""
    return HFSource(name="squad", resource_id="rajpurkar/squad", source_type=HFSourceType.DATASET)


@pytest.fixture
def mock_model_source():
    """Provide a mock Hugging Face model source."""
    return HFSource(
        name="bert", resource_id="google-bert/bert-base-uncased", source_type=HFSourceType.MODEL
    )


# --- Sample JSON Data ---

SAMPLE_MODEL_JSON = {
    "id": "google-bert/bert-base-uncased",
    "lastModified": "2024-03-15T10:00:00.000Z",
    "description": "BERT is a transformers model pretrained on a large corpus of English data.",
    "cardData": {"title": "BERT Base Uncased", "language": "en"},
}

SAMPLE_DATASET_JSON = {
    "id": "rajpurkar/squad",
    "lastModified": "2024-03-10T08:00:00.000Z",
    "description": "Stanford Question Answering Dataset (SQuAD) is "
    "a reading comprehension dataset.",
    "cardData": {"title": "SQuAD", "language": ["en"]},
}

SAMPLE_JSON_NO_TITLE = {
    "id": "some-org/some-model",
    "lastModified": "2024-03-01T12:00:00Z",
    "description": "A model without a card title.",
    # No cardData.title
}

SAMPLE_JSON_NO_ID = {
    "lastModified": "2024-03-01T12:00:00Z",
    "description": "A resource without an ID.",
    # Missing id, modelId, datasetId
}


# --- Tests for parse ---


def test_parse_model_success(parser, mock_model_source):
    """Verify that a valid model JSON is parsed into correct RawArticle."""
    articles = parser.parse(SAMPLE_MODEL_JSON, mock_model_source)

    assert len(articles) == 1
    article = articles[0]

    assert article.title == "BERT Base Uncased"
    assert article.url == "https://huggingface.co/google-bert/bert-base-uncased"
    assert "transformers model pretrained" in article.content
    assert article.source_name == "bert"
    assert isinstance(article.published_date, datetime)
    assert article.published_date.year == 2024
    assert article.published_date.month == 3


def test_parse_dataset_success(parser, mock_dataset_source):
    """Verify that a valid dataset JSON is parsed into correct RawArticle."""
    articles = parser.parse(SAMPLE_DATASET_JSON, mock_dataset_source)

    assert len(articles) == 1
    article = articles[0]

    assert article.title == "SQuAD"
    assert article.url == "https://huggingface.co/datasets/rajpurkar/squad"
    assert "reading comprehension dataset" in article.content
    assert article.source_name == "squad"
    assert isinstance(article.published_date, datetime)


def test_parse_fallback_title_to_id(parser, mock_model_source):
    """Verify that title falls back to resource_id if cardData.title is missing."""
    articles = parser.parse(SAMPLE_JSON_NO_TITLE, mock_model_source)

    assert len(articles) == 1
    assert articles[0].title == "some-org/some-model"  # Fallback to id


def test_parse_skips_missing_id(parser, mock_model_source, caplog):
    """Verify that resources missing ID are skipped."""
    with caplog.at_level(logging.WARNING):
        articles = parser.parse(SAMPLE_JSON_NO_ID, mock_model_source)

    assert len(articles) == 0
    assert "missing 'id', 'modelId', or 'datasetId'" in caplog.text


def test_parse_handles_empty_description(parser, mock_model_source):
    """Verify that missing description results in empty content string."""
    json_no_desc = {"id": "test/model", "lastModified": "2024-03-01T12:00:00Z"}

    articles = parser.parse(json_no_desc, mock_model_source)

    assert len(articles) == 1
    assert articles[0].content == ""


# --- Tests for date parsing ---


def test_parse_iso_date_with_milliseconds(parser):
    """Verify that ISO dates with milliseconds and 'Z' are parsed correctly."""
    date_str = "2024-03-15T10:00:00.000Z"
    result = parser._parse_iso_date(date_str)

    assert result is not None
    assert result.year == 2024
    assert result.month == 3
    assert result.day == 15


def test_parse_iso_date_without_milliseconds(parser):
    """Verify that ISO dates without milliseconds are parsed correctly."""
    date_str = "2024-03-15T10:00:00Z"
    result = parser._parse_iso_date(date_str)

    assert result is not None
    assert result.year == 2024


def test_parse_iso_date_invalid_format(parser, caplog):
    """Verify that invalid date strings return None and log warning."""
    with caplog.at_level(logging.WARNING):
        result = parser._parse_iso_date("not-a-date")

    assert result is None
    assert "Failed to parse date" in caplog.text


def test_parse_iso_date_none(parser):
    """Verify that None input returns None."""
    result = parser._parse_iso_date(None)
    assert result is None
