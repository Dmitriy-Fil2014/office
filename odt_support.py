"""Minimal local OpenDocument Text (.odt) reader/writer.

Keeps the ODT ZIP package and updates paragraph text in content.xml.
Complex formatting is retained where possible; text edits are paragraph based.
"""
import io
import zipfile
import xml.etree.ElementTree as ET

NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}
ET.register_namespace("office", NS["office"])
ET.register_namespace("text", NS["text"])


def _paragraphs(root):
    return root.findall(".//text:p", NS) + root.findall(".//text:h", NS)


def _plain_text(element):
    parts = []
    for node in element.iter():
        if node.tag == "{%s}tab" % NS["text"]:
            parts.append("\t")
        elif node.tag == "{%s}line-break" % NS["text"]:
            parts.append("\n")
        elif node.text:
            parts.append(node.text)
    return "".join(parts)


def read_odt_bytes(data):
    with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
        root = ET.fromstring(archive.read("content.xml"))
    return "\n".join(_plain_text(p) for p in _paragraphs(root))


def modify_odt_bytes(data, new_text):
    source = io.BytesIO(data)
    output = io.BytesIO()
    with zipfile.ZipFile(source, "r") as zin:
        entries = [(item, zin.read(item.filename)) for item in zin.infolist()]
    content = next((payload for item, payload in entries if item.filename == "content.xml"), None)
    if content is None:
        raise ValueError("В ODT отсутствует content.xml")
    root = ET.fromstring(content)
    paragraphs = _paragraphs(root)
    lines = new_text.split("\n")
    for index, paragraph in enumerate(paragraphs):
        value = lines[index] if index < len(lines) else ""
        text_nodes = [node for node in paragraph.iter() if node.tag in ("{%s}span" % NS["text"],)]
        spans = [node for node in paragraph.iter() if node.tag == "{%s}p" % NS["text"] or node.tag == "{%s}h" % NS["text"]]
        del text_nodes, spans
        first = True
        for node in paragraph.iter():
            if node.text:
                if first:
                    node.text = value
                    first = False
                else:
                    node.text = ""
        if first:
            paragraph.text = value
    updated = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(output, "w") as zout:
        for item, payload in entries:
            if item.filename == "content.xml":
                payload = updated
            info = zipfile.ZipInfo(item.filename, item.date_time)
            info.compress_type = zipfile.ZIP_STORED if item.filename == "mimetype" else item.compress_type
            info.external_attr = item.external_attr
            zout.writestr(info, payload)
    return output.getvalue()
