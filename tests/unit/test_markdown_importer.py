from src.chatbot.modules.integrations.markdown.importer import MarkdownCatalogImporter
from src.chatbot.shared.enums import CatalogStatus


def test_markdown_importer_parses_legacy_table_and_quarantines_everything():
    importer = MarkdownCatalogImporter("tests/fixtures/markdown_mapping.json")

    report = importer.import_source("fixture-cfc-faq")

    assert report["imported_faq_count"] == 1
    assert report["skipped_row_count"] == 1
    assert len(importer.staged_faqs) == 1
    faq = importer.staged_faqs[0]
    assert faq["status"] == CatalogStatus.QUARANTINED.value
    assert faq["approved"] is False
    assert faq["question_examples"] == ["Sản phẩm có gì?", "Có loại nào?"]
    assert faq["intent"] == "markdown_faq_thong_tin_chung"
    assert faq["source_file"] == "markdown_faq_legacy.md"
