"""
Invoice PDF document renderer — Phase 5B.

render_invoice_pdf(invoice) → bytes

Renders the invoice as a PDF using xhtml2pdf (ReportLab backend) matching
the exact layout in finalinv.pdf and client specification on a US Letter
page.  Short invoices stay on one page; longer ones flow onto extra pages
with the item table's header repeated.

Template: apps/invoices/templates/invoices/invoice.html
"""

import os
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.template.loader import render_to_string

from apps.common.constants import gst_state_code
from apps.invoices.models import Invoice


def _amount_in_words(amount) -> str:
    """
    Convert an integer rupee amount to words (Indian number system).
    Example: 331068 → 'Three Lakh Thirty One Thousand Sixty Eight'
    """
    ones = [
        "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
        "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
        "Sixteen", "Seventeen", "Eighteen", "Nineteen",
    ]
    tens = [
        "", "", "Twenty", "Thirty", "Forty", "Fifty",
        "Sixty", "Seventy", "Eighty", "Ninety",
    ]

    def _below_hundred(n: int) -> str:
        if n < 20:
            return ones[n]
        return (tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")).strip()

    def _below_thousand(n: int) -> str:
        if n < 100:
            return _below_hundred(n)
        return (ones[n // 100] + " Hundred" + (" " + _below_hundred(n % 100) if n % 100 else "")).strip()

    if amount == 0:
        return "Zero"

    n = int(amount)
    parts = []

    crore = n // 10_000_000
    n %= 10_000_000
    lakh = n // 100_000
    n %= 100_000
    thousand = n // 1000
    n %= 1000
    rest = n

    if crore:
        parts.append(_below_thousand(crore) + " Crore")
    if lakh:
        parts.append(_below_thousand(lakh) + " Lakh")
    if thousand:
        parts.append(_below_thousand(thousand) + " Thousand")
    if rest:
        parts.append(_below_thousand(rest))

    return " ".join(parts)


def _paise_words(paise: int) -> str:
    ones = [
        "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
        "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
        "Sixteen", "Seventeen", "Eighteen", "Nineteen",
    ]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty",
            "Sixty", "Seventy", "Eighty", "Ninety"]
    if paise == 0:
        return ""
    if paise < 20:
        return ones[paise]
    return (tens[paise // 10] + (" " + ones[paise % 10] if paise % 10 else "")).strip()


def grand_total_in_words(grand_total) -> str:
    """'INR Three Lakh Thirty One Thousand Sixty Eight Only'"""
    if not grand_total:
        return "INR Zero Only"
    gt = Decimal(str(grand_total))
    rupees = int(gt)
    paise = round((gt - Decimal(rupees)) * 100)
    words = "INR " + _amount_in_words(rupees)
    if paise > 0:
        words += f" and {_paise_words(paise)} paise"
    words += " Only"
    return words


def format_indian_currency(val, decimals: int = 2) -> str:
    """
    Format a number or Decimal into Indian comma-separated format.
    Example: 280566.00 -> '2,80,566.00'
    """
    if val is None or val == "":
        return ""
    try:
        d = Decimal(str(val))
    except Exception:
        return str(val)

    sign = "-" if d < 0 else ""
    d = abs(d)
    fmt_str = f"{{:.{decimals}f}}"
    val_str = fmt_str.format(d)
    parts = val_str.split(".")
    integer_part = parts[0]
    decimal_part = f".{parts[1]}" if len(parts) > 1 and decimals > 0 else ""

    if len(integer_part) <= 3:
        formatted_int = integer_part
    else:
        last3 = integer_part[-3:]
        rest = integer_part[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted_int = ",".join(groups) + "," + last3

    return f"{sign}{formatted_int}{decimal_part}"


def pisa_link_callback(uri, rel):
    """Convert HTML URIs to absolute system paths so xhtml2pdf can access media/static."""
    if uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
    elif uri.startswith(settings.STATIC_URL):
        path = os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, ""))
    else:
        path = uri
    return path


def _find_image_path(*candidates) -> str | None:
    """Find the first existing absolute filesystem path among candidate paths/filenames."""
    for cand in candidates:
        if not cand:
            continue
        if os.path.isabs(cand) and os.path.exists(cand):
            return cand
        rel = os.path.join(settings.MEDIA_ROOT, cand)
        if os.path.exists(rel):
            return rel
    return None


def _fit_logo_size(path: str, max_width: int = 86, max_height: int = 86) -> tuple[int, int]:
    """Return display dimensions for a logo, preserving its aspect ratio."""
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
        if not width or not height:
            return max_width, max_height
        scale = min(max_width / width, max_height / height)
        return max(1, round(width * scale)), max(1, round(height * scale))
    except Exception:
        return max_width, max_height


def _font_face_paths() -> dict[str, str]:
    """
    Absolute paths for the embedded invoice font.

    Noto Sans is bundled with the app because the base-14 PDF fonts do not
    contain the rupee sign (U+20B9).  A local file URI keeps xhtml2pdf from
    depending on the host operating system's fonts.
    """
    font_dir = os.path.join(
        settings.BASE_DIR, "apps", "invoices", "static", "fonts"
    )
    names = {
        "font_regular": "NotoSans-Regular.ttf",
        "font_bold": "NotoSans-Bold.ttf",
        "font_italic": "NotoSans-Italic.ttf",
        "font_bold_italic": "NotoSans-BoldItalic.ttf",
    }
    return {
        key: os.path.join(font_dir, filename).replace("\\", "/")
        for key, filename in names.items()
    }


def render_invoice_pdf(invoice: Invoice) -> bytes:
    """
    Render invoice as PDF bytes matching the finalinv.pdf format and client specification.
    """
    is_draft = invoice.status != "ISSUED"

    logo_path = None
    if is_draft:
        customer = invoice.customer
        biz = {}
        try:
            from apps.company.models import CompanySettings
            cs = CompanySettings.objects.first()
            if cs:
                biz = {
                    "business_name": cs.business_name,
                    "address": cs.address,
                    "state": cs.state,
                    "phone": cs.phone,
                    "email": cs.email,
                    "gstin": cs.gstin,
                    "bank_holder_name": cs.bank_holder_name,
                    "bank_name": cs.bank_name,
                    "bank_account_no": cs.bank_account_no,
                    "bank_ifsc": cs.bank_ifsc,
                }
                if cs.logo:
                    try:
                        if hasattr(cs.logo, "path") and os.path.exists(cs.logo.path):
                            logo_path = cs.logo.path
                        else:
                            cand = os.path.join(settings.MEDIA_ROOT, str(cs.logo))
                            if os.path.exists(cand):
                                logo_path = cand
                    except Exception:
                        logo_path = None
        except Exception:
            biz = {}

        cust_data = {
            "name": customer.name,
            "code": customer.code,
            "phone": customer.phone,
            "gstin": customer.gstin,
            "state": customer.state,
            "billing_address": customer.billing_address,
        }
    else:
        biz = invoice.business_snapshot or {}
        cust_data = invoice.customer_snapshot or {}
        if biz.get("logo"):
            cand = os.path.join(settings.MEDIA_ROOT, biz["logo"])
            if os.path.exists(cand):
                logo_path = cand

    # Look for seal and signature images
    seal_path = _find_image_path(
        "company/seal.png",
        "company/logos/seal.jpeg",
        "company/seal.jpg",
        "company/logos/seal.png",
    )
    signature_path = _find_image_path(
        "company/signature.png",
        "company/logos/AT sign.png",
        "company/signature.jpg",
        "company/logos/signature.png",
    )

    biz_gstin = biz.get("gstin") or ""
    cust_gstin = cust_data.get("gstin") or ""

    biz_state = biz.get("state") or ""
    cust_state = cust_data.get("state") or ""
    biz_state_code = gst_state_code(biz_state, biz_gstin)
    cust_state_code = gst_state_code(cust_state, cust_gstin)

    logo_width, logo_height = (
        _fit_logo_size(logo_path) if logo_path else (86, 86)
    )

    # Consignee (Ship To) Details
    consignee_data = {
        "name": getattr(invoice, "consignee_name", "") or cust_data.get("name") or "",
        "address": getattr(invoice, "consignee_address", "") or cust_data.get("billing_address") or "",
        "gstin": getattr(invoice, "consignee_gstin", "") or cust_data.get("gstin") or "",
        "state": getattr(invoice, "consignee_state", "") or cust_data.get("state") or "Tamil Nadu",
        "state_code": getattr(invoice, "consignee_state_code", "") or cust_state_code or "33",
    }

    # Dispatch & Transport metadata
    dispatch_data = {
        "e_way_bill_no": getattr(invoice, "e_way_bill_no", "") or "",
        "delivery_note": getattr(invoice, "delivery_note", "") or "",
        "payment_terms": getattr(invoice, "payment_terms", "") or "",
        "reference_no_date": getattr(invoice, "reference_no_date", "") or "",
        "other_references": getattr(invoice, "other_references", "") or "",
        "buyer_order_no": getattr(invoice, "buyer_order_no", "") or "",
        "order_date": getattr(invoice, "order_date", None),
        "dispatch_doc_no": getattr(invoice, "dispatch_doc_no", "") or "",
        "delivery_note_date": getattr(invoice, "delivery_note_date", None),
        "dispatched_through": getattr(invoice, "dispatched_through", "") or "",
        "destination": getattr(invoice, "destination", "") or "",
        "bill_of_lading_no": getattr(invoice, "bill_of_lading_no", "") or "",
        "motor_vehicle_no": getattr(invoice, "motor_vehicle_no", "") or "",
        "terms_of_delivery": getattr(invoice, "terms_of_delivery", "") or "",
    }

    items = list(invoice.items.all().order_by("line_no"))
    lines = []
    total_qty = Decimal("0")
    primary_unit = ""
    subtotal = Decimal("0.00")
    computed_cgst_total = Decimal("0.00")
    computed_sgst_total = Decimal("0.00")

    inv_type = getattr(invoice, "invoice_type", "GST")
    is_gst = (inv_type != "NON_GST")

    for item in items:
        unit = item.unit_name or (item.product.unit.name if item.product and item.product.unit else "pcs")
        if not primary_unit and unit:
            primary_unit = unit
        total_qty += item.quantity
        subtotal += item.line_total

        gst_rate_val = item.gst_rate if is_gst else None
        if gst_rate_val is not None:
            gst_val = Decimal(str(gst_rate_val))
            half_gst_rate = gst_val / Decimal("2")
            gst_rate_str = f"{gst_val:f}".rstrip("0").rstrip(".") if "." in f"{gst_val:f}" else f"{gst_val}"
            half_rate_str = f"{half_gst_rate:f}".rstrip("0").rstrip(".") if "." in f"{half_gst_rate:f}" else f"{half_gst_rate}"

            computed_cgst = (item.line_total * half_gst_rate / Decimal("100")).quantize(Decimal("0.01"))
            cgst_val = item.cgst_amount if (item.cgst_amount and item.cgst_amount > 0) else computed_cgst
            sgst_val = item.sgst_amount if (item.sgst_amount and item.sgst_amount > 0) else computed_cgst
        else:
            gst_rate_str = ""
            half_rate_str = ""
            cgst_val = Decimal("0.00")
            sgst_val = Decimal("0.00")

        computed_cgst_total += cgst_val
        computed_sgst_total += sgst_val

        qty_dec = Decimal(str(item.quantity))
        if qty_dec == qty_dec.to_integral():
            qty_str = format_indian_currency(qty_dec, decimals=0)
        else:
            qty_str = format_indian_currency(qty_dec, decimals=3)

        lines.append(
            {
                "line_no": item.line_no,
                "description": item.product_name or (item.product.name if item.product else ""),
                "hsn_sac": item.hsn_sac or "",
                "gst_rate": gst_rate_val,
                "gst_rate_str": gst_rate_str,
                "half_rate_str": half_rate_str,
                "quantity": item.quantity,
                "quantity_str": qty_str,
                "unit_name": unit,
                "rate": item.rate,
                "rate_formatted": format_indian_currency(item.rate),
                "line_total": item.line_total,
                "line_total_formatted": format_indian_currency(item.line_total),
                "cgst_amount": cgst_val,
                "cgst_amount_formatted": format_indian_currency(cgst_val),
                "sgst_amount": sgst_val,
                "sgst_amount_formatted": format_indian_currency(sgst_val),
            }
        )

    # Tax breakdown rows
    tax_rows = []
    if is_gst:
        rate_map: dict = {}
        for line in lines:
            if line["gst_rate"] is None:
                continue
            rate_key = str(line["gst_rate"])
            if rate_key not in rate_map:
                rate_map[rate_key] = {
                    "rate": line["gst_rate"],
                    "rate_str": line["gst_rate_str"],
                    "half_rate": line["half_rate_str"],
                    "taxable": Decimal("0.00"),
                    "cgst": Decimal("0.00"),
                    "sgst": Decimal("0.00"),
                    "total_tax": Decimal("0.00"),
                }
            rate_map[rate_key]["taxable"] += line["line_total"]
            rate_map[rate_key]["cgst"] += line["cgst_amount"]
            rate_map[rate_key]["sgst"] += line["sgst_amount"]
            rate_map[rate_key]["total_tax"] += (line["cgst_amount"] + line["sgst_amount"])

        for row in rate_map.values():
            row["taxable_formatted"] = format_indian_currency(row["taxable"])
            row["cgst_formatted"] = format_indian_currency(row["cgst"])
            row["sgst_formatted"] = format_indian_currency(row["sgst"])
            row["total_tax_formatted"] = format_indian_currency(row["total_tax"])
            tax_rows.append(row)

    if is_gst:
        final_cgst = invoice.total_cgst if (invoice.total_cgst and invoice.total_cgst > 0) else computed_cgst_total
        final_sgst = invoice.total_sgst if (invoice.total_sgst and invoice.total_sgst > 0) else computed_sgst_total
        final_tax = final_cgst + final_sgst
        final_round_off = invoice.round_off if invoice.round_off is not None else Decimal("0.00")
        final_grand_total = (subtotal + final_tax + final_round_off).quantize(Decimal("1.00"))
    else:
        final_cgst = Decimal("0.00")
        final_sgst = Decimal("0.00")
        final_tax = Decimal("0.00")
        final_round_off = invoice.round_off if invoice.round_off is not None else Decimal("0.00")
        final_grand_total = (subtotal + final_round_off).quantize(Decimal("1.00"))

    from apps.payments.models import PaymentAllocation
    from django.db.models import Sum

    try:
        alloc_sum = (
            PaymentAllocation.objects.filter(invoice_id=invoice.id).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
    except Exception:
        alloc_sum = Decimal("0.00")

    advance_amount = getattr(invoice, "advance_amount", Decimal("0.00")) or Decimal("0.00")
    total_paid = max(alloc_sum, advance_amount)
    balance_amount = max(Decimal("0.00"), final_grand_total - total_paid)

    grand_words = grand_total_in_words(final_grand_total)
    tax_words = grand_total_in_words(final_tax) if final_tax > 0 else ""

    total_qty_str = (
        format_indian_currency(total_qty, decimals=0)
        if total_qty == total_qty.to_integral()
        else format_indian_currency(total_qty, decimals=3)
    )

    has_advance = (advance_amount > Decimal("0.00"))
    has_payment = (total_paid > Decimal("0.00"))
    show_advance_separate = has_advance and (total_paid > advance_amount)

    # Dynamic spacer height calibrated so the entire invoice fits in exactly 1 page
    num_lines = len(lines)
    extra_rows = 0
    if has_payment or has_advance:
        extra_rows += 2
        if show_advance_separate:
            extra_rows += 1
    adv_offset = extra_rows * 9

    if is_gst and tax_rows:
        if num_lines == 1:
            spacer_height = max(10, 155 - adv_offset)
        elif num_lines == 2:
            spacer_height = max(10, 120 - adv_offset)
        elif num_lines == 3:
            spacer_height = max(10, 90 - adv_offset)
        elif num_lines == 4:
            spacer_height = max(10, 60 - adv_offset)
        else:
            spacer_height = 12
    else:
        if num_lines == 1:
            spacer_height = max(15, 210 - adv_offset)
        elif num_lines == 2:
            spacer_height = max(15, 175 - adv_offset)
        elif num_lines == 3:
            spacer_height = max(15, 140 - adv_offset)
        elif num_lines == 4:
            spacer_height = max(15, 105 - adv_offset)
        else:
            spacer_height = 15

    # Keep the declaration block near the bottom of the footer, as in the
    # client's sample, while giving long invoices room for their lines.
    footer_spacer_height = max(16, 90 - max(0, num_lines - 1) * 8)

    formatted_invoice = {
        "invoice_number": invoice.invoice_number or f"{invoice.id}",
        "invoice_date": invoice.invoice_date,
        "invoice_type": inv_type,
        "notes": invoice.notes,
        "subtotal": subtotal,
        "subtotal_formatted": format_indian_currency(subtotal),
        "total_cgst": final_cgst,
        "total_cgst_formatted": format_indian_currency(final_cgst),
        "total_sgst": final_sgst,
        "total_sgst_formatted": format_indian_currency(final_sgst),
        "total_tax": final_tax,
        "total_tax_formatted": format_indian_currency(final_tax),
        "round_off": final_round_off,
        "round_off_formatted": format_indian_currency(final_round_off),
        "grand_total": final_grand_total,
        "grand_total_formatted": format_indian_currency(final_grand_total),
        "advance_amount": advance_amount,
        "advance_amount_formatted": format_indian_currency(advance_amount),
        "total_paid": total_paid,
        "total_paid_formatted": format_indian_currency(total_paid),
        "balance_amount": balance_amount,
        "balance_amount_formatted": format_indian_currency(balance_amount),
        "has_advance": has_advance,
        "has_payment": has_payment,
        "show_advance_separate": show_advance_separate,
    }

    context = {
        "invoice": invoice,
        "inv": formatted_invoice,
        "is_draft": is_draft,
        "is_gst": is_gst,
        "biz": biz,
        "biz_state": biz_state,
        "biz_state_code": biz_state_code,
        "cust": cust_data,
        "cust_state_code": cust_state_code,
        "consignee": consignee_data,
        "dispatch": dispatch_data,
        "lines": lines,
        "logo_path": logo_path,
        "logo_width": logo_width,
        "logo_height": logo_height,
        "seal_path": seal_path,
        "signature_path": signature_path,
        **_font_face_paths(),
        "spacer_height": spacer_height,
        "footer_spacer_height": footer_spacer_height,
        "total_quantity": total_qty,
        "total_quantity_str": total_qty_str,
        "primary_unit": primary_unit,
        "grand_total_words": grand_words,
        "tax_total_words": tax_words,
        "tax_rows": tax_rows,
    }

    html = render_to_string("invoices/invoice.html", context)

    from xhtml2pdf import pisa
    pdf_buffer = BytesIO()
    pisa.CreatePDF(html, dest=pdf_buffer, link_callback=pisa_link_callback)
    return pdf_buffer.getvalue()
