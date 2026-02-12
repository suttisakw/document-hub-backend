# Database Schema Design สำหรับ Document Hub OCR System

## 📊 Entity Relationship Diagram

```
┌─────────────┐
│    Users    │
├─────────────┤
│ id (PK)     │
│ email       │
│ name        │
│ password    │
│ created_at  │
│ updated_at  │
└──────┬──────┘
       │
       │ 1:N
┌──────▼──────────────┐
│    Documents       │
├────────────────────┤
│ id (PK)            │
│ user_id (FK)       │
│ name               │
│ type               │
│ status             │
│ file_path          │
│ file_size          │
│ pages              │
│ confidence         │
│ scanned_at         │
│ created_at         │
│ updated_at         │
└──────┬─────────────┘
       │
       │ 1:N
┌──────▼──────────────┐
│  Document_Pages    │
├────────────────────┤
│ id (PK)            │
│ document_id (FK)   │
│ page_number        │
│ image_path         │
│ width              │
│ height             │
└──────┬─────────────┘
       │
       │ 1:N
┌──────▼──────────────┐
│  Extracted_Fields  │
├────────────────────┤
│ id (PK)            │
│ document_id (FK)   │
│ page_id (FK)       │
│ field_name         │
│ field_value        │
│ confidence         │
│ bbox_x             │
│ bbox_y             │
│ bbox_width         │
│ bbox_height        │
│ is_edited          │
│ created_at         │
│ updated_at         │
└─────────────────────┘

┌─────────────────────┐
│  Matching_Rules    │
├─────────────────────┤
│ id (PK)            │
│ name               │
│ description        │
│ enabled            │
│ doc_types          │ (JSON array)
│ conditions         │ (JSON)
│ fields             │ (JSON)
│ created_at         │
│ updated_at         │
└──────┬─────────────┘
       │
       │ 1:N
┌──────▼──────────────┐
│  Matched_Sets      │
├─────────────────────┤
│ id (PK)            │
│ rule_id (FK)       │
│ name               │
│ status             │
│ matched_at         │
│ created_at         │
│ updated_at         │
└──────┬─────────────┘
       │
       │ N:M
┌──────▼──────────────┐
│ Matched_Documents  │
├─────────────────────┤
│ id (PK)            │
│ matched_set_id(FK) │
│ document_id (FK)   │
│ created_at         │
└─────────────────────┘

┌─────────────────────┐
│  Input_Interfaces  │
├─────────────────────┤
│ id (PK)            │
│ name               │
│ type               │
│ enabled            │
│ config             │ (JSON)
│ created_at         │
│ updated_at         │
└─────────────────────┘

┌─────────────────────┐
│  Output_APIs       │
├─────────────────────┤
│ id (PK)            │
│ name               │
│ endpoint           │
│ method             │
│ format             │
│ enabled            │
│ headers            │ (JSON)
│ field_mapping      │ (JSON)
│ created_at         │
│ updated_at         │
└─────────────────────┘
```

---

## 📝 SQL Schema (PostgreSQL)

### Users Table

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
```

### Documents Table

```sql
CREATE TYPE document_status AS ENUM (
    'pending',
    'processing',
    'scanned',
    'verified',
    'matched',
    'error'
);

CREATE TYPE document_type AS ENUM (
    'Invoice',
    'Receipt',
    'Contract',
    'PO',
    'Tax Invoice',
    'Quotation',
    'Other'
);

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(500) NOT NULL,
    type document_type NOT NULL,
    status document_status NOT NULL DEFAULT 'pending',
    file_path VARCHAR(1000) NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(100),
    pages INTEGER DEFAULT 1,
    confidence DECIMAL(5,2),
    scanned_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_type ON documents(type);
CREATE INDEX idx_documents_created_at ON documents(created_at DESC);
```

### Document Pages Table

```sql
CREATE TABLE document_pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    image_path VARCHAR(1000),
    width INTEGER,
    height INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, page_number)
);

CREATE INDEX idx_document_pages_document_id ON document_pages(document_id);
```

### Extracted Fields Table

```sql
CREATE TABLE extracted_fields (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_id UUID REFERENCES document_pages(id) ON DELETE SET NULL,
    field_name VARCHAR(255) NOT NULL,
    field_value TEXT,
    confidence DECIMAL(5,2),
    bbox_x DECIMAL(10,2),
    bbox_y DECIMAL(10,2),
    bbox_width DECIMAL(10,2),
    bbox_height DECIMAL(10,2),
    is_edited BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_extracted_fields_document_id ON extracted_fields(document_id);
CREATE INDEX idx_extracted_fields_page_id ON extracted_fields(page_id);
CREATE INDEX idx_extracted_fields_field_name ON extracted_fields(field_name);
```

### Matching Rules Table

```sql
CREATE TABLE matching_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    doc_types JSONB NOT NULL, -- Array of document types
    conditions JSONB NOT NULL, -- Array of condition objects
    fields JSONB NOT NULL, -- Array of field definitions
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_matching_rules_enabled ON matching_rules(enabled);
```

### Matched Sets Table

```sql
CREATE TYPE matched_set_status AS ENUM (
    'complete',
    'partial',
    'review'
);

CREATE TABLE matched_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID REFERENCES matching_rules(id) ON DELETE SET NULL,
    name VARCHAR(500) NOT NULL,
    status matched_set_status NOT NULL DEFAULT 'review',
    matched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_matched_sets_rule_id ON matched_sets(rule_id);
CREATE INDEX idx_matched_sets_status ON matched_sets(status);
```

### Matched Documents Table (Junction Table)

```sql
CREATE TABLE matched_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    matched_set_id UUID NOT NULL REFERENCES matched_sets(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(matched_set_id, document_id)
);

CREATE INDEX idx_matched_documents_set_id ON matched_documents(matched_set_id);
CREATE INDEX idx_matched_documents_document_id ON matched_documents(document_id);
```

### Input Interfaces Table

```sql
CREATE TYPE interface_type AS ENUM (
    'sftp',
    'rest_api',
    'blob_storage',
    's3',
    'ftp'
);

CREATE TABLE input_interfaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    type interface_type NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    config JSONB NOT NULL, -- Flexible config storage
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_input_interfaces_enabled ON input_interfaces(enabled);
```

### Output APIs Table

```sql
CREATE TYPE http_method AS ENUM ('GET', 'POST', 'PUT', 'PATCH', 'DELETE');
CREATE TYPE output_format AS ENUM ('json', 'xml', 'csv');

CREATE TABLE output_apis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    endpoint VARCHAR(1000) NOT NULL,
    method http_method NOT NULL DEFAULT 'POST',
    format output_format NOT NULL DEFAULT 'json',
    enabled BOOLEAN DEFAULT TRUE,
    headers JSONB, -- Custom headers
    field_mapping JSONB, -- Field mapping configuration
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_output_apis_enabled ON output_apis(enabled);
```

---

## 🔄 Drizzle ORM Schema (Node.js)

```typescript
// schema.ts
import { pgTable, uuid, varchar, timestamp, integer, decimal, boolean, jsonb, pgEnum } from 'drizzle-orm/pg-core';
import { relations } from 'drizzle-orm';

export const documentStatusEnum = pgEnum('document_status', [
  'pending',
  'processing',
  'scanned',
  'verified',
  'matched',
  'error'
]);

export const documentTypeEnum = pgEnum('document_type', [
  'Invoice',
  'Receipt',
  'Contract',
  'PO',
  'Tax Invoice',
  'Quotation',
  'Other'
]);

export const users = pgTable('users', {
  id: uuid('id').primaryKey().defaultRandom(),
  email: varchar('email', { length: 255 }).notNull().unique(),
  name: varchar('name', { length: 255 }).notNull(),
  passwordHash: varchar('password_hash', { length: 255 }).notNull(),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow(),
});

export const documents = pgTable('documents', {
  id: uuid('id').primaryKey().defaultRandom(),
  userId: uuid('user_id').notNull().references(() => users.id, { onDelete: 'cascade' }),
  name: varchar('name', { length: 500 }).notNull(),
  type: documentTypeEnum('type').notNull(),
  status: documentStatusEnum('status').notNull().default('pending'),
  filePath: varchar('file_path', { length: 1000 }).notNull(),
  fileSize: integer('file_size').notNull(),
  mimeType: varchar('mime_type', { length: 100 }),
  pages: integer('pages').default(1),
  confidence: decimal('confidence', { precision: 5, scale: 2 }),
  scannedAt: timestamp('scanned_at', { withTimezone: true }),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow(),
});

export const documentPages = pgTable('document_pages', {
  id: uuid('id').primaryKey().defaultRandom(),
  documentId: uuid('document_id').notNull().references(() => documents.id, { onDelete: 'cascade' }),
  pageNumber: integer('page_number').notNull(),
  imagePath: varchar('image_path', { length: 1000 }),
  width: integer('width'),
  height: integer('height'),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
});

export const extractedFields = pgTable('extracted_fields', {
  id: uuid('id').primaryKey().defaultRandom(),
  documentId: uuid('document_id').notNull().references(() => documents.id, { onDelete: 'cascade' }),
  pageId: uuid('page_id').references(() => documentPages.id, { onDelete: 'set null' }),
  fieldName: varchar('field_name', { length: 255 }).notNull(),
  fieldValue: varchar('field_value', { length: 5000 }),
  confidence: decimal('confidence', { precision: 5, scale: 2 }),
  bboxX: decimal('bbox_x', { precision: 10, scale: 2 }),
  bboxY: decimal('bbox_y', { precision: 10, scale: 2 }),
  bboxWidth: decimal('bbox_width', { precision: 10, scale: 2 }),
  bboxHeight: decimal('bbox_height', { precision: 10, scale: 2 }),
  isEdited: boolean('is_edited').default(false),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow(),
});

// Relations
export const usersRelations = relations(users, ({ many }) => ({
  documents: many(documents),
}));

export const documentsRelations = relations(documents, ({ one, many }) => ({
  user: one(users, {
    fields: [documents.userId],
    references: [users.id],
  }),
  pages: many(documentPages),
  extractedFields: many(extractedFields),
}));
```

---

## 🐍 SQLModel Schema (Python)

```python
# models.py
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime
from enum import Enum
from pydantic import EmailStr

class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SCANNED = "scanned"
    VERIFIED = "verified"
    MATCHED = "matched"
    ERROR = "error"

class DocumentType(str, Enum):
    INVOICE = "Invoice"
    RECEIPT = "Receipt"
    CONTRACT = "Contract"
    PO = "PO"
    TAX_INVOICE = "Tax Invoice"
    QUOTATION = "Quotation"
    OTHER = "Other"

class User(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)
    email: EmailStr = Field(unique=True, index=True)
    name: str
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    documents: List["Document"] = Relationship(back_populates="user")

class Document(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    name: str
    type: DocumentType
    status: DocumentStatus = DocumentStatus.PENDING
    file_path: str
    file_size: int
    mime_type: Optional[str] = None
    pages: int = 1
    confidence: Optional[float] = None
    scanned_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    user: User = Relationship(back_populates="documents")
    pages: List["DocumentPage"] = Relationship(back_populates="document")
    extracted_fields: List["ExtractedField"] = Relationship(back_populates="document")

class DocumentPage(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)
    document_id: str = Field(foreign_key="document.id")
    page_number: int
    image_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    document: Document = Relationship(back_populates="pages")
    extracted_fields: List["ExtractedField"] = Relationship(back_populates="page")

class ExtractedField(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)
    document_id: str = Field(foreign_key="document.id")
    page_id: Optional[str] = Field(default=None, foreign_key="documentpage.id")
    field_name: str
    field_value: Optional[str] = None
    confidence: Optional[float] = None
    bbox_x: Optional[float] = None
    bbox_y: Optional[float] = None
    bbox_width: Optional[float] = None
    bbox_height: Optional[float] = None
    is_edited: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    document: Document = Relationship(back_populates="extracted_fields")
    page: Optional[DocumentPage] = Relationship(back_populates="extracted_fields")
```

---

## 🔍 Indexes และ Performance Optimization

### Recommended Indexes:

```sql
-- Composite indexes for common queries
CREATE INDEX idx_documents_user_status ON documents(user_id, status);
CREATE INDEX idx_documents_type_status ON documents(type, status);
CREATE INDEX idx_extracted_fields_doc_field ON extracted_fields(document_id, field_name);

-- Full-text search (if needed)
CREATE INDEX idx_documents_name_fts ON documents USING gin(to_tsvector('english', name));

-- Partial indexes for active records
CREATE INDEX idx_documents_active ON documents(status) WHERE status IN ('pending', 'processing');
```

---

## 📊 Sample Queries

### Get Dashboard Stats

```sql
-- Total documents
SELECT COUNT(*) FROM documents WHERE user_id = $1;

-- Documents by status
SELECT status, COUNT(*) 
FROM documents 
WHERE user_id = $1 
GROUP BY status;

-- Recent documents
SELECT * FROM documents 
WHERE user_id = $1 
ORDER BY created_at DESC 
LIMIT 10;
```

### Get Document with Fields

```sql
SELECT 
    d.*,
    json_agg(
        json_build_object(
            'id', ef.id,
            'field_name', ef.field_name,
            'field_value', ef.field_value,
            'confidence', ef.confidence,
            'bbox', json_build_object(
                'x', ef.bbox_x,
                'y', ef.bbox_y,
                'width', ef.bbox_width,
                'height', ef.bbox_height
            )
        )
    ) as fields
FROM documents d
LEFT JOIN extracted_fields ef ON d.id = ef.document_id
WHERE d.id = $1
GROUP BY d.id;
```

---

## 🔐 Security Considerations

1. **Password Hashing**: ใช้ bcrypt หรือ argon2
2. **File Paths**: เก็บใน S3, ไม่เก็บ absolute paths
3. **SQL Injection**: ใช้ parameterized queries (ORM handles this)
4. **Data Validation**: Validate inputs ด้วย Pydantic/Zod
5. **Access Control**: Row-level security สำหรับ multi-tenant

---

*Schema นี้รองรับทั้ง Node.js (Drizzle) และ Python (SQLModel)*

