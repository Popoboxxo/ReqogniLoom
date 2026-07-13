# Backend Data Model Design — SE Masks Unification (REQ-L1-058 through REQ-L3-RF004-004)

**Date:** 2026-07-04  
**Status:** Design Phase (No Code Changes)  
**Scope:** Data model extensions for unified SE-mask architecture across 13 entity types

---

## 1. Field Definitions — New Columns

### Requirement Model Extensions

| Field | Type | Null | Default | Purpose | AC Ref |
|-------|------|------|---------|---------|--------|
| `type` | CharField(64) | No | 'SyReq' | Requirement type (StReq, SyReq, UseCase, FeatureReq) | REQ-L3-RF003-005 |
| `moscow_priority` | CharField(16) | Yes | None | MoSCoW priority (Must, Should, Could, Won't) — visible only when type='StReq' | REQ-L3-RF003-005 AC1 |
| `complexity_fibonacci` | IntegerField | Yes | None | Complexity via Fibonacci scale (1, 2, 3, 5, 8, 13, 21) — visible only when type='SyReq' | REQ-L3-RF003-005 AC2 |
| `verification_method` | CharField(128) | Yes | None | Verification method (Test, Review, Analysis, Inspection) — visible only when type='SyReq' | REQ-L3-RF003-005 AC2 |
| `uid` | CharField(64) | Yes | None | Unique identifier (read-only, persisted or derived) | REQ-L2-RF-025 AC3 |

**Indexes:**
- BTree on `type` (filter by requirement type in queries)
- BTree on `uid` (fast UID lookup)

### ArchitectureElement Model Extensions

| Field | Type | Null | Default | Purpose | AC Ref |
|-------|------|------|---------|---------|--------|
| `asil_level` | CharField(16) | Yes | None | ASIL level (QM, A, B, C, D) — visible only for ArchE | REQ-L3-RF004-004 AC1 |
| `make_or_buy` | CharField(32) | Yes | None | Make-or-Buy decision (Make, Buy, Reuse) | REQ-L3-RF004-004 AC1 |
| `uid` | CharField(64) | Yes | None | Unique identifier (read-only, persisted or derived) | REQ-L2-RF-025 AC3 |

**Indexes:**
- BTree on `asil_level` (risk-based filtering)
- BTree on `make_or_buy` (supply-chain analysis)
- BTree on `uid`

### New Model: AttributeVisibilityConfig (Admin Configuration)

**Purpose:** Allows admins to control which type-dependent fields are visible in the UI per entity type per workspace.

| Field | Type | Null | Constraint | Purpose |
|-------|------|------|-----------|---------|
| `id` (PK) | UUIDField | No | default=uuid4 | Primary key |
| `tenant` (FK) | ForeignKey(Tenant) | No | on_delete=PROTECT | Tenant isolation |
| `entity_type` | CharField(64) | No | — | Target entity type (Requirement, ArchitectureElement, TestCase, etc.) |
| `attribute_name` | CharField(128) | No | — | Field name (e.g., 'moscow_priority', 'asil_level') |
| `is_visible` | BooleanField | No | default=True | Show/hide toggle |
| `is_required` | BooleanField | No | default=False | Mark as required in forms |
| `created_at`, `created_by`, `modified_at`, `modified_by`, `version` | AuditFields | — | — | Audit trail |

**Constraints:**
- Unique constraint: `(tenant_id, entity_type, attribute_name)`

**Indexes:**
- Composite BTree: `(tenant_id, entity_type)` for fast bulk config lookups per entity type

---

## 2. Recursive CTE Strategy — Level Derivation (REQ-L1-058 AC2)

### Problem Statement
Current `ArchitectureElement.get_level()` is Python-recursive, causing N+1 queries when fetching bulk requirements. Example: 1000 ArchElements → 1000+ DB roundtrips.

### Solution: PostgreSQL WITH RECURSIVE CTE

**Query Structure (Pseudocode):**

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
WHERE ae.tenant_id = %s;
```

### Implementation Location

1. **Manager Method (persistence/managers.py):**
   - Create `ArchitectureElementManager` with `.get_queryset_with_level()` method
   - Annotates QuerySet with `level` using `Subquery` + `RawSQL` (Django 3.2+) or `Extra`
   - Returns queryset with `level` as computed field

2. **Serializer (rest_framework):**
   - Add `level` as `SerializerMethodField` (read_only=True)
   - Value sourced from annotated queryset (no additional DB calls)

3. **ViewSet:**
   - Override `get_queryset()` to use manager's annotated queryset
   - Ensures level is available for all list/retrieve endpoints

### Example Django ORM Pattern

```python
# Manager method
def get_queryset_with_level(self):
    from django.db.models import OuterRef, Subquery, Value, CharField, Case, When
    
    # Recursive CTE stored as database view or executed inline
    # Returns annotated queryset with 'level' field
    return self.get_queryset().annotate(
        level=RawSQL("""
            (WITH RECURSIVE h AS (...) SELECT level FROM h WHERE id = %s)
        """, [OuterRef('id')])
    )
```

### Performance Implications

- **Before:** 1000 items → ~1000 queries (O(n) depth traversals)
- **After:** 1 CTE query → all levels computed in single statement
- **DB Index:** BTree on `parent_id` backs the join predicate
- **Timeout Risk:** CTE depth limit ~100 levels safe; 1000+ levels may timeout

---

## 3. Allocation-Tracking via TraceLink (REQ-L1-058 AC3)

### Proposed Changes to TraceLink Model

| Change | Type | Details |
|--------|------|---------|
| `link_type` | Existing CharField → Consider CharField with choices | Current: free text; Propose: enum-like with named constants |
| Add typed constant | Code | `LINK_TYPE_ALLOCATED_TO = 'allocated-to'` |

### Allocation Use Case

**API Endpoint:** `GET /api/v1/requirements/{req_id}/allocation/`

Returns all ArchitectureElements a requirement is allocated to, grouped by target level.

**Response Schema (JSON):**

```json
{
  "requirement_id": "UUID",
  "requirement_title": "string",
  "allocations": [
    {
      "architecture_element_id": "UUID",
      "architecture_element_title": "string",
      "target_level": 2,
      "asil_level": "A",
      "make_or_buy": "Make"
    }
  ]
}
```

### Coverage Reporting

**Query Pattern (pseudo-SQL):**

```sql
SELECT 
  r.id, r.title, ae.id, ae.title, 
  COUNT(*) OVER (PARTITION BY r.id) as allocation_count
FROM pl_requirement r
LEFT JOIN pl_tracelink tl ON r.artifact_id = tl.source_id 
  AND tl.link_type = 'allocated-to'
LEFT JOIN pl_artifact art ON tl.target_id = art.id
LEFT JOIN pl_architecture_element ae ON art.id = ae.artifact_id
WHERE r.tenant_id = %s
ORDER BY r.id, ae.id;
```

---

## 4. Serializer Architecture — Dynamic Field Visibility

### Strategy

**Single Universal Serializer with Conditional Fields** (not separate serializers per type)

#### Base Serializer Pattern

```python
class RequirementSerializer(serializers.ModelSerializer):
    # Always included
    id = serializers.UUIDField(read_only=True)
    uid = serializers.CharField(read_only=True)
    version = serializers.IntegerField(read_only=True)
    
    # Conditional: shown based on type
    moscow_priority = serializers.ChoiceField(
        choices=['Must', 'Should', 'Could', 'Won\'t'],
        required=False,
        allow_null=True
    )
    complexity_fibonacci = serializers.IntegerField(
        required=False,
        allow_null=True
    )
    verification_method = serializers.CharField(
        required=False,
        allow_null=True
    )
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        req_type = instance.type
        
        # Filter fields based on type
        if req_type != 'StReq':
            data.pop('moscow_priority', None)
        if req_type != 'SyReq':
            data.pop('complexity_fibonacci', None)
            data.pop('verification_method', None)
        
        return data
```

#### ArchitectureElement Serializer

```python
class ArchitectureElementSerializer(serializers.ModelSerializer):
    # Always included (read-only)
    id = serializers.UUIDField(read_only=True)
    uid = serializers.CharField(read_only=True)
    version = serializers.IntegerField(read_only=True)
    level = serializers.IntegerField(read_only=True)  # from CTE annotation
    
    # Type-dependent fields (shown for all ArchE)
    asil_level = serializers.ChoiceField(
        choices=['QM', 'A', 'B', 'C', 'D'],
        required=False,
        allow_null=True
    )
    make_or_buy = serializers.ChoiceField(
        choices=['Make', 'Buy', 'Reuse'],
        required=False,
        allow_null=True
    )
```

### Frontend Contract

**GET Response:**

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

**Dynamic Rendering Logic (React):**

```javascript
{requirement.type === 'StReq' && (
  <MoSCoWDropdown value={requirement.moscow_priority} />
)}
{requirement.type === 'SyReq' && (
  <>
    <FibonacciSlider value={requirement.complexity_fibonacci} />
    <VerificationMethodDropdown value={requirement.verification_method} />
  </>
)}
```

---

## 5. Migration Sequence

### Phase 1: Data Model Extension (Week 1)

1. **Create Migration: Add new columns**
   ```
   python manage.py makemigrations
   python manage.py migrate
   ```
   - `Requirement.type` (CharField, default='SyReq')
   - `Requirement.moscow_priority` (nullable)
   - `Requirement.complexity_fibonacci` (nullable)
   - `Requirement.verification_method` (nullable)
   - `ArchitectureElement.asil_level` (nullable)
   - `ArchitectureElement.make_or_buy` (nullable)
   - `Requirement.uid` (nullable, unique=False for now)
   - `ArchitectureElement.uid` (nullable)

2. **Create AttributeVisibilityConfig Model**
   - Migration: `CreateAttributeVisibilityConfig`
   - Indexes on `(tenant_id, entity_type)`

3. **Backfill Defaults**
   - `UPDATE pl_requirement SET type = 'SyReq' WHERE type IS NULL;`
   - Leave new fields NULL (frontend handles absence)

### Phase 2: Manager & QuerySet Annotation (Week 2)

1. Create `ArchitectureElementManager` with `get_queryset_with_level()`
2. Wire manager as default in `ArchitectureElement.objects`
3. Verify CTE query performance (target: <500ms for 10k items)

### Phase 3: Serializer Updates (Week 2)

1. Update `RequirementSerializer` to include conditional fields
2. Update `ArchitectureElementSerializer` to annotate level + include ASIL/Make-or-Buy
3. Add read-only `uid` and `version` to both

### Phase 4: Frontend Integration (Week 3)

1. React `RequirementEditor` checks `type` and renders conditional fields
2. React `ArchitectureEditor` renders ASIL/Make-or-Buy dropdowns
3. Split-View layout (REQ-L1-084) uses resizable divider

### Phase 5: Testing & Validation (Week 4)

1. Unit tests: Serializer field filtering per type
2. Integration tests: Allocation-tracking API endpoint
3. Performance tests: CTE query time <500ms for 10k items
4. Frontend E2E: Type-dependent fields visible/hidden correctly

---

## 6. Open Questions & Dependencies

| Question | Impact | Owner | Timeline |
|----------|--------|-------|----------|
| Should `uid` be auto-generated or user-entered? | Schema design, API contract | se-requirements | Before Phase 1 |
| What's the exact Fibonacci sequence for complexity (1–21 or 0–21)? | Serializer validation | Frontend | Before Phase 3 |
| Should AttributeVisibilityConfig be exposed via admin UI or API? | Admin UX, Access control | ui-ux-designer | Before Phase 3 |
| Is TraceLink.link_type conversion to enum-like choices required now, or deferred? | Backward compatibility | se-architect | Before Phase 1 |
| PostgreSQL only, or support SQLite for dev? | Dev environment setup | devops-engineer | Before Phase 1 |
| Should ArchitectureElement.parent_id be renamed to parent for consistency? | API contract, Serialization | api-specialist | Before Phase 1 |

---

## 7. Traceability Matrix

| REQ ID | AC | Design Section | Status |
|--------|----|----|--------|
| REQ-L1-058 | AC1 | Field Definitions (1) | Design Phase |
| REQ-L1-058 | AC2 | Recursive CTE Strategy (2) | Design Phase |
| REQ-L1-058 | AC3 | Allocation-Tracking (3) | Design Phase |
| REQ-L2-RF-025 | AC1 | Field Definitions (1) + Serializer (4) | Design Phase |
| REQ-L2-RF-025 | AC2 | Serializer (4) | Design Phase |
| REQ-L2-RF-025 | AC3 | Serializer (4) | Design Phase |
| REQ-L3-RF003-005 | AC1 | Field Definitions (1) + Serializer (4) | Design Phase |
| REQ-L3-RF003-005 | AC2 | Field Definitions (1) + Serializer (4) | Design Phase |
| REQ-L3-RF004-004 | AC1 | Field Definitions (1) + Serializer (4) | Design Phase |

---

**Next Steps:** Baseline approval from se-architect, then proceed with Phase 1 migrations.
