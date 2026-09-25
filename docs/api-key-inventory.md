# API-key inventory (`manage.py inventory_api_keys`)

**Audit track:** `CR-03` (P1 for new agent/UI keys, P2 for legacy hardening) — see
`docs/se/reports/deep_audit/system-audit-2026-09/09-evidence-register.md` and §4.7 of
`08-remediation-roadmap-and-alternatives.md`.

`CR-03` asks for two separate things, in this order:

1. A new REST/MCP key must carry an **explicit scope**, an **explicit workspace fence**
   and an **explicit expiry decision**.
2. A legacy key is **inventoried and rotated**, never silently changed.

`inventory_api_keys` is the inventory half, and only the inventory half. It exists so that
requirement 2 can be executed deliberately, by a human, with a ticket — instead of being
smuggled in as a data migration nobody reviewed.

---

## What the report contains

One record per `ApiKey` row (`at_api_key`), ordered by `created_at` then `id` so two runs
diff cleanly. Every column is mapped to a real model field; the table below is the
authoritative list.

| Column | Model field | Notes |
|---|---|---|
| `key_id` | `id` (UUID PK) | The stable, non-reversible identifier. Use it in tickets. |
| `name` | `name` | Operator-supplied label. |
| `tenant_id` | `tenant_id` | FK to `pl_tenant`. |
| `tenant_slug` | `tenant__slug` | Human-readable tenant. |
| `owner_user_id` | `user_id` | FK to `pl_user`. |
| `owner_username` | `user__username` | The human to contact about a rotation. E-mail is deliberately **not** emitted (PII in archived evidence). |
| `principal_type` | `principal_type` | `user` \| `agent`. |
| `agent_label` | `agent_label` | e.g. `Claude Code`. |
| `scope` | `scope` | Verbatim stored value. |
| `scope_is_legacy_alias` | derived from `scope` | `true` for `read`/`write`, the two legacy aliases. |
| `workspace_ids` | `workspace_ids` | Verbatim list. Workspace UUIDs are not secret. |
| `workspace_fence_state` | derived from `workspace_ids` | `set` \| `unset`. |
| `expires_at` | `expires_at` | `null` when the row records no expiry. |
| `expiry_state` | derived from `expires_at` | `no_expiry_set` \| `expired` \| `not_yet_expired`. |
| `created_at` | `created_at` | From `AuditableModel`. |
| `last_used_at` | `last_used_at` | **The model has this field** — no proxy is invented. |
| `usage_state` | derived from `last_used_at` | `used` \| `never_used`. |
| `revoked_at` | `revoked_at` | |
| `status` | derived | `revoked` > `expired` > `active`. |
| `not_revoked` | derived | The model's own `ApiKey.is_active`. Reported separately from `status` on purpose — an **expired key is still `is_active`**, because expiry is not revocation. |
| `secret_present` | derived from `key_hash` | Boolean only. See below. |
| `unsatisfied_rules` | derived | Which documented rules this key's attributes do **not** satisfy. |
| `rotation_candidate` | derived | |
| `rotation_reasons` | derived | Why. |

### `expiry_state` — three states, not two

`expires_at IS NULL` and `expires_at <= now` are different facts, and the model keeps them
apart (`ApiKey.is_expired` returns `False` for `NULL`). The report therefore distinguishes:

* `no_expiry_set` — the row records no expiry decision. **The model cannot tell a deliberate
  "never expires" apart from a decision nobody ever took**; both are `NULL`. The report says
  "no expiry set" and stops there. Whether that is acceptable is a decision for the reviewer,
  not something this command can read off the row.
* `expired` — a recorded expiry that has since passed.
* `not_yet_expired` — a recorded expiry still in the future.

### The rule flags (`unsatisfied_rules`)

The three rules are the three clauses of the documented new-key contract (roadmap §4.7,
acceptance criterion 3):

| Rule id | Unsatisfied when |
|---|---|
| `explicit-canonical-scope` | `scope` is not one of the canonical tiers `read_only` / `author` / `admin` — i.e. it is a legacy alias (`read`, `write`) or empty. |
| `workspace-fence-set` | `workspace_ids` is empty. |
| `expiry-decision-recorded` | `expires_at IS NULL`. |

These are attribute comparisons, full stop.

---

## The rotation rule

One named constant, `LEGACY_KEY_ROTATION_RULE` in
`backend/auth_tenancy/management/commands/inventory_api_keys.py`, carrying an explicit date:

* **name** — `CR-03-LEGACY-API-KEY-ROTATION/2026-09-25`
* **effective date** — `2026-09-25`
* **classification** — a key is a **rotation candidate** if **either**
  1. it was created **before** the effective date (UTC calendar day of `created_at`), **or**
  2. its attributes do not satisfy one of the three new-key contract rules above.

The boundary is a plain calendar day, not a timestamp: a key created at `2026-09-25T00:00:00Z`
is **not** pre-dated; a key created one second earlier **is**.

Every output format prints the rule name, its effective date, its reference and its criteria in
a header, so a reader can see *why* a key was listed without opening the source. Adjusting the
policy means editing that one constant in a reviewable commit — the date is also part of the
rule *name*, so an old archived report can never be mistaken for a run under a newer rule.

### Rotation reasons

| Reason | Meaning |
|---|---|
| `created-before-rule-effective-date` | The key predates the rule. |
| `no-canonical-scope` | `scope` is a legacy alias, not one of the three canonical tiers. |
| `no-workspace-fence` | `workspace_ids` is empty — the key is unfenced. |
| `no-expiry-decision` | `expires_at IS NULL`. |

---

## How to run it

```bash
# Human-readable report on stdout
python manage.py inventory_api_keys

# Archive as machine-readable evidence
python manage.py inventory_api_keys --format json --output keys-2026-09-25.json
python manage.py inventory_api_keys --format csv  --output keys-2026-09-25.csv

# One tenant only
python manage.py inventory_api_keys --tenant-id 9b1f0e2c-...
```

Against the test stack:

```bash
docker compose -p reqlo-audit-w1-test --project-directory . \
  -f deploy/docker-compose.yml -f testing/docker-compose.test.yml \
  run --rm backend-test python manage.py inventory_api_keys --format json
```

### Flags

| Flag | Values | Default | Purpose |
|---|---|---|---|
| `--format` | `text`, `json`, `csv` | `text` | Report format. |
| `--output` | path | *(stdout)* | Write the report to a file; stdout then carries only a one-line confirmation. |
| `--tenant-id` | UUID | *(all tenants)* | Narrow the inventory. The report states the filter in its header. |

There is no `--fix`, no `--apply`, no `--rotate`. Those are rejected as unknown arguments.

**Safe to run against production.** The command is report-only by construction: it issues one
`SELECT`, holds the read inside `SET LOCAL row_security = off` (the same pattern
`inventory_link_types` uses for `TraceLink`, so an RLS-blinded connection fails loudly instead
of silently reporting "0 keys, nothing to rotate"), and writes nothing to the database. It
touches no key row and needs no confirmation prompt.

### Diffing over time

Archive `--format json` runs. `generated_at` is the only intentionally volatile field; the
`keys` array, `totals` and `rotation_rule` are stable, so:

```bash
python manage.py inventory_api_keys --format json --output /tmp/keys-before.json
#   ... time passes, keys are rotated through the normal path ...
python manage.py inventory_api_keys --format json --output /tmp/keys-after.json
diff <(jq 'del(.generated_at)' /tmp/keys-before.json) <(jq 'del(.generated_at)' /tmp/keys-after.json)
```

The CSV format is a flat table (lists `;`-joined) preceded by `#` comment rows carrying the
rule and its date. Strip the comments if your CSV reader does not skip `#` rows.

---

## What this command deliberately does **NOT** do

* **It never modifies a key.** No `.save()`, no `.delete()`, no `.update()`, no
  `bulk_update`, no rotation helper, no `create_api_key`, no `revoke_api_key`. A before/after
  snapshot of every field (including `modified_at` and `version`, which *any* write bumps) is
  asserted unchanged in the test suite, and a captured-query assertion proves the run issued no
  `INSERT`/`UPDATE`/`DELETE`/DDL statement.
* **It never deletes or deactivates anything**, and it has no dry-run flag, because there is
  nothing to dry-run.
* **It never prints key material.** `key_hash` is read only to compute the boolean
  `secret_present`. Neither the hash, nor its version prefix, nor its length, nor any fragment
  reaches stdout or the output file — the field name does not appear either, so
  `grep -i key_hash` over an archived report finds nothing. The test suite asserts that no
  8-character window of any fixture hash appears in any of the three formats, and includes a
  positive control proving the detector is not vacuously green.
* **It never stamps a capability verdict.** There is no `valid` / `invalid` / `broken` /
  `not-agent-capable` column, and the words do not appear in the output. A row's attribute
  values do not earn such a verdict; the report says what is recorded and which rule the
  record does not meet, and stops.
* **It does not adjudicate usability.** A key on the rotation-candidate list may be perfectly
  fine for its purpose today. The list means "this row does not meet the documented contract,
  and the contract says such a key is changed by rotation" — nothing more.

---

## How to interpret the rotation-candidate list

1. **It is a worklist, not a defect list.** Every candidate is a key that predates the rule or
   whose recorded attributes fall short of it. Both are *policy* gaps, not observed failures.
2. **Group by `rotation_reasons`.** A candidate listed only as `created-before-rule-effective-date`
   satisfies all three contract rules and is simply old — schedule it for routine rotation.
   `no-workspace-fence` means the key can act in every workspace its owner holds a role in:
   that is the one with the widest blast radius, so prioritise it.
3. **Check `status` and `last_used_at` before scheduling anything.** An `expired` or `revoked`
   candidate may be dead weight rather than a live credential, and a `never_used` key is a
   cheap candidate for retirement rather than rotation.
4. **The rule is dated on purpose.** When the effective date is moved forward in a later
   commit, run the inventory again and keep both reports: the diff then *is* the audit trail
   of the policy change.

### Acting on a candidate

**Rotation happens through the existing key-management path — never through this command:**

* REST: `POST /api/v1/api-keys/` (new key with explicit scope, fence and expiry), then
  `DELETE /api/v1/api-keys/<pk>/` for the old one.
* MCP: the key-management tool group.
* Code: `AuthenticationService.create_api_key` / `revoke_api_key`.

That is the whole point of `CR-03`'s second clause: an old key is changed by rotation, by a
deliberate act, through a path that enforces the new-key contract on the *new* key. This
command only tells you which rows are in scope for that act.

---

## Sample output (text)

Fixture: one compliant new-style key, one key with an empty workspace fence, one key with no
expiry, one expired key. Real output of `render_text` — note that no `key_hash` material
appears anywhere, only `secret present`.

```text
API-key inventory - READ-ONLY (no key row is created, changed or removed)
Generated: 2026-09-25T17:45:00+00:00
Tenants: all

Rotation rule applied
  name          : CR-03-LEGACY-API-KEY-ROTATION/2026-09-25 (effective 2026-09-25 UTC)
  reference     : CR-03 (P1 new agent/UI keys, P2 legacy hardening)
  criteria      : rotation candidate if created before the effective date (UTC), or if the key does not satisfy one of the new-key contract rules: explicit-canonical-scope, workspace-fence-set, expiry-decision-recorded
  acting on one : rotate through the normal key-management path (REST /api/v1/api-keys/, MCP key group, AuthenticationService) - never through this command

Totals: 4 key(s) | 3 rotation candidate(s) | 0 revoked | 1 expired | 1 with no expiry set | 1 without workspace fence | 2 never used

KEYS (4)
----------------------------------------------------------------------------------------------------
[1] legacy-exporter
    id fd93f28a-8331-437a-b9b5-e32912bbd638 | tenant acme-systems (0c57cb9e-d408-433c-b47d-00ccd9ae92a4) | owner alice.chen (ee05da61-0b8d-45eb-97fe-0cc8ecbb194d)
    principal user | scope author (canonical) | fence 2 ws [922d23d7-e5c9-4c8d-9e5d-4836f57f7d90, 3014ef66-b447-4e49-a0aa-608ca04a086f]
    created 2026-06-02T09:15:00+00:00 | expiry none (no_expiry_set) | last_used never (never_used)
    status active | revoked_at none | secret present
    unsatisfied rules: expiry-decision-recorded
    rotation: CANDIDATE: created-before-rule-effective-date, no-expiry-decision
[2] expired-report-bot
    id 98ea9f2f-e17e-4c0b-8c6c-c37fc7480296 | tenant acme-systems (0c57cb9e-d408-433c-b47d-00ccd9ae92a4) | owner alice.chen (ee05da61-0b8d-45eb-97fe-0cc8ecbb194d)
    principal agent  label="Report Bot" | scope read_only (canonical) | fence 1 ws [3014ef66-b447-4e49-a0aa-608ca04a086f]
    created 2026-07-21T16:40:00+00:00 | expiry 2026-09-22T15:45:00+00:00 (expired) | last_used 2026-09-22T12:45:00+00:00 (used)
    status expired | revoked_at none | secret present
    unsatisfied rules: all satisfied
    rotation: CANDIDATE: created-before-rule-effective-date
[3] legacy-ci-runner
    id a7a9ac9c-852a-4c47-b1cb-62b4f266a0aa | tenant acme-systems (0c57cb9e-d408-433c-b47d-00ccd9ae92a4) | owner alice.chen (ee05da61-0b8d-45eb-97fe-0cc8ecbb194d)
    principal agent  label="GitHub Actions" | scope write (legacy alias) | fence UNSET
    created 2026-08-14T11:05:00+00:00 | expiry 2026-11-09T17:45:00+00:00 (not_yet_expired) | last_used never (never_used)
    status active | revoked_at none | secret present
    unsatisfied rules: explicit-canonical-scope, workspace-fence-set
    rotation: CANDIDATE: created-before-rule-effective-date, no-canonical-scope, no-workspace-fence
[4] compliant-agent
    id 13240710-7d1f-44bf-ad11-6955e76247de | tenant acme-systems (0c57cb9e-d408-433c-b47d-00ccd9ae92a4) | owner alice.chen (ee05da61-0b8d-45eb-97fe-0cc8ecbb194d)
    principal agent  label="Claude Code" | scope read_only (canonical) | fence 1 ws [922d23d7-e5c9-4c8d-9e5d-4836f57f7d90]
    created 2026-09-26T08:30:00+00:00 | expiry 2026-10-25T17:45:00+00:00 (not_yet_expired) | last_used 2026-09-25T11:45:00+00:00 (used)
    status active | revoked_at none | secret present
    unsatisfied rules: all satisfied
    rotation: not a candidate

ROTATION CANDIDATES (3) - rule: CR-03-LEGACY-API-KEY-ROTATION/2026-09-25 (effective 2026-09-25 UTC)
----------------------------------------------------------------------------------------------------
  fd93f28a-8331-437a-b9b5-e32912bbd638  legacy-exporter  (tenant acme-systems, owner alice.chen)  created 2026-06-02T09:15:00+00:00
      reasons: created-before-rule-effective-date, no-expiry-decision
  98ea9f2f-e17e-4c0b-8c6c-c37fc7480296  expired-report-bot  (tenant acme-systems, owner alice.chen)  created 2026-07-21T16:40:00+00:00
      reasons: created-before-rule-effective-date
  a7a9ac9c-852a-4c47-b1cb-62b4f266a0aa  legacy-ci-runner  (tenant acme-systems, owner alice.chen)  created 2026-08-14T11:05:00+00:00
      reasons: created-before-rule-effective-date, no-canonical-scope, no-workspace-fence
```

Note `[2] expired-report-bot`: it satisfies all three contract rules yet is still a candidate,
because it predates the rule date. Note `[1]`: it satisfies scope and fence, and is listed for
`no-expiry-decision` alone.

---

## Tests

`backend/auth_tenancy/tests/test_inventory_api_keys_command.py` (39 tests):

* **Read-only** — full before/after field snapshot per key row; captured-query assertion that
  no `INSERT`/`UPDATE`/`DELETE`/DDL statement is issued; patched `create_api_key`,
  `revoke_api_key`, `ApiKey.save`, `ApiKey.delete`, `ApiKey.unscoped.create` all
  `assert_not_called()`; `--fix`/`--apply`/`--rotate`/`--write`/`--revoke` all rejected.
* **No secret output** — sentinel `key_hash` values; no 8-character window of any of them
  appears in stdout or in the `--output` file, in all three formats; `"key_hash"` absent from
  the file; `secret_present` present and boolean; positive control proving the window scan
  detects a real leak.
* **Rotation classification** — boundary date (`2026-09-24T23:59:59Z` is a candidate,
  `2026-09-25T00:00:00Z` is not, for otherwise identical compliant keys), each contract rule
  detected in isolation, and each producing its own reason.
* **Expiry** — `no_expiry_set` vs `expired` vs `not_yet_expired`; expired ≠ revoked;
  `classify_expiry` matches the model's own `is_expired` semantics at the exact boundary.
* **No capability stamping** — the words `invalid`, `broken`, `insecure`, `compromised`,
  `usab` appear in no format's output; no column name contains `valid` or `capab`.

Run them:

```bash
docker compose -p reqlo-audit-w1-test --project-directory . \
  -f deploy/docker-compose.yml -f testing/docker-compose.test.yml \
  run --rm backend-test pytest -q --create-db \
  auth_tenancy/tests/test_inventory_api_keys_command.py
```

## Related

* `backend/auth_tenancy/models.py` — the `ApiKey` model and the `API_KEY_SCOPE_*` /
  `PRINCIPAL_TYPE_*` constants the report's vocabulary is derived from.
* `backend/link_types/management/commands/inventory_link_types.py` — the sibling
  read-only whole-database inventory command this one follows (RLS-off read, no write path).
* `backend/rest_api/tests/test_api_key_agent_fields.py` — the existing pins for the legacy
  defaults (`write` / empty fence / `expires_at=NULL`). The rotation rule exists precisely
  because those defaults are still reachable; this command does not change them.
