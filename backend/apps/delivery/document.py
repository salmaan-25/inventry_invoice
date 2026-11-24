"""
Delivery Challan PDF renderer — Phase 7.

render_challan_pdf(challan) → bytes

The document is a plain placeholder until the client supplies the approved
challan format (D13). It renders products from the invoice item snapshots and
business details from the invoice's saved business snapshot, so it stays
historical even if the catalogue or settings change later.

Template: apps/delivery/templates/delivery/challan.html
"""

from io import BytesIO

from django.template.loader import render_to_string

from apps.common.decimals import format_quantity
from apps.delivery.models import DeliveryChallan


def render_challan_pdf(challan: DeliveryChallan) -> bytes:
    """Render a delivery challan as PDF bytes."""
    invoice = challan.invoice

    items = []
    for line in challan.items.select_related("invoice_item").all():
        item = line.invoice_item
        items.append(
            {
                "line_no": item.line_no,
                "product_name": item.product_name,
                "product_code": item.product_code,
                "hsn_sac": item.hsn_sac,
                "unit_name": item.unit_name,
                "quantity": format_quantity(line.quantity),
            }
        )

    context = {
        "challan": challan,
        "invoice": invoice,
        "biz": invoice.business_snapshot or {},
        "cust": invoice.customer_snapshot or {},
        "items": items,
    }

    html = render_to_string("delivery/challan.html", context)

    from xhtml2pdf import pisa

    pdf_buffer = BytesIO()
    pisa.CreatePDF(html, dest=pdf_buffer)
    return pdf_buffer.getvalue()
