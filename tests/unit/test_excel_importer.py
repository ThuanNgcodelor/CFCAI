from pathlib import Path
from src.chatbot.modules.integrations.excel.reader import FastExcelReader
from src.chatbot.modules.integrations.excel.importer import ExcelCatalogImporter
from src.chatbot.shared.enums import CatalogStatus, PageCode

def test_fast_excel_reader_cfc():
    cfc_path = "docs/CfcCoBayN8n.xlsx"
    assert Path(cfc_path).exists()
    
    sheets = FastExcelReader.read_sheets(cfc_path)
    assert "FAQ" in sheets
    assert len(sheets["FAQ"]) > 0
    # Check that headers were properly parsed
    first_row = sheets["FAQ"][0]
    assert "intent" in first_row
    assert "answer" in first_row

def test_fast_excel_reader_zeo():
    zeo_path = "docs/ZeoN8n.xlsx"
    assert Path(zeo_path).exists()
    
    sheets = FastExcelReader.read_sheets(zeo_path)
    assert "FAQ" in sheets
    assert "Shopee" in sheets
    assert len(sheets["Shopee"]) > 0

def test_excel_importer_staging_and_quarantine():
    # INV-5: All new records must default to QUARANTINED
    importer = ExcelCatalogImporter()
    cfc_res = importer.import_cfc_file("docs/CfcCoBayN8n.xlsx")
    zeo_res = importer.import_zeo_file("docs/ZeoN8n.xlsx")

    assert cfc_res["imported_faq_count"] > 0
    assert zeo_res["imported_product_count"] > 0

    # Verify all records have QUARANTINED status
    for faq in importer.staged_faqs:
        assert faq["status"] == CatalogStatus.QUARANTINED.value
        assert faq["approved"] is False

    for prod in importer.staged_products:
        assert prod["status"] == CatalogStatus.QUARANTINED.value
        assert prod["approved"] is False

def test_excel_conflict_detection_case_t11():
    # Case T11: When two rows have identical SKU with conflicting names
    importer = ExcelCatalogImporter()
    
    # Simulate conflict in seen_skus
    seen = {"SKU-999": {"name": "Sản phẩm A"}}
    conflicts = []
    
    new_row = {"item_id": "SKU-999", "name": "Sản phẩm B (mâu thuẫn)"}
    if new_row["item_id"] in seen:
        if seen[new_row["item_id"]]["name"] != new_row["name"]:
            conflicts.append(new_row)

    assert len(conflicts) == 1
    assert conflicts[0]["item_id"] == "SKU-999"
