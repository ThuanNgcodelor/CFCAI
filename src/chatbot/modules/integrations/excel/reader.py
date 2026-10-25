import re
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
        namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        relationships_namespace = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
        package_relationship_namespace = "{http://schemas.openxmlformats.org/package/2006/relationships}"

        with zipfile.ZipFile(p, "r") as archive:
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in root.findall(f"{namespace}si"):
                    shared_strings.append("".join(node.text or "" for node in item.iter(f"{namespace}t")))

            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {
                relation.attrib["Id"]: relation.attrib["Target"]
                for relation in relations.findall(f"{package_relationship_namespace}Relationship")
            }

            for sheet in workbook.findall(f".//{namespace}sheet"):
                title = sheet.attrib["name"]
                relation_id = sheet.attrib[f"{relationships_namespace}id"]
                target = targets[relation_id].lstrip("/")
                sheet_path = target if target.startswith("xl/") else f"xl/{target}"
                worksheet = ET.fromstring(archive.read(sheet_path))
                parsed_rows: list[dict[int, Any]] = []
                for row in worksheet.findall(f".//{namespace}row"):
                    values: dict[int, Any] = {}
                    for cell in row.findall(f"{namespace}c"):
                        coordinate = cell.attrib.get("r", "A1")
                        column_name = re.match(r"[A-Z]+", coordinate)
                        if column_name is None:
                            continue
                        column_index = 0
                        for character in column_name.group(0):
                            column_index = column_index * 26 + ord(character) - ord("A") + 1
                        column_index -= 1
                        cell_type = cell.attrib.get("t")
                        value_node = cell.find(f"{namespace}v")
                        if cell_type == "inlineStr":
                            value: Any = "".join(
                                node.text or "" for node in cell.iter(f"{namespace}t")
                            )
                        elif value_node is None or value_node.text is None:
                            value = ""
                        elif cell_type == "s":
                            value = shared_strings[int(value_node.text)]
                        elif cell_type == "b":
                            value = value_node.text == "1"
                        else:
                            value = value_node.text
                        values[column_index] = value
                    parsed_rows.append(values)

                if not parsed_rows:
                    result[title] = []
                    continue
                headers = {
                    index: str(value).strip()
                    for index, value in parsed_rows[0].items()
                    if str(value).strip()
                }
                records: list[dict[str, Any]] = []
                for values in parsed_rows[1:]:
                    record = {
                        header: values.get(index, "")
                        for index, header in headers.items()
                    }
                    if any(value not in (None, "") for value in record.values()):
                        records.append(record)
                result[title] = records
        return result
