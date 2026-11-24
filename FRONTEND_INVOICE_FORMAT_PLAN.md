# Frontend Changes Plan — Invoice Format (finalinv.pdf)

The backend now renders the invoice PDF in the client's `finalinv.pdf` layout.
The frontend does **not** need to build the invoice grid itself; it needs to
collect the extra header fields and download the PDF from the document endpoint.

---

## 1. Company settings screen

Add five inputs to the existing business-profile / settings form.

| UI label | API field | Type | Notes |
|---|---|---|---|
| State | `state` | select | Indian state/UT list; default `Tamil Nadu` |
| A/c Holder's Name | `bank_holder_name` | text | printed under Company's Bank Details |
| Bank Name | `bank_name` | text | printed under Company's Bank Details |
| A/c No. | `bank_account_no` | text | printed under Company's Bank Details |
| Branch & IFS Code | `bank_ifsc` | text | printed under Company's Bank Details |

- Endpoint: `PATCH /api/settings/company/` (Admin only), `GET` for all signed-in users.
- Use `multipart/form-data` when a logo is also being uploaded, otherwise JSON is fine.
- The existing logo upload stays unchanged. A logo that already contains the
  business name is fine: the PDF shows the logo in the header and the business
  name once in the `From` block.

**Acceptance:** after saving, `GET /api/settings/company/` returns the five values
and the invoice PDF shows them in the footer/bank block and in
`State Name : <state> , Code : <GST state code>`.

---

## 2. Invoice create / edit form

The backend already accepts these fields. Add them to the form (all optional)
and send them in `POST /api/invoices/` and `PATCH /api/invoices/{id}/`.

### 2.1 Invoice meta (right-hand grid in the PDF)

| UI label | API field | Type |
|---|---|---|
| Invoice No. | `invoice_number` | text (leave blank to auto-number) |
| Dated | `invoice_date` | date (required) |
| Delivery Note | `delivery_note` | text |
| Mode/Terms of Payment | `payment_terms` | text |
| Reference No. & Date. | `reference_no_date` | text |
| Other References | `other_references` | text |
| Buyer's Order No. | `buyer_order_no` | text |
| Dated (order) | `order_date` | date |
| Dispatch Doc No. | `dispatch_doc_no` | text |
| Delivery Note Date | `delivery_note_date` | date |

### 2.2 Transport block (right-hand lower grid)

| UI label | API field | Type |
|---|---|---|
| Dispatched through | `dispatched_through` | text |
| Destination | `destination` | text |
| Bill of Lading/LR-RR No. | `bill_of_lading_no` | text |
| Motor Vehicle No. | `motor_vehicle_no` | text |
| Terms of Delivery | `terms_of_delivery` | textarea |

### 2.3 Optional consignee block (not printed in the current layout)

The API accepts `consignee_name`, `consignee_address`, `consignee_gstin`,
`consignee_state`, `consignee_state_code`. Keep the fields if they already exist
in the form; they are not part of the current `finalinv.pdf` layout.

### 2.4 Items

No change. Keep sending `lines: [{ product, quantity, rate, gst_rate?, hsn_sac?,
unit_name?, description? }]`. The backend calculates all totals.

**Suggested layout:** put the new fields in a collapsible "Dispatch & References"
section below the customer/date row so the normal create flow stays short.

---

## 3. Invoice detail / preview screen

1. Replace any hand-built invoice preview with the server PDF:
   - `GET /api/invoices/{id}/document/`
   - authenticated fetch with `credentials: 'include'`
   - render in an `<iframe>` / `<embed>` or open as a blob URL
   - show a "Print / Download" button
2. Show the saved dispatch fields in the detail view (read-only), so the user can
   confirm what will print.
3. Draft invoices still return a PDF with the red `DRAFT` watermark. Show a
   "Draft — not a valid tax invoice" banner next to the preview.

### Download helper (already documented in `API_CONTRACT.md`)

```js
async function downloadInvoicePdf(invoiceId) {
  const res = await fetch(`/api/invoices/${invoiceId}/document/`, {
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Could not load invoice PDF');
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, '_blank');
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
```

---

## 4. Field-to-PDF map

| PDF area | Source |
|---|---|
| Header logo | Company settings `logo` |
| "In the name of Allah" | fixed text |
| GST INVOICE / INVOICE | `invoice_type` (`GST` / `NON_GST`) |
| (ORIGINAL FOR RECIPIENT) | fixed text; DRAFT when `status = DRAFT` |
| From block | business snapshot (`business_name`, `address`, `gstin`, `state`, `phone`, `email`) |
| Buyer (Bill to) | customer snapshot (`name`, `billing_address`, `gstin`, `state`, `phone`) |
| Invoice No. / Dated | `invoice_number`, `invoice_date` |
| Delivery Note / Mode | `delivery_note`, `payment_terms` |
| Reference / Other | `reference_no_date`, `other_references` |
| Buyer's Order No. / Dated | `buyer_order_no`, `order_date` |
| Dispatch Doc No. / Delivery Note Date | `dispatch_doc_no`, `delivery_note_date` |
| Dispatched through / Destination | `dispatched_through`, `destination` |
| Bill of Lading / Motor Vehicle | `bill_of_lading_no`, `motor_vehicle_no` |
| Terms of Delivery | `terms_of_delivery` |
| Item rows | invoice item snapshots |
| Totals, tax table, words | server-calculated invoice fields |
| Bank details | company settings `bank_*` |
| Seal / signature | `media/company/seal.png`, `media/company/signature.png` |

---

## 5. Testing checklist

- [ ] Save state + bank details as Admin; verify non-admin gets `403`.
- [ ] Create an invoice with every dispatch field; PDF shows each value.
- [ ] Create an invoice with blank optional fields; PDF rows remain blank and aligned.
- [ ] Issue a GST invoice with 18% lines; PDF shows CGST/SGST rows, tax table and ₹ totals.
- [ ] Issue a non-GST invoice; PDF uses the non-GST layout.
- [ ] Open a draft; PDF shows the DRAFT watermark.
- [ ] Download/print from the browser; one US Letter page for a short invoice.
