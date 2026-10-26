from __future__ import annotations

from pathlib import Path

import pytest

from src.chatbot.modules.integrations.data_loader import DataSourceLoader


def _manifest(tmp_path: Path, *, auto_publish: bool = False) -> Path:
    path = tmp_path / "manifest.yaml"
    path.write_text(
        f"""version: 1
sources:
  - id: fixture-faq
    page_id: CFC
    kind: markdown_faq
    path: tests/fixtures/markdown_faq_legacy.md
    mapping: tests/fixtures/markdown_mapping.json
    importer_source: fixture-cfc-faq
    auto_stage: true
    auto_publish: {str(auto_publish).lower()}
""",
        encoding="utf-8",
    )
    return path


def test_manifest_validation_parses_registered_source(tmp_path: Path) -> None:
    result = DataSourceLoader(_manifest(tmp_path)).validate()
    assert result[0]["source_id"] == "fixture-faq"
    assert result[0]["page_id"] == "CFC"
    assert result[0]["record_count"] == 1
    assert result[0]["valid"] is True


def test_manifest_rejects_auto_publish(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot enable auto_publish"):
        DataSourceLoader(_manifest(tmp_path, auto_publish=True)).sources()
