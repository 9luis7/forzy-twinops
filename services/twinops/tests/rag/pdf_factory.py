"""Small dependency-free searchable PDF builder for ingestion tests."""


def searchable_pdf(*page_texts: str) -> bytes:
    objects: list[bytes] = []
    page_count = len(page_texts)
    first_page_object = 3
    font_object = first_page_object + page_count * 2
    kids = " ".join(
        f"{first_page_object + index * 2} 0 R" for index in range(page_count)
    )
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(
        (
            f"<< /Type /Pages /Count {page_count} /Kids [{kids}] >>"
        ).encode("ascii")
    )
    for index, text in enumerate(page_texts):
        page_object = first_page_object + index * 2
        content_object = page_object + 1
        escaped = (
            text.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
        )
        stream = (
            "BT /F1 12 Tf 72 720 Td "
            f"({escaped}) Tj ET"
        ).encode("latin-1")
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R "
                "/MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_object} 0 R >> >> "
                f"/Contents {content_object} 0 R >>"
            ).encode("ascii")
        )
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode("ascii"))
        result.extend(body)
        result.extend(b"\nendobj\n")
    xref_offset = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    result.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    result.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(result)
