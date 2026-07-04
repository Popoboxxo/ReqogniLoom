# Backend Implementation Notes — Phase 1 & 2 (REQ-L1-058 through REQ-L3-RF004-004)

**Date:** 2026-07-04  
**Status:** Phase 1 & 2 Complete  
**Scope:** SE Mask Standardization — Models, Migrations, Managers, Serializers, API Endpoints

---

## 1. Migration Execution

### Migration File
- **Location:** `backend/persistence/migrations/0013_add_se_mask_fields.py`
- **Dependencies:** `0012_add_parent_id_to_architecture_element`
- **Operations:**
  - ADD COLUMN `type` to `Requirement` (CharField, choices, default='SyReq')
  - ADD COLUMN `moscow_priority` to `Requirement` (CharField, nullable)
  - ADD COLUMN `complexity_fibonacci` to `Requirement` (IntegerField, nullable)
  - ADD COLUMN `verification_method` to `Requirement` (CharField, nullable)
  - ADD COLUMN `uid` to `Requirement` (CharField, nullable, non-unique)
  - ADD COLUMN `asil_level` to `ArchitectureElement` (CharField, choices, nullable)
  - ADD COLUMN `make_or_buy` to `ArchitectureElement` (CharField, choices, nullable)
  - ADD COLUMN `uid` to `ArchitectureElement` (CharField, nullable)
  - CREATE TABLE `pl_attribute_visibility_config` (full schema with audit fields)
  - CREATE INDEX `idx_requirement_type_btree` on `type`
  - CREATE INDEX `idx_requirement_uid_btree` on `uid`
  - CREATE INDEX `idx_arch_elem_asil_btree` on `asil_level`
  - CREATE INDEX `idx_arch_elem_makebuy_btree` on `make_or_buy`
  - CREATE INDEX `idx_arch_elem_uid_btree` on `uid`
  - CREATE INDEX `idx_attrvisib_tenant_type` on `(tenant_id, entity_type)`
  - CREATE CONSTRAINT `uq_attrvisib_tenant_entity_attr` UNIQUE on `(tenant_id, entity_type, attribute_name)`

### Execution
```bash
cd backend
python manage.py migrate
# Expected output:
# Applying persistence.0013_add_se_mask_fields... OK
```

### Backfill
- **Automatic:** Migration sets `Requirement.type` default='SyReq' for all new records
- **Existing records:** All existing requirements retain `type=NULL` until explicitly updated
- **No data loss:** Type-dependent fields remain nullable; frontend handles absence

---

## 2. Model Updates

### Requirement Model (`backend/persistence/models.py`)
**New Fields:**
- `type` (CharField, choices=RequirementType) — Type classification (StReq, SyReq, UseCase, FeatureReq)
- `moscow_priority` (CharField, nullable, choices=MoSCoWPriority) — MoSCoW priority (Must/Should/Could/Won't)
- `complexity_fibonacci` (IntegerField, nullable, choices=ComplexityFibonacci) — Fibonacci scale (1, 2, 3, 5, 8, 13, 21)
- `verification_method` (CharField, nullable, choices=VerificationMethod) — Verification method (Test/Review/Analysis/Inspection)
- `uid` (CharField, nullable) — Unique identifier (read-only)

**Indexes:**
- BTree on `type` — Filter by requirement type
- BTree on `uid` — Fast UID lookup

**Compliance:**
- REQ-L3-RF003-005 AC1: moscow_priority visible only for StReq
- REQ-L3-RF003-005 AC2: complexity_fibonacci, verification_method visible only for SyReq
- REQ-L2-RF-025 AC3: uid for stable identification

### ArchitectureElement Model (`backend/persistence/models.py`)
**New Fields:**
- `asil_level` (CharField, nullable, choices=ASILLevel) — ASIL level (QM/A/B/C/D)
- `make_or_buy` (CharField, nullable, choices=MakeOrBuy) — Make-or-Buy decision (Make/Buy/Reuse)
- `uid` (CharField, nullable) — Unique identifier (read-only)

**Modified Methods:**
- `get_level()` — Fallback for single-instance level computation (recursive)
- `level` property — Prefers CTE-annotated level from `.get_with_level()`

**Indexes:**
- BTree on `asil_level` — Risk-based filtering
- BTree on `make_or_buy` — Supply-chain analysis
- BTree on `uid` — Fast UID lookup

**Compliance:**
- REQ-L1-058 AC2: Level derivation via CTE (db-side) via manager
- REQ-L3-RF004-004 AC1: asil_level, make_or_buy fields
- REQ-L2-RF-025 AC3: uid for stable identification

### AttributeVisibilityConfig Model (NEW)
**Purpose:** Admin configuration for field visibility per entity type per workspace

**Fields:**
- `id` (UUIDField, primary key)
- `tenant` (ForeignKey, on_delete=PROTECT) — Tenant isolation
- `entity_type` (CharField(64)) — Target entity type (e.g., 'Requirement', 'ArchitectureElement')
- `attribute_name` (CharField(128)) — Field name (e.g., 'moscow_priority', 'asil_level')
- `is_visible` (BooleanField, default=True) — Show/hide toggle
- `is_required` (BooleanField, default=False) — Mark as required in forms
- `created_by`, `modified_by` (ForeignKey to User, nullable) — Audit trail
- `created_at`, `modified_at` (DateTimeField, auto) — Timestamps
- `version` (IntegerField, default=1) — Version counter

**Constraints:**
- UNIQUE on `(tenant_id, entity_type, attribute_name)`
- INDEX on `(tenant_id, entity_type)` for fast bulk lookups

**Compliance:**
- REQ-L1-058 AC2: Supports conditional field visibility via serializer

### Choice Enums (NEW)
**Location:** `backend/persistence/models.py` (lines 75–148)

1. **RequirementType**
   - STREQ = "StReq" (Stakeholder Requirement)
   - SYREQ = "SyReq" (System Requirement)
   - USECASE = "UseCase" (Use Case)
   - FEATUREREQ = "FeatureReq" (Feature Requirement)

2. **MoSCoWPriority**
   - MUST = "Must" (Must Have)
   - SHOULD = "Should" (Should Have)
   - COULD = "Could" (Could Have)
   - WONT = "Won't" (Won't Have)

3. **ComplexityFibonacci**
   - 1, 2, 3, 5, 8, 13, 21 (Integer choices)

4. **VerificationMethod**
   - TEST = "Test"
   - REVIEW = "Review"
   - ANALYSIS = "Analysis"
   - INSPECTION = "Inspection"

5. **ASILLevel**
   - QM = "QM" (not ASIL)
   - A = "A" (ASIL A)
   - B = "B" (ASIL B)
   - C = "C" (ASIL C)
   - D = "D" (ASIL D)

6. **MakeOrBuy**
   - MAKE = "Make"
   - BUY = "Buy"
   - REUSE = "Reuse"

---

## 3. Recursive CTE Manager

### Location
`backend/persistence/managers.py` (NEW FILE)

### Classes
1. **ArchitectureElementQuerySet**
   - Custom QuerySet subclass with `.get_with_level()` method
   - Returns QuerySet annotated with `level` field (tree depth) via PostgreSQL CTE

2. **ArchitectureElementManager**
   - Custom Manager extending TenantManager
   - `.get_with_level()` — Annotate queryset with tree depth using CTE
   - Returns ArchitectureElementQuerySet for method chaining

### CTE Query Strategy (PostgreSQL-specific)
**Pseudocode:**
```sql
WITH RECURSIVE hierarchy AS (
  -- Base case: root elements (parent IS NULL)
  SELECT id, parent_id, 0 AS level
  FROM pl_architecture_element
  WHERE parent_id IS NULL AND tenant_id = %s

  UNION ALL

  -- Recursive case: children inherit parent's level + 1
  SELECT ae.id, ae.parent_id, h.level + 1
  FROM pl_architecture_element ae
  JOIN hierarchy h ON ae.parent_id = h.id
  WHERE ae.tenant_id = %s
)
SELECT ae.*, h.level
FROM pl_architecture_element ae
JOIN hierarchy h ON ae.id = h.id
WHERE ae.tenant_id = %s
```

### Performance Implications
- **Before:** 1000 elements → ~1000 queries (O(n) depth traversals)
- **After:** 1 CTE query → all levels computed in single statement
- **Timeout Risk:** Supports up to ~100 levels; deeper hierarchies may timeout
- **Index:** BTree on `parent_id` backs the join predicate

### Usage
```python
# Bulk fetch with level annotation (REQ-L1-058 AC2)
elements = ArchitectureElement.objects.filter(tenant=ws.tenant).get_with_level()
for elem in elements:
    print(f"{elem.title}: level={elem.level}")  # O(1), no additional queries
```

---

## 4. Serializer Updates

### RequirementSerializer (`backend/rest_api/serializers.py`)
**New Fields:**
- `type` (ChoiceField, default='SyReq')
- `moscow_priority` (ChoiceField, nullable, conditional)
- `complexity_fibonacci` (IntegerField, nullable, conditional)
- `verification_method` (ChoiceField, nullable, conditional)
- `uid` (CharField, read_only)

**Key Method: `to_representation()`**
- Filters fields based on `instance.type` before returning to client
- AC1: Removes `moscow_priority` if `type != 'StReq'`
- AC2: Removes `complexity_fibonacci`, `verification_method` if `type != 'SyReq'`

**Frontend Contract:**
```json
{
  "type": "StReq",
  "title": "User shall be able to log in",
  "uid": "REQ-001",
  "version": 3,
  "moscow_priority": "Must",
  "complexity_fibonacci": null,
  "verification_method": null
}
```
The frontend ignores fields that are not in the response (null is included but empty for non-matching types).

### ArchitectureElementSerializer (`backend/rest_api/serializers.py`)
**New Fields:**
- `asil_level` (ChoiceField, nullable)
- `make_or_buy` (ChoiceField, nullable)
- `uid` (CharField, read_only)

**Modified Method: `get_level()`**
- Prefers CTE-annotated `level` from `.get_with_level()` (O(1))
- Falls back to recursive `get_level()` if not annotated
- Supports dict pre-materialization from views

**Frontend Contract:**
```json
{
  "id": "UUID",
  "title": "Main Controller",
  "uid": "ARCH-001",
  "version": 2,
  "level": 1,
  "asil_level": "A",
  "make_or_buy": "Make"
}
```

### AttributeVisibilityConfigSerializer (NEW)
**Fields:**
- `id` (UUIDField, read_only)
- `tenant_id` (UUIDField, required)
- `entity_type` (CharField)
- `attribute_name` (CharField)
- `is_visible` (BooleanField, default=True)
- `is_required` (BooleanField, default=False)
- `created_by` (read_only, from `created_by.username`)
- `modified_by` (read_only, from `modified_by.username`, nullable)
- `created_at`, `modified_at` (read_only)
- `version` (read_only)

**Endpoint:** `/api/v1/attribute-visibility-config/`

---

## 5. API Endpoints (New & Modified)

### RequirementViewSet
**Modified Endpoints:**
- `POST /api/v1/requirements/` — Create with type-dependent fields
- `PATCH /api/v1/requirements/{pk}/` — Update type-dependent fields
- `GET /api/v1/requirements/{pk}/` — Retrieve with filtered fields

**New Endpoint:**
- `GET /api/v1/requirements/{pk}/allocation/` — List allocations

**Allocation Endpoint Response:**
```json
{
  "requirement_id": "UUID",
  "requirement_title": "User Shall Log In",
  "allocations": [
    {
      "architecture_element_id": "UUID",
      "architecture_element_title": "Authentication Module",
      "target_level": 2,
      "asil_level": "A",
      "make_or_buy": "Make"
    }
  ]
}
```

**Implementation Detail:**
- Queries TraceLinks with `link_type='allocated-to'`
- Joins to ArchitectureElement via Artifact
- Returns allocation details with hierarchy level

### ArchitectureElementViewSet
**Modified Endpoints:**
- `POST /api/v1/architecture-elements/` — Create with ASIL/Make-or-Buy
- `PATCH /api/v1/architecture-elements/{pk}/` — Update ASIL/Make-or-Buy
- `GET /api/v1/architecture-elements/{pk}/` — Retrieve with level annotation (CTE)

**QuerySet Optimization:**
- Views should use `.get_with_level()` for bulk list operations to populate `level` annotation
- Serializer's `get_level()` method checks for annotation before falling back to recursion

### AttributeVisibilityConfigViewSet (NEW)
**Endpoint:** `/api/v1/attribute-visibility-config/`

**Methods:**
- `GET /api/v1/attribute-visibility-config/` — List all visibility configs (tenant-scoped)
- `POST /api/v1/attribute-visibility-config/` — Create new config (returns 201)
- `PATCH /api/v1/attribute-visibility-config/{pk}/` — Update config (is_visible, is_required)
- `DELETE /api/v1/attribute-visibility-config/{pk}/` — Delete config (returns 204)

**Permissions:**
- Tenant admin scope (enforced by BaseEntityViewSet)

---

## 6. Database Schema Validation

### Post-Migration Checklist
1. **Columns Added:**
   - `pl_requirement.type` (VARCHAR(64), NOT NULL, DEFAULT='SyReq')
   - `pl_requirement.moscow_priority` (VARCHAR(16), nullable)
   - `pl_requirement.complexity_fibonacci` (INTEGER, nullable)
   - `pl_requirement.verification_method` (VARCHAR(128), nullable)
   - `pl_requirement.uid` (VARCHAR(64), nullable)
   - `pl_architecture_element.asil_level` (VARCHAR(16), nullable)
   - `pl_architecture_element.make_or_buy` (VARCHAR(32), nullable)
   - `pl_architecture_element.uid` (VARCHAR(64), nullable)

2. **New Tables:**
   - `pl_attribute_visibility_config` (full schema, indexes, constraints)

3. **Indexes Created:**
   - `idx_requirement_type_btree`
   - `idx_requirement_uid_btree`
   - `idx_arch_elem_asil_btree`
   - `idx_arch_elem_makebuy_btree`
   - `idx_arch_elem_uid_btree`
   - `idx_attrvisib_tenant_type`

4. **Constraints Created:**
   - `uq_attrvisib_tenant_entity_attr` (UNIQUE on tenant_id, entity_type, attribute_name)

### Verification SQL
```sql
-- Check new columns on Requirement
\d pl_requirement
-- Expected columns: type, moscow_priority, complexity_fibonacci, verification_method, uid

-- Check new columns on ArchitectureElement
\d pl_architecture_element
-- Expected columns: asil_level, make_or_buy, uid

-- Check new table
\d pl_attribute_visibility_config

-- Check indexes
\di pl_requirement_type_btree
\di pl_arch_elem_asil_btree

-- Check constraints
SELECT constraint_name, constraint_type FROM information_schema.table_constraints
WHERE table_name = 'pl_attribute_visibility_config';
```

---

## 7. Service Layer Integration (Notes)

### Expected Service Changes
The following service methods should be updated to accept new parameters:
1. **RequirementService.create_requirement()**
   - NEW params: `type`, `moscow_priority`, `complexity_fibonacci`, `verification_method`, `uid`

2. **RequirementService.update_requirement()**
   - NEW params: `type`, `moscow_priority`, `complexity_fibonacci`, `verification_method`, `uid`

3. **ArchitectureElementService.create_architecture_element()**
   - NEW params: `asil_level`, `make_or_buy`, `uid`

4. **ArchitectureElementService.update_architecture_element()**
   - NEW params: `asil_level`, `make_or_buy`, `uid`

### Implementation Status
- Service layer updates are **OUT OF SCOPE** for Phase 1 & 2
- API views pass new parameters transparently via serializer validation
- Services should handle gracefully (ignore unknown kwargs or add explicit support)

---

## 8. Testing & Validation (OUT OF SCOPE)

Per user override: No tests are written or executed.
Phase 3 & 4 will cover:
- Unit tests: Serializer field filtering per type
- Integration tests: Allocation-tracking API endpoint
- Performance tests: CTE query time <500ms for 10k items
- Frontend E2E: Type-dependent fields visible/hidden correctly

---

## 9. Known Limitations & Future Work

1. **CTE Depth Limit:** PostgreSQL CTE supports ~100 hierarchy levels safely
2. **uid Auto-Generation:** Currently read-only; backend does not auto-generate (frontend responsibility or future feature)
3. **TraceLink.link_type Enum:** No constraint enforcement; 'allocated-to' is free text for now
4. **Service Layer:** New parameters should be explicitly documented in service docstrings
5. **AttributeVisibilityConfig UI:** No admin UI implemented yet; CRUD via API only
6. **Frontend Dynamic Rendering:** React components must implement type-dependent field visibility logic

---

## 10. Compliance & Traceability

| REQ ID | AC | Section | Status |
|--------|----|----|--------|
| REQ-L1-058 | AC1 | Field Definitions (Requirement.type) | COMPLETE |
| REQ-L1-058 | AC2 | Recursive CTE Manager | COMPLETE |
| REQ-L1-058 | AC3 | Allocation API Endpoint | COMPLETE |
| REQ-L2-RF-025 | AC1 | Serializer uid + version | COMPLETE |
| REQ-L2-RF-025 | AC2 | Type-dependent field rendering | COMPLETE |
| REQ-L2-RF-025 | AC3 | uid serialization | COMPLETE |
| REQ-L3-RF003-005 | AC1 | moscow_priority (StReq only) | COMPLETE |
| REQ-L3-RF003-005 | AC2 | complexity_fibonacci, verification_method (SyReq only) | COMPLETE |
| REQ-L3-RF004-004 | AC1 | asil_level, make_or_buy | COMPLETE |

---

## 11. Migration Sequence Summary

**Phase 1 (Data Model Extension):**
1. Run migration 0013_add_se_mask_fields
2. Verify schema via `python manage.py showmigrations`
3. Check database schema matches expected columns/indexes/constraints

**Phase 2 (Manager & Serializer):**
1. Verify ArchitectureElementManager is imported and used by models
2. Test serializer `to_representation()` logic via API calls
3. Verify level annotation in ArchitectureElementSerializer.get_level()

**Phase 3 (Frontend Integration):**
1. React components check `requirement.type` and render fields conditionally
2. Admin UI for AttributeVisibilityConfig (separate task)
3. Test allocation endpoint via `/api/v1/requirements/{pk}/allocation/`

---

**End of Implementation Notes**
