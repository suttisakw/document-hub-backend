# Backend API Endpoint Catalog

This catalog documents the endpoints currently used by frontend integration.
Examples focus on Matching, Matching Rules, Taxonomy, OCR workflow.

## Auth

All endpoints below require `Authorization: Bearer <token>` unless explicitly public.

---

## Documents

### GET `/documents/`

Query params:
- `limit`, `offset`
- `q`, `status`, `type`
- `created_from`, `created_to`
- `confidence_min`, `confidence_max`
- `sort_by` (`created_at|updated_at|name|confidence`), `sort_order` (`asc|desc`)

Response:
```json
{
  "items": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "name": "invoice-a",
      "type": "invoice",
      "status": "processing",
      "file_path": "...",
      "file_size": 12345,
      "mime_type": "application/pdf",
      "pages": 2,
      "confidence": 94.3,
      "created_at": "2026-02-12T10:00:00"
    }
  ],
  "total": 120,
  "limit": 25,
  "offset": 0
}
```

### POST `/documents/export`

Request:
```json
{
  "document_ids": ["uuid-1", "uuid-2"]
}
```

Response: zip stream + headers:
- `X-Requested-Count`
- `X-Exported-Count`

---

## OCR Workflow

### GET `/ocr/jobs`

Query params:
- `provider`
- `status`
- `document_id`
- `limit`, `offset`

Response: `OcrJobWithDocumentResponse[]`

### GET `/ocr/jobs/queue`

Returns only active queue jobs: `triggered` + `running`

### GET `/ocr/jobs/history`

Returns only terminal jobs: `completed`, `error`, `cancelled`

### POST `/ocr/jobs/{job_id}/retry`

Retries a failed OCR job (`status == error`) and returns new job payload.

### POST `/ocr/jobs/{job_id}/cancel`

Cancels an active OCR job (`pending|triggered|running`).

Sample response:
```json
{
  "id": "uuid",
  "document_id": "uuid",
  "provider": "easyocr",
  "status": "cancelled",
  "requested_at": "2026-02-12T10:00:00",
  "completed_at": "2026-02-12T10:01:00",
  "error_message": "Cancelled by user"
}
```

### GET `/ocr/jobs/{job_id}/result`

Returns normalized result envelope for a job:
```json
{
  "job_id": "uuid",
  "document_id": "uuid",
  "provider": "external",
  "status": "completed",
  "requested_at": "...",
  "completed_at": "...",
  "error_message": null,
  "result_json": {"status": true, "result": []}
}
```

### POST `/ocr/webhook/external`

External OCR callback endpoint.
- Validates webhook secret (global or per-interface)
- Resolves job via `request_id` or `transaction_id`
- Applies extracted structured result to `ExtractedField`

---

## Matching

### GET `/matching/sets`
### POST `/matching/sets`
### GET `/matching/sets/{set_id}`
### PATCH `/matching/sets/{set_id}`
### DELETE `/matching/sets/{set_id}`
### POST `/matching/sets/{set_id}/documents`
### DELETE `/matching/sets/{set_id}/documents/{document_id}`
### GET `/matching/unmatched`
### POST `/matching/auto-match`

Create set sample:
```json
{
  "name": "Set A",
  "status": "review"
}
```

Add documents sample:
```json
{
  "document_ids": ["uuid-1", "uuid-2"]
}
```

---

## Matching Rules

### GET `/matching/rules`
### POST `/matching/rules`
### GET `/matching/rules/{rule_id}`
### PATCH `/matching/rules/{rule_id}`
### DELETE `/matching/rules/{rule_id}`
### POST `/matching/rules/{rule_id}/enable`
### POST `/matching/rules/{rule_id}/disable`
### POST `/matching/rules/{rule_id}/test`

Rule create sample:
```json
{
  "name": "Invoice Number Match",
  "description": "Match by invoice number",
  "enabled": true,
  "doc_types": ["invoice"],
  "conditions": [
    {
      "left_field": "invoice_number",
      "operator": "equals",
      "right_field": "invoice_number",
      "sort_order": 0
    }
  ],
  "fields": []
}
```

Rule test sample:
```json
{
  "document_ids": ["uuid-1", "uuid-2", "uuid-3"]
}
```

Rule test response sample:
```json
{
  "matches": [
    {
      "left_document_id": "uuid-1",
      "right_document_id": "uuid-2",
      "left_name": "Invoice A",
      "right_name": "Invoice B"
    }
  ],
  "evaluated_pairs": 1,
  "matched_pairs": 1,
  "skipped_pairs": 2,
  "applied_doc_types": ["invoice"]
}
```

---

## Taxonomy

### Categories
- `GET /taxonomy/categories`
- `GET /taxonomy/categories/stats`
- `POST /taxonomy/categories`
- `PATCH /taxonomy/categories/{category_id}`
- `DELETE /taxonomy/categories/{category_id}`

### Tags
- `GET /taxonomy/tags`
- `GET /taxonomy/tags/stats`
- `POST /taxonomy/tags`
- `PATCH /taxonomy/tags/{tag_id}`
- `DELETE /taxonomy/tags/{tag_id}`

### Groups
- `GET /taxonomy/groups`
- `POST /taxonomy/groups`
- `PATCH /taxonomy/groups/{group_id}`
- `DELETE /taxonomy/groups/{group_id}`
- `GET /taxonomy/groups/{group_id}/documents`
- `POST /taxonomy/groups/{group_id}/documents`
