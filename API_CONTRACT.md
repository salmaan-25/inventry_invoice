# Billing & Inventory Management System (V1)
# Complete Frontend API Contract & Integration Guide

**Base URL (Local Development):** `http://localhost:8000`  
**API Prefix:** `/api`  
**Date Format:** `YYYY-MM-DD` (ISO-8601 calendar date)  
**Money Precision:** Exact 2-decimal string (e.g. `"1250.00"`)  
**Quantity Precision:** Exact 3-decimal string (e.g. `"10.500"`)  

---

## 1. Authentication & Security Handshake

The application uses **Django Session Authentication** with secure HTTP cookies (`sessionid` and `csrftoken`). **Never store tokens or credentials in `localStorage` or `sessionStorage`.**

### Protocol Rules for the Frontend:
1. **Credentials:** Set `credentials: 'include'` on **every** network call (handled automatically by `fetchBaseQuery({ credentials: 'include' })`).
2. **CSRF Handshake:** Before making login or mutation requests (`POST`, `PATCH`), perform `GET /api/auth/csrf/` once. Read the `csrftoken` cookie and attach it as the `X-CSRFToken` HTTP header on all subsequent mutation calls.
3. **Session Check:** On initial app boot, call `GET /api/auth/me/`. If HTTP 200, the user is already authenticated. If HTTP 401, redirect to `/login`.

```typescript
// Example: src/api/baseApi.ts (RTK Query)
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

function getCsrfToken(): string | null {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : null;
}

export const baseApi = createApi({
  reducerPath: 'api',
  baseQuery: fetchBaseQuery({
    baseUrl: 'http://localhost:8000/api',
    credentials: 'include',
    prepareHeaders: (headers, { endpoint }) => {
      const csrfToken = getCsrfToken();
      if (csrfToken) {
        headers.set('X-CSRFToken', csrfToken);
      }
      return headers;
    },
  }),
  tagTypes: [
    'Auth', 'Company', 'Customer', 'Product', 'StockMovement',
    'Invoice', 'DeliveryChallan', 'Payment', 'Expense',
    'ExpenseCategory', 'OtherIncome', 'OtherIncomeCategory',
    'Dashboard', 'Report',
  ],
  endpoints: () => ({}),
});
```

---

## 2. Standard Response Envelopes & Error Handling

### 2.1. Paginated List Response (`StandardPagination`)
Every list endpoint returns this shape:
```json
{
  "count": 42,
  "next": "http://localhost:8000/api/products/?page=2",
  "previous": null,
  "results": [ ... ]
}
```
Query parameters supported by all paginated endpoints:
- `?page=1` (1-based index)
- `?page_size=25` (Default: 25, Max: 100)

### 2.2. Error Responses
All 4xx/5xx errors return a uniform schema:

#### Validation Error (HTTP 400):
```json
{
  "code": "VALIDATION_ERROR",
  "detail": "Invalid input.",
  "field_errors": {
    "phone": ["Phone number must be between 10 and 15 digits."],
    "name": ["This field is required."]
  }
}
```

#### Business Rule / Domain Error (HTTP 400):
```json
{
  "code": "INSUFFICIENT_STOCK",
  "detail": "Product P0001 (Motor 5HP) only has 2.000 in stock; 5.000 requested.",
  "field_errors": {}
}
```

#### Common Error Codes:
- `NOT_AUTHENTICATED` (401): Not logged in or session expired.
- `PERMISSION_DENIED` (403): User lacks permissions (e.g. staff accessing admin settings).
- `NOT_FOUND` (404): Resource not found.
- `THROTTLED` (429): Login rate-limit reached (5 attempts/minute).
- `INVALID_DATE_RANGE` (400): `from` is after `to` or invalid date format.
- `INSUFFICIENT_STOCK` (400): Issuing invoice with inadequate goods stock.
- `OVER_DISPATCH` (400): Challan quantity exceeds ordered invoice line remaining balance.
- `OVER_ALLOCATION` (400): Payment allocation sum exceeds total payment amount.

---

## 3. Global Enums & Constants

| Enum Name | Values | Notes |
|---|---|---|
| `Role` | `"ADMIN"`, `"STAFF"` | User authorization role |
| `ItemType` | `"GOODS"`, `"GOODS_HARDWARE"`, `"SERVICE"` | Service items do not track stock |
| `InvoiceStatus` | `"DRAFT"`, `"ISSUED"` | Once ISSUED, invoice is immutable |
| `PaymentStatus` | `"UNPAID"`, `"PARTIALLY_PAID"`, `"PAID"` | Dynamic invoice payment state |
| `PaymentMethod` | `"CASH"`, `"BANK_TRANSFER"`, `"UPI"`, `"CHEQUE"` | Customer payments (NEFT/RTGS/IMPS use `"BANK_TRANSFER"`) |
| `MovementType` | `"OPENING_STOCK"`, `"STOCK_IN"`, `"STOCK_OUT"`, `"ADJUSTMENT"` | Stock ledger audit types |

---

## 4. Complete API Endpoint Specifications

---

### Phase 1: Authentication & Staff Management

#### 1. Obtain CSRF Cookie
- **Endpoint:** `GET /api/auth/csrf/`
- **Access:** Public
- **Response (200 OK):**
```json
{
  "detail": "CSRF cookie set."
}
```

#### 2. User Login
- **Endpoint:** `POST /api/auth/login/`
- **Access:** Public (Throttled: 5 attempts/min)
- **Request Body:**
```json
{
  "username": "admin_user",
  "password": "Password123!"
}
```
- **Response (200 OK):**
```json
{
  "id": 1,
  "username": "admin_user",
  "full_name": "Admin Mohamed",
  "role": "ADMIN"
}
```

#### 3. User Logout
- **Endpoint:** `POST /api/auth/logout/`
- **Access:** Authenticated
- **Response (200 OK):**
```json
{
  "detail": "Logged out successfully."
}
```

#### 4. Current User Session (`Me`)
- **Endpoint:** `GET /api/auth/me/`
- **Access:** Authenticated
- **Response (200 OK):**
```json
{
  "id": 1,
  "username": "admin_user",
  "full_name": "Admin Mohamed",
  "role": "ADMIN"
}
```

#### 5. List Business Staff / Employees
- **Endpoint:** `GET /api/staff/`
- **Access:** Admin or Staff
- **Query Params:** `?search=`, `?all=true`
- **Response (200 OK):**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "employee_id": "EMP-001",
      "name": "Kaviarasan",
      "contact": "9876543210",
      "notes": "Foreman",
      "created_at": "2026-11-22T12:00:00Z",
      "updated_at": "2026-11-22T12:00:00Z"
    }
  ]
}
```

#### 6. Create Employee
- **Endpoint:** `POST /api/staff/`
- **Access:** Admin or Staff
- **Request Body:**
```json
{
  "employee_id": "EMP-002",
  "name": "Venkatesh",
  "contact": "9123456780",
  "notes": "Carpenter"
}
```
- **Response (201 Created):** Returns created employee object.

#### 7. Update Employee
- **Endpoint:** `PATCH /api/staff/{id}/`
- **Access:** Admin or Staff
- **Request Body:**
```json
{
  "name": "Venkatesh Kumar",
  "contact": "9999988888"
}
```
- **Response (200 OK):** Returns updated employee object.

#### 8. Delete Employee
- **Endpoint:** `DELETE /api/staff/{id}/`
- **Access:** Admin or Staff
- **Response (200 OK):**
```json
{
  "detail": "Employee Venkatesh (EMP-002) deleted successfully."
}
```

---

### Phase 2: Company Settings (Business Profile)

#### 1. Retrieve Company Profile
- **Endpoint:** `GET /api/company/`
- **Access:** Authenticated (Staff or Admin)
- **Response (200 OK):**
```json
{
  "id": 1,
  "business_name": "Salmaan Tech Solutions",
  "logo": "http://localhost:8000/media/company/logos/logo.png",
  "address": "123 Commercial Road, Chennai, Tamil Nadu",
  "state": "Tamil Nadu",
  "phone": "044-24567890",
  "email": "contact@salmaantech.com",
  "gstin": "33AAAAA0000A1Z5",
  "bank_holder_name": "Salmaan Tech Solutions",
  "bank_name": "State Bank of India",
  "bank_account_no": "1234567890123",
  "bank_ifsc": "SBIN0001234",
  "updated_at": "2026-11-20T10:00:00Z"
}
```

#### 2. Update Company Profile
- **Endpoint:** `PATCH /api/company/`
- **Access:** Admin only
- **Content-Type:** `multipart/form-data` (if updating logo) or `application/json`
- **Request Form Data:**
  - `business_name`: string
  - `address`: string
  - `state`: string (one of the Indian states/UTs; printed on invoices)
  - `phone`: string
  - `email`: string
  - `gstin`: string (15-character valid Indian GSTIN)
  - `bank_holder_name`: string (printed on invoices)
  - `bank_name`: string (printed on invoices)
  - `bank_account_no`: string (printed on invoices)
  - `bank_ifsc`: string (printed on invoices)
  - `logo`: File (PNG or JPG under 2MB, optional)
- **Response (200 OK):** Updated company profile object.

---

### Phase 3: Customer Management

#### 1. List Customers
- **Endpoint:** `GET /api/customers/`
- **Access:** Authenticated
- **Query Params:** `?search=` (matches name, code, phone), `?is_active=true|false`, `?page=`, `?page_size=`
- **Response (200 OK):**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "code": "C0001",
      "name": "Acme Corp Pvt Ltd",
      "phone": "9840123456",
      "gstin": "33ABCDE1234F1Z5",
      "state": "Tamil Nadu",
      "billing_address": "45 Industrial Estate, Guindy, Chennai",
      "is_active": true,
      "created_at": "2026-11-20T10:00:00Z",
      "updated_at": "2026-11-20T10:00:00Z"
    }
  ]
}
```

#### 2. Create Customer
- **Endpoint:** `POST /api/customers/`
- **Access:** Authenticated
- **Request Body:**
```json
{
  "name": "Acme Corp Pvt Ltd",
  "phone": "9840123456",
  "gstin": "33ABCDE1234F1Z5",
  "state": "Tamil Nadu",
  "billing_address": "45 Industrial Estate, Guindy, Chennai"
}
```
*Note: `code` is auto-generated by the backend (`C0001`, `C0002`). Client input for `code` is ignored.*
- **Response (201 Created):** Returns created customer object.

#### 3. Customer Detail
- **Endpoint:** `GET /api/customers/{id}/`
- **Access:** Authenticated
- **Response (200 OK):** Full customer object.

#### 4. Update Customer
- **Endpoint:** `PATCH /api/customers/{id}/`
- **Access:** Authenticated
- **Request Body:** Partial fields (`name`, `phone`, `gstin`, `state`, `billing_address`, `is_active`).
- **Response (200 OK):** Updated customer object.

#### 5. Customer Invoices (All Invoices)
- **Endpoint:** `GET /api/customers/{id}/invoices/`
- **Access:** Authenticated
- **Query Params:** `?status=ISSUED|DRAFT`, `?page=`, `?page_size=`
- **Response (200 OK):** Paginated list of all invoices for this customer.
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 15,
      "invoice_number": "AT/26-27/005",
      "invoice_date": "2026-11-22",
      "status": "ISSUED",
      "grand_total": "8000.00",
      "paid_amount": "8000.00",
      "balance_due": "0.00",
      "payment_status": "PAID"
    }
  ]
}
```

#### 6. Customer Open Invoices (For Payment Allocation)
- **Endpoint:** `GET /api/customers/{id}/open-invoices/`
- **Access:** Authenticated
- **Response (200 OK):** Lists all `ISSUED` invoices with an outstanding balance.
```json
[
  {
    "id": 10,
    "invoice_number": "INV-2026-0001",
    "invoice_date": "2026-11-15",
    "grand_total": "11800.00",
    "total_paid": "5000.00",
    "balance_due": "6800.00"
  }
]
```

#### 7. Customer Ledger Statement
- **Endpoint:** `GET /api/customers/{id}/statement/`
- **Access:** Authenticated
- **Query Params:** `?from=YYYY-MM-DD&to=YYYY-MM-DD` (Optional date filter)
- **Response (200 OK):**
```json
{
  "customer": {
    "id": 1,
    "code": "C0001",
    "name": "Acme Corp Pvt Ltd"
  },
  "total_invoiced": "25000.00",
  "total_paid": "15000.00",
  "outstanding_balance": "10000.00",
  "entries": [
    {
      "date": "2026-11-10",
      "type": "INVOICE",
      "reference": "INV-2026-0001",
      "debit": "11800.00",
      "credit": "0.00",
      "running_balance": "11800.00"
    },
    {
      "date": "2026-11-12",
      "type": "PAYMENT",
      "reference": "PAY-1",
      "debit": "0.00",
      "credit": "5000.00",
      "running_balance": "6800.00"
    }
  ]
}
```

---

### Phase 4: Products & Inventory Management

#### 1. List Measurement Units
- **Endpoint:** `GET /api/units/`
- **Access:** Authenticated
- **Response (200 OK):**
```json
{
  "count": 4,
  "next": null,
  "previous": null,
  "results": [
    { "id": 1, "name": "piece" },
    { "id": 2, "name": "kg" },
    { "id": 3, "name": "meter" },
    { "id": 4, "name": "hour" }
  ]
}
```

#### 2. List Products
- **Endpoint:** `GET /api/products/`
- **Access:** Authenticated
- **Query Params:**
  - `?search=` (matches name or code)
  - `?item_type=GOODS|GOODS_HARDWARE|SERVICE`
  - `?is_active=true|false`
  - `?low_stock=true` (filters products at or below reorder level)
- **Response (200 OK):**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "code": "P0001",
      "name": "Copper Cable 2.5mm",
      "description": "Insulated copper wire",
      "item_type": "GOODS",
      "unit": 3,
      "unit_name": "meter",
      "selling_price": "45.00",
      "hsn_sac": "8544",
      "gst_rate": "18.00",
      "reorder_level": "100.000",
      "current_stock": "450.000",
      "is_low_stock": false,
      "is_active": true
    }
  ]
}
```

#### 3. Create Product
- **Endpoint:** `POST /api/products/`
- **Access:** Authenticated
- **Request Body:**
```json
{
  "name": "Copper Cable 2.5mm",
  "code": "",
  "description": "Insulated copper wire",
  "item_type": "GOODS",
  "unit": 3,
  "selling_price": "45.00",
  "hsn_sac": "8544",
  "gst_rate": "18.00",
  "reorder_level": "100.000",
  "opening_stock": "500.000"
}
```
*Notes:*
- If `code` is blank, the backend auto-generates sequential `P0001`, `P0002`.
- `opening_stock` is optional and write-only; it automatically logs an `OPENING_STOCK` movement.
- If `item_type` is `"SERVICE"`, `opening_stock` and `reorder_level` must not be sent.
- **Response (201 Created):** Created product object.

#### 4. Update Product
- **Endpoint:** `PATCH /api/products/{id}/`
- **Access:** Authenticated
- **Request Body:** Partial fields (`name`, `description`, `selling_price`, `hsn_sac`, `gst_rate`, `reorder_level`, `is_active`).
- *Note: `current_stock` and `opening_stock` cannot be modified via PATCH.*
- **Response (200 OK):** Updated product object.

#### 5. Add Physical Stock (`Stock-In`)
- **Endpoint:** `POST /api/products/{id}/stock-in/`
- **Access:** Authenticated
- **Request Body:**
```json
{
  "quantity": "50.000",
  "reason": "PO #1043 Vendor Delivery"
}
```
- **Response (200 OK):** Updated product object with new `current_stock`.

#### 6. Stock Adjustment (`Audit / Correction`)
- **Endpoint:** `POST /api/products/{id}/adjust/`
- **Access:** Authenticated
- **Request Body:**
```json
{
  "quantity_change": "-5.000",
  "reason": "Damaged in warehouse audit"
}
```
*Note: `reason` is required. `quantity_change` can be positive (e.g. `"+10.000"`) or negative (e.g. `"-5.000"`). Stock cannot fall below 0.*
- **Response (200 OK):** Updated product object.

#### 7. Stock Movement Audit Ledger
- **Endpoint:** `GET /api/stock-movements/`
- **Access:** Authenticated
- **Query Params:** `?product=`, `?from=YYYY-MM-DD`, `?to=YYYY-MM-DD`
- **Response (200 OK):**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "product": 1,
      "product_name": "Copper Cable 2.5mm",
      "product_code": "P0001",
      "movement_type": "STOCK_IN",
      "quantity_change": "50.000",
      "balance_after": "500.000",
      "reason": "PO #1043 Vendor Delivery",
      "invoice": null,
      "created_by_name": "Admin Mohamed",
      "created_at": "2026-11-20T11:00:00Z"
    }
  ]
}
```

---

### Phase 5: Invoicing Engine

#### 1. Stateless Calculation Preview
Use this while the user is typing line items in the invoice creation screen to dynamically preview tax and total values without database saves.
- **Endpoint:** `POST /api/invoices/calculate/`
- **Access:** Authenticated
- **Request Body:**
```json
{
  "customer": 1,
  "lines": [
    {
      "product": 1,
      "quantity": "10.000",
      "rate": "100.00"
    }
  ]
}
```
*Note: `customer` is optional. If `rate` is omitted or null, the product's current selling price is automatically used.*
- **Response (200 OK):**
```json
{
  "is_gst": true,
  "subtotal": "1000.00",
  "cgst_amount": "90.00",
  "sgst_amount": "90.00",
  "total_tax": "180.00",
  "round_off": "0.00",
  "grand_total": "1180.00",
  "lines": [
    {
      "line_no": 1,
      "product_name": "Copper Cable 2.5mm",
      "quantity": "10.000",
      "rate": "100.00",
      "gst_rate": "18.00",
      "line_total": "1000.00",
      "cgst_amount": "90.00",
      "sgst_amount": "90.00"
    }
  ]
}
```

#### 2. List Invoices
- **Endpoint:** `GET /api/invoices/`
- **Access:** Authenticated
- **Query Params:** `?status=DRAFT|ISSUED`, `?customer=`, `?from=YYYY-MM-DD`, `?to=YYYY-MM-DD`, `?page=`, `?page_size=`
- **Response (200 OK):**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "invoice_number": "INV-2026-0001",
      "customer": 1,
      "customer_name": "Acme Corp Pvt Ltd",
      "invoice_date": "2026-11-20",
      "status": "ISSUED",
      "subtotal": "1000.00",
      "total_cgst": "90.00",
      "total_sgst": "90.00",
      "total_tax": "180.00",
      "round_off": "0.00",
      "grand_total": "1180.00",
      "paid_amount": "0.00",
      "balance_due": "1180.00",
      "payment_status": "UNPAID",
      "delivery_status": "PENDING",
      "created_at": "2026-11-20T10:00:00Z",
      "updated_at": "2026-11-20T14:30:00Z"
    }
  ]
}
```

#### 3. Invoice Detail
- **Endpoint:** `GET /api/invoices/{id}/`
- **Access:** Authenticated
- **Response (200 OK):** Complete Invoice DTO:
```json
{
  "id": 1,
  "invoice_number": "INV-2026-0001",
  "customer": 1,
  "customer_name": "Acme Corp Pvt Ltd",
  "invoice_date": "2026-11-20",
  "notes": "Payment terms: Net 15 days",
  "status": "ISSUED",
  "subtotal": "1000.00",
  "total_cgst": "90.00",
  "total_sgst": "90.00",
  "total_tax": "180.00",
  "round_off": "0.00",
  "grand_total": "1180.00",
  "paid_amount": "0.00",
  "balance_due": "1180.00",
  "payment_status": "UNPAID",
  "delivery_status": "PENDING",
  "business_snapshot": {
    "business_name": "My Enterprise",
    "address": "123 Business St, Chennai",
    "state": "Tamil Nadu",
    "phone": "044-24567890",
    "email": "contact@myenterprise.com",
    "gstin": "33AAAAA0000A1Z5",
    "logo": "company/logos/logo.png",
    "bank_holder_name": "My Enterprise",
    "bank_name": "State Bank of India",
    "bank_account_no": "1234567890123",
    "bank_ifsc": "SBIN0001234"
  },
  "customer_snapshot": {
    "code": "C0001",
    "name": "Acme Corp Pvt Ltd",
    "phone": "9876543210",
    "gstin": "33BBBBB1111B1Z2",
    "state": "Tamil Nadu",
    "billing_address": "456 Client Ave, Chennai"
  },
  "items": [
    {
      "id": 1,
      "line_no": 1,
      "product": 1,
      "product_name": "Copper Cable 2.5mm",
      "product_code": "P0001",
      "hsn_sac": "8544",
      "unit_name": "meter",
      "item_type": "GOODS",
      "gst_rate": "18.00",
      "quantity": "10.000",
      "rate": "100.00",
      "line_total": "1000.00",
      "cgst_amount": "90.00",
      "sgst_amount": "90.00"
    }
  ],
  "created_by": 1,
  "created_at": "2026-11-20T10:00:00Z",
  "updated_at": "2026-11-20T14:30:00Z",
  "issued_by": 1,
  "issued_by_name": "Admin Mohamed",
  "issued_at": "2026-11-20T14:30:00Z"
}
```

#### 4. Create Draft Invoice
- **Endpoint:** `POST /api/invoices/`
- **Access:** Authenticated
- **Request Body:**
```json
{
  "customer": 1,
  "invoice_date": "2026-11-20",
  "invoice_number": "INV-2026-0001",
  "invoice_type": "GST",
  "notes": "Payment terms: Net 15 days",

  "consignee_name": "",
  "consignee_address": "",
  "consignee_gstin": "",
  "consignee_state": "Tamil Nadu",
  "consignee_state_code": "33",

  "e_way_bill_no": "",
  "delivery_note": "DN-1",
  "payment_terms": "30 Days",
  "reference_no_date": "REF-1 01-11-26",
  "other_references": "",
  "buyer_order_no": "PO-123",
  "order_date": "2026-11-01",
  "dispatch_doc_no": "DD-9",
  "delivery_note_date": "2026-11-20",
  "dispatched_through": "Lorry",
  "destination": "Chennai",
  "bill_of_lading_no": "LR-77",
  "motor_vehicle_no": "TN 01 AB 1234",
  "terms_of_delivery": "FOB Chennai",

  "advance_amount": "0.00",
  "lines": [
    {
      "product": 1,
      "quantity": "10.000",
      "rate": "100.00"
    }
  ]
}
```
*Note: The key is `lines` (matching calculate preview). All totals (`line_total`, `cgst`, `sgst`, `grand_total`) are calculated and secured by the server. All dispatch/consignee fields are optional and are printed in the invoice's header grid exactly as supplied.*
- **Response (201 Created):** Full invoice object (same schema as GET invoice detail) with `status: "DRAFT"`.

#### 5. Update Draft Invoice
- **Endpoint:** `PATCH /api/invoices/{id}/`
- **Access:** Authenticated
- **Request Body:** Partial update of `customer`, `invoice_date`, `notes`, or replace the entire `lines` array.
- *Error:* Returns HTTP 400 if the invoice is already `ISSUED`.
- **Response (200 OK):** Full updated invoice object.

#### 6. Issue Invoice (Finalize & Deduct Stock)
- **Endpoint:** `POST /api/invoices/{id}/issue/`
- **Access:** Authenticated
- **Request Body:** Empty `{}`
- **Behavior:**
  - Atomically verifies stock. If insufficient, returns HTTP 400 `INSUFFICIENT_STOCK` and nothing changes.
  - Decrements product stock in a single transaction.
  - Takes immutable snapshots of business and customer details.
  - Sets `status` to `"ISSUED"`.
- **Response (200 OK):** Full finalized invoice object.

#### 7. Download / View PDF Invoice
- **Endpoint:** `GET /api/invoices/{id}/document/`
- **Access:** Authenticated
- **Response:** Binary PDF stream (`Content-Type: application/pdf`).
  - Drafts include a diagonal **"DRAFT"** watermark.
  - Issued invoices render clean tax invoice formats based on customer GST status.

#### 8. Remaining Dispatch Quantities
- **Endpoint:** `GET /api/invoices/{id}/awaiting-dispatch/`
- **Access:** Authenticated
- **Response (200 OK):** Shows goods items not yet dispatched.
```json
[
  {
    "invoice_item_id": 1,
    "product_name": "Copper Cable 2.5mm",
    "unit": "meter",
    "invoiced_quantity": "10.000",
    "already_dispatched": "4.000",
    "remaining_quantity": "6.000"
  }
]
```

---

### Phase 6: Delivery Challans (Dispatch Documents)

#### 1. List Delivery Challans
- **Endpoint:** `GET /api/challans/`
- **Access:** Authenticated
- **Query Params:** `?invoice=`, `?customer=`, `?from=`, `?to=`, `?page=`, `?page_size=`
- **Response (200 OK):**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "invoice": 1,
      "invoice_number": "INV-2026-0001",
      "invoice_date": "2026-11-20",
      "customer": 1,
      "customer_name": "Acme Corp Pvt Ltd",
      "delivery_date": "2026-11-20",
      "delivered_by": "Ramesh (Driver - TN09-1234)",
      "received_by": "Security Gate #2",
      "created_by": 1,
      "created_by_name": "Admin Mohamed",
      "created_at": "2026-11-20T15:00:00Z"
    }
  ]
}
```

#### 2. Create Delivery Challan
- **Endpoint:** `POST /api/challans/`
- **Access:** Authenticated
- **Request Body:**
```json
{
  "invoice": 1,
  "delivery_date": "2026-11-20",
  "delivered_by": "Ramesh (Driver - TN09-1234)",
  "received_by": "Security Gate #2",
  "items": [
    {
      "invoice_item": 1,
      "quantity": "6.000"
    }
  ]
}
```
*Note: Validates that `quantity` does not exceed the remaining undispatched balance.*
- **Response (201 Created):** Full challan object with `items`.

#### 3. Challan Detail
- **Endpoint:** `GET /api/challans/{id}/`
- **Access:** Authenticated
- **Response (200 OK):** Full challan object:
```json
{
  "id": 1,
  "invoice": 1,
  "invoice_number": "INV-2026-0001",
  "invoice_date": "2026-11-20",
  "customer": 1,
  "customer_name": "Acme Corp Pvt Ltd",
  "delivery_date": "2026-11-20",
  "delivered_by": "Ramesh (Driver - TN09-1234)",
  "received_by": "Security Gate #2",
  "created_by": 1,
  "created_by_name": "Admin Mohamed",
  "created_at": "2026-11-20T15:00:00Z",
  "items": [
    {
      "id": 1,
      "invoice_item": 1,
      "line_no": 1,
      "product": 1,
      "product_name": "Copper Cable 2.5mm",
      "product_code": "P0001",
      "hsn_sac": "8544",
      "unit_name": "meter",
      "item_type": "GOODS",
      "quantity": "6.000"
    }
  ]
}
```

#### 4. Download / View PDF Challan
- **Endpoint:** `GET /api/challans/{id}/document/`
- **Access:** Authenticated
- **Response:** Binary PDF stream (`Content-Type: application/pdf`).

---

### Phase 7: Customer Payments & Multi-Invoice Allocations

#### 1. List Payments
- **Endpoint:** `GET /api/payments/`
- **Access:** Authenticated
- **Query Params:** `?customer=`, `?from=`, `?to=`, `?page=`, `?page_size=`
- **Response (200 OK):**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "customer": 1,
      "customer_name": "Acme Corp Pvt Ltd",
      "payment_date": "2026-11-20",
      "amount": "1180.00",
      "method": "BANK_TRANSFER",
      "reference": "UTR987654321",
      "note": "Payment for INV-2026-0001",
      "client_token": "e7c1f8b2-5401-4439-847e-8c65910fa098",
      "received_by": 1,
      "received_by_name": "Admin Mohamed",
      "created_at": "2026-11-20T16:00:00Z"
    }
  ]
}
```

#### 2. Payment Detail
- **Endpoint:** `GET /api/payments/{id}/`
- **Access:** Authenticated
- **Response (200 OK):** Full payment object with allocations:
```json
{
  "id": 1,
  "customer": 1,
  "customer_name": "Acme Corp Pvt Ltd",
  "payment_date": "2026-11-20",
  "amount": "1180.00",
  "method": "BANK_TRANSFER",
  "reference": "UTR987654321",
  "note": "Payment for INV-2026-0001",
  "client_token": "e7c1f8b2-5401-4439-847e-8c65910fa098",
  "received_by": 1,
  "received_by_name": "Admin Mohamed",
  "created_at": "2026-11-20T16:00:00Z",
  "allocations": [
    {
      "id": 1,
      "invoice": 1,
      "invoice_number": "INV-2026-0001",
      "invoice_date": "2026-11-20",
      "grand_total": "1180.00",
      "amount": "1180.00"
    }
  ]
}
```

#### 3. Record Customer Payment
- **Endpoint:** `POST /api/payments/`
- **Access:** Authenticated
- **Request Body:**
```json
{
  "customer": 1,
  "payment_date": "2026-11-20",
  "amount": "1180.00",
  "method": "BANK_TRANSFER",
  "reference": "UTR987654321",
  "note": "Payment for INV-2026-0001",
  "client_token": "e7c1f8b2-5401-4439-847e-8c65910fa098",
  "allocations": [
    {
      "invoice": 1,
      "amount": "1180.00"
    }
  ]
}
```
*Rules:*
- `method`: Must be one of `"CASH"`, `"BANK_TRANSFER"`, `"UPI"`, `"CHEQUE"`. (Electronic transfers like NEFT/RTGS/IMPS use `"BANK_TRANSFER"`).
- `client_token`: Client-generated UUID to guarantee idempotent retries.
- Sum of `allocations[].amount` must exactly match the payment `amount`.
- Invoices must belong to the specified `customer` and be in `ISSUED` status.
- Cannot allocate more than the remaining balance due on each invoice.
- **Response (201 Created):** Full created payment object (with `allocations`).

---

### Phase 8 & 9: Expenses & Other Income

#### 1. Expense Categories
- `GET /api/expense-categories/` — List categories (Returns flat array `ExpenseCategory[]`, **not** paginated):
```json
[
  { "id": 1, "name": "Rent", "is_active": true },
  { "id": 2, "name": "Electricity", "is_active": true }
]
```
- `POST /api/expense-categories/` — Create category (Admin only, body: `{"name": "Fuel"}`)

#### 2. List Expenses
- **Endpoint:** `GET /api/expenses/`
- **Access:** Authenticated
- **Query Params:** `?search=`, `?category=`, `?from=YYYY-MM-DD`, `?to=YYYY-MM-DD`, `?page=`, `?page_size=`
- **Response (200 OK):**
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "total_amount": "6200.50",
  "results": [
    {
      "id": 1,
      "date": "2026-11-20",
      "category": 1,
      "category_name": "Rent",
      "description": "Warehouse monthly lease",
      "payment_method": "BANK_TRANSFER",
      "paid_to": "Landlord Realtors",
      "amount": "5000.00",
      "created_at": "2026-11-20T10:00:00Z"
    }
  ]
}
```
*Note: `total_amount` is the database sum of all filtered records across all pages.*

#### 3. Expense Detail & Edit
- `GET /api/expenses/{id}/` — Retrieve single expense.
- `PATCH /api/expenses/{id}/` — Partial update (`date`, `category`, `description`, `amount`, `payment_method`, `paid_to`, `notes`).
- **Response (200 OK):** Updated expense object.

#### 4. Create Expense
- **Endpoint:** `POST /api/expenses/`
- **Access:** Authenticated
- **Request Body:**
```json
{
  "date": "2026-11-20",
  "category": 1,
  "description": "Warehouse monthly lease",
  "amount": "5000.00",
  "payment_method": "BANK_TRANSFER",
  "paid_to": "Landlord Realtors",
  "notes": "Ref: Nov 2026"
}
```
- **Response (201 Created):** Created expense object.

#### 5. Export Expenses to Excel (.xlsx)
- **Endpoint:** `GET /api/expenses/export/?from=YYYY-MM-DD&to=YYYY-MM-DD`
- **Access:** Authenticated
- **Response:** Binary `.xlsx` workbook stream.

#### 6. Income Categories
- `GET /api/income-categories/` — List income categories (Returns flat array `IncomeCategory[]`, **not** paginated).
- `POST /api/income-categories/` — Create income category (Admin only, body: `{"name": "Scrap Sale"}`).

#### 7. Other Income List, Detail, Create & Edit
- `GET /api/other-income/?from=&to=&category=&search=` — Returns paginated list + `total_amount`.
- `GET /api/other-income/{id}/` — Retrieve single other income record.
- `PATCH /api/other-income/{id}/` — Partial update (`date`, `category`, `description`, `amount`, `payment_method`, `received_from`, `notes`).
- `POST /api/other-income/` — Create other income:
```json
{
  "date": "2026-11-20",
  "category": 1,
  "description": "Sold scrap packaging material",
  "amount": "800.00",
  "payment_method": "CASH",
  "received_from": "Local Recyclers"
}
```
- `GET /api/other-income/export/?from=YYYY-MM-DD&to=YYYY-MM-DD` — Export to `.xlsx`.

*Note on DELETE Endpoints:* By design (D14 compliance & accounting audit trail), financial records (invoices, challans, payments, expenses, income) are never hard-deleted. Entities supporting deactivation (staff, customers, products, categories) use `is_active: false` via `PATCH`.

---

### Phase 10: Executive Dashboard

#### 1. Retrieve Dashboard Figures
- **Endpoint:** `GET /api/dashboard/`
- **Access:** Authenticated (Staff or Admin)
- **Response (200 OK):**
```json
{
  "as_of": "2026-11-20",
  "today_sales": "1180.00",
  "month_sales": {
    "amount": "45200.00",
    "invoice_count": 14
  },
  "month_payments_received": "32000.00",
  "outstanding_amount": "13200.00",
  "stock": {
    "tracked_product_count": 48,
    "low_stock_count": 3
  },
  "month_expenses": "8450.00",
  "month_other_income": "1200.00",
  "open_challans_to_dispatch": 0,
  "recent_invoices": [
    {
      "id": 14,
      "invoice_number": "INV-2026-0014",
      "invoice_date": "2026-11-20",
      "customer_name": "Acme Corp Pvt Ltd",
      "grand_total": "1180.00",
      "payment_status": "UNPAID"
    }
  ],
  "low_stock_products": [
    {
      "id": 5,
      "name": "Safety Switches 16A",
      "current_stock": "4.000",
      "reorder_level": "20.000",
      "unit": "piece"
    }
  ]
}
```

---

## 5. Summary Checklist for Frontend Development

1. **Authentication Flow (RTK Query):**
   - Call `GET /api/auth/csrf/` at app start.
   - Dispatch `login` mutation to `/api/auth/login/` with username and password.
   - Store user info in Redux `authSlice` (never store passwords or session keys).
   - Check `/api/auth/me/` on app initialization.
2. **Numbers & Calculations:**
   - Always treat money returned from backend as strings.
   - For real-time invoice previews, hit `POST /api/invoices/calculate/` with `{ customer, lines }` so the backend math (CGST, SGST, roundoff) matches the final printed invoice without saving to DB.
3. **Draft vs Issued Invoices:**
   - If `invoice.status === 'DRAFT'`: Show "Edit", "Add Lines", "Issue Invoice" buttons.
   - If `invoice.status === 'ISSUED'`: Disable editing, show "Print PDF", "Generate Delivery Challan", and "Awaiting Dispatch".
4. **File Downloads (PDF & Excel):**
   - For binary file downloads (PDF documents and Excel exports), use a raw authenticated fetch helper configured with `credentials: 'include'`:
   ```typescript
   export async function downloadFile(url: string, filename: string): Promise<void> {
     const response = await fetch(url, {
       method: 'GET',
       credentials: 'include',
     });
     if (!response.ok) throw new Error('Download failed');
     const blob = await response.blob();
     const blobUrl = window.URL.createObjectURL(blob);
     const link = document.createElement('a');
     link.href = blobUrl;
     link.download = filename;
     document.body.appendChild(link);
     link.click();
     link.remove();
     window.URL.revokeObjectURL(blobUrl);
   }
   ```
