from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class RenderedPage:
    page_number: int
    png_bytes: bytes
    width: int
    height: int


def render_pdf_to_png_pages(
    pdf_bytes: bytes, *, scale: float = 2.0
) -> list[RenderedPage]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    pages: list[RenderedPage] = []

    for i in range(len(pdf)):
        page = pdf.get_page(i)
        bitmap = page.render(scale=scale)
        pil_img: Image.Image = bitmap.to_pil()
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        png = buf.getvalue()
        pages.append(
            RenderedPage(
                page_number=i + 1,
                png_bytes=png,
                width=pil_img.width,
                height=pil_img.height,
            )
        )
        page.close()

    pdf.close()
    return pages
