import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any


class FastExcelReader:
    """
    Standard-library based Excel XLSX reader.
    Guarantees 100% pure Python execution without requiring binary compilation.
    """

    @staticmethod
    def read_sheets(file_path: str) -> dict[str, list[dict[str, Any]]]:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"Excel file not found: {file_path}")

        result: dict[str, list[dict[str, Any]]] = {}

        with zipfile.ZipFile(p, "r") as z:
            # 1. Parse shared strings table
            shared_strings = []
            if "xl/sharedStrings.xml" in z.namelist():
                sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in sst.findall(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"
                ):
                    text_node = si.find(
                        "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
                    )
                    shared_strings.append(
                        text_node.text
                        if text_node is not None and text_node.text
                        else ""
                    )

            # 2. Parse workbook structure to get sheet names
            wb = ET.fromstring(z.read("xl/workbook.xml"))
            ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            sheets = wb.findall(".//m:sheet", ns)

            for idx, s in enumerate(sheets):
                s_name = s.attrib["name"]
                sheet_file = f"xl/worksheets/sheet{idx + 1}.xml"
                if sheet_file not in z.namelist():
                    continue

                ws = ET.fromstring(z.read(sheet_file))
                rows = ws.findall(".//m:row", ns)
                if not rows:
                    result[s_name] = []
                    continue

                # Header row
                header_row = rows[0]
                headers: list[str] = []
                for cell in header_row.findall("m:c", ns):
                    v = cell.find("m:v", ns)
                    cell_type = cell.attrib.get("t")
                    val = ""
                    if v is not None and v.text:
                        val = (
                            shared_strings[int(v.text)] if cell_type == "s" else v.text
                        )
                    headers.append(val.strip())

                # Data rows
                sheet_data: list[dict[str, Any]] = []
                for r in rows[1:]:
                    row_dict = {}
                    cells = r.findall("m:c", ns)
                    for col_idx, cell in enumerate(cells):
                        if col_idx >= len(headers):
                            break
                        h_name = headers[col_idx]
                        if not h_name:
                            continue

                        v = cell.find("m:v", ns)
                        cell_type = cell.attrib.get("t")
                        val = ""
                        if v is not None and v.text:
                            val = (
                                shared_strings[int(v.text)]
                                if cell_type == "s"
                                else v.text
                            )
                        row_dict[h_name] = val

                    if any(row_dict.values()):
                        sheet_data.append(row_dict)

                result[s_name] = sheet_data

        return result
