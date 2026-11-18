# Third-Party Notices

Date: 2026-11-18
Owner: `security-auditor`
Finding: DEP-007 (MPL-2.0 dependency present in npm lockfiles)
Decision: **E6**, decided by the user on **2026-11-17** — the MPL-2.0 dependency is
**KEPT** with this documented legal review. It is **not** replaced and no
dependency version is changed by this decision.

This notice records the evidence that the Mozilla Public License 2.0 (MPL-2.0)
packages in this repository are development/build-time only. The project's own
source is licensed under the MIT License (see repository root `LICENSE:1`).

## 1. Component inventory (MPL-2.0, pure SPDX identifier)

All entries below carry the exact SPDX identifier `MPL-2.0`. References use
`lockfile:line` (1-based, line of the `license` field) as committed. An audit
claim that "axe-core 4.14.0 is in the e2e lock" is **false**: `e2e/package-lock.json`
contains no axe-core entry (and no license metadata at all — that is a separate
DEP-010 metadata gap handled in WP-3). The real MPL evidence is in the two
lockfiles below.

### 1.1 `frontend/package-lock.json` — 13 MPL-2.0 entries (all `dev: true`)

| Component | Version | License | Lockfile:line | Scope |
|---|---|---|---|---|
| axe-core | 4.12.1 | MPL-2.0 | `frontend/package-lock.json:4398` | dev (test/a11y) |
| lightningcss | 1.33.0 | MPL-2.0 | `frontend/package-lock.json:8285` | dev (build/CSS transform) |
| lightningcss-android-arm64 | 1.33.0 | MPL-2.0 | `frontend/package-lock.json:8318` | dev (optional platform binary) |
| lightningcss-darwin-arm64 | 1.33.0 | MPL-2.0 | `frontend/package-lock.json:8339` | dev (optional platform binary) |
| lightningcss-darwin-x64 | 1.33.0 | MPL-2.0 | `frontend/package-lock.json:8360` | dev (optional platform binary) |
| lightningcss-freebsd-x64 | 1.33.0 | MPL-2.0 | `frontend/package-lock.json:8381` | dev (optional platform binary) |
| lightningcss-linux-arm-gnueabihf | 1.33.0 | MPL-2.0 | `frontend/package-lock.json:8402` | dev (optional platform binary) |
| lightningcss-linux-arm64-gnu | 1.33.0 | MPL-2.0 | `frontend/package-lock.json:8423` | dev (optional platform binary) |
| lightningcss-linux-arm64-musl | 1.33.0 | MPL-2.0 | `frontend/package-lock.json:8444` | dev (optional platform binary) |
| lightningcss-linux-x64-gnu | 1.33.0 | MPL-2.0 | `frontend/package-lock.json:8465` | dev (optional platform binary) |
| lightningcss-linux-x64-musl | 1.33.0 | MPL-2.0 | `frontend/package-lock.json:8486` | dev (optional platform binary) |
| lightningcss-win32-arm64-msvc | 1.33.0 | MPL-2.0 | `frontend/package-lock.json:8507` | dev (optional platform binary) |
| lightningcss-win32-x64-msvc | 1.33.0 | MPL-2.0 | `frontend/package-lock.json:8528` | dev (optional platform binary) |

### 1.2 `integrations/hermes-plugin/reqogniloom/package-lock.json` — 12 MPL-2.0 entries (all `dev: true`)

The same `lightningcss@1.33.0` toolchain appears in the plugin's build lockfile.

| Component | Version | License | Lockfile:line | Scope |
|---|---|---|---|---|
| lightningcss | 1.33.0 | MPL-2.0 | `integrations/hermes-plugin/reqogniloom/package-lock.json:1111` | dev (build/CSS transform) |
| lightningcss-android-arm64 | 1.33.0 | MPL-2.0 | `integrations/hermes-plugin/reqogniloom/package-lock.json:1144` | dev (optional platform binary) |
| lightningcss-darwin-arm64 | 1.33.0 | MPL-2.0 | `integrations/hermes-plugin/reqogniloom/package-lock.json:1165` | dev (optional platform binary) |
| lightningcss-darwin-x64 | 1.33.0 | MPL-2.0 | `integrations/hermes-plugin/reqogniloom/package-lock.json:1186` | dev (optional platform binary) |
| lightningcss-freebsd-x64 | 1.33.0 | MPL-2.0 | `integrations/hermes-plugin/reqogniloom/package-lock.json:1207` | dev (optional platform binary) |
| lightningcss-linux-arm-gnueabihf | 1.33.0 | MPL-2.0 | `integrations/hermes-plugin/reqogniloom/package-lock.json:1228` | dev (optional platform binary) |
| lightningcss-linux-arm64-gnu | 1.33.0 | MPL-2.0 | `integrations/hermes-plugin/reqogniloom/package-lock.json:1252` | dev (optional platform binary) |
| lightningcss-linux-arm64-musl | 1.33.0 | MPL-2.0 | `integrations/hermes-plugin/reqogniloom/package-lock.json:1276` | dev (optional platform binary) |
| lightningcss-linux-x64-gnu | 1.33.0 | MPL-2.0 | `integrations/hermes-plugin/reqogniloom/package-lock.json:1295` | dev (optional platform binary) |
| lightningcss-linux-x64-musl | 1.33.0 | MPL-2.0 | `integrations/hermes-plugin/reqogniloom/package-lock.json:1319` | dev (optional platform binary) |
| lightningcss-win32-arm64-msvc | 1.33.0 | MPL-2.0 | `integrations/hermes-plugin/reqogniloom/package-lock.json:1340` | dev (optional platform binary) |
| lightningcss-win32-x64-msvc | 1.33.0 | MPL-2.0 | `integrations/hermes-plugin/reqogniloom/package-lock.json:1361` | dev (optional platform binary) |

### 1.3 Dual-licensed — not a finding

`dompurify@3.4.17` is `MPL-2.0 OR Apache-2.0` (`frontend/package-lock.json:5680`).
The Apache-2.0 alternative applies, so this entry is **not** an MPL finding and
is listed here only for completeness.

## 2. Dev/build-only evidence

Every MPL entry above is marked `"dev": true` in its lockfile. They are pulled
in only by the frontend toolchain (axe-core for accessibility tests, lightningcss
as a CSS transformer) and by the plugin build.

The production image does **not** contain these packages:
`frontend/Dockerfile` builds in a `node:26.13.0-slim` `builder` stage and the
final `nginx:1.31-alpine` stage copies **only** `/app/dist` (compiled static
assets) via `COPY --from=builder /app/dist /usr/share/nginx/html`
(`frontend/Dockerfile:36` onward). No `node_modules` directory, no MPL source
file and no MPL binary is copied into the distributed image.

Both Docker build stages use `RUN npm ci` (development and builder), so the
lockfile is enforced reproducibly. Local hot reload is unaffected: the dev
compose override still runs `npm install` inside the mounted source volume
(`deploy/docker-compose.override.yml:238` command).

## 3. Explicit conditions

For each MPL-2.0 component in section 1:

- **(a) No MPL file is vendored or copied** into this repository's source tree.
  The packages exist only as npm registry artifacts resolved by `npm ci` into
  an ephemeral `node_modules` directory.
- **(b) No MPL file is modified.** No patch, overlay, fork or edit touches any
  file from these packages; they are consumed exactly as published upstream.
- **(c) No MPL file is distributed.** No MPL source, object or executable form
  is shipped in the production image, release archive, npm package or any other
  distributed artifact of this project.

## 4. MPL section 3.2 reasoning

MPL 2.0 section 3.2 ("Distribution of Executable Form") imposes a
source-availability obligation when a covered work is **distributed** in
executable form. Here the MPL packages are **unmodified** (condition b) and
**not distributed** (condition c); they are used solely as local development
and build inputs. No executable form of an MPL-covered file leaves the build
environment. Therefore **no source offer is required** — the section 3.2
trigger does not fire.

This conclusion is re-validated by `scripts/tests/test_license_notices.py`,
which re-reads all committed lockfiles, extracts every pure MPL-2.0 component
and fails if one is undocumented or ceases to be `dev: true`.

## 5. Governance

- **Owner:** `security-auditor` (named reviewer of this exception).
- **Decision:** E6, user decision on 2026-11-17; documented here 2026-11-18.
- **Review trigger:** re-review this notice on **any version bump** of an MPL
  component above, on **first vendoring/copying** of an MPL file into the repo,
  or if an MPL component is promoted to a production dependency / included in a
  distributed artifact. The `dev: true` gate in the guard test enforces the
  promotion case automatically.
- **Upstream license references:**
  - MPL 2.0 full text: https://www.mozilla.org/media/MPL/2.0/index.txt
  - SPDX MPL-2.0: https://spdx.org/licenses/MPL-2.0.html
  - axe-core: https://github.com/dequelabs/axe-core/blob/develop/LICENSE
  - lightningcss: https://github.com/parcel-bundler/lightningcss/blob/master/LICENSE
  - khroma (MIT, `license` file in the 2.1.0 tarball): https://github.com/fabiospampinato/khroma
  - undici (MIT): https://github.com/nodejs/undici/blob/main/LICENSE
  - zod (MIT): https://github.com/colinhacks/zod/blob/master/LICENSE
- **Fallback plan:** if any condition in section 3 breaks (vendoring,
  modification, distribution, or a legal re-review that disallows the use),
  replace the component with a permissively licensed (MIT/Apache-2.0)
  alternative before shipping — e.g. swap the lightningcss CSS transform or
  the axe-core based accessibility check — and update this notice.

## 6. DEP-010 frontend lock metadata (WP-1)

`frontend/package-lock.json` previously had 883 `resolved` entries but only
880 `license` fields. The three gaps (khroma 2.1.0, undici 8.12.3, zod 4.6.7)
were filled with their verified upstream `MIT` identifier; coverage is now
883/883. khroma's npm metadata omits the field, but its published 2.1.0 tarball
contains an MIT `license` file, so `MIT` is the correct value rather than a
NOASSERTION. No dependency version was changed.
