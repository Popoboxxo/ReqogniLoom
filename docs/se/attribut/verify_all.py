#!/usr/bin/env python3
# verify_all.py — Re-Verifikation aller tragenden Aussagen des Reports.
import json, re, subprocess, urllib.request, os, sys  # noqa

BASE = os.environ.get("RL_BASE","http://127.0.0.1:8001")
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
PW = ""
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    if line.startswith("SYSTEM_ADMIN_PASSWORD="):
        PW = line.split("=", 1)[1].strip(); break


def api(path, token=None, method="GET", body=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body else None, headers=h)
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def sh(cmd):
    return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, cwd=ROOT).stdout


tok = api("/api/v1/auth/login/", None, "POST", {"username": "admin", "password": PW})["token"]
TYPES = ["Requirement", "StakeholderNeed", "ArchitectureElement", "TestCase", "Adr",
         "Risk", "Issue", "Goal", "Icd", "GlossaryTerm", "ChangeRequest"]
PRESETS = ["minimal", "standard", "extended"]
R = []


def check(claim, ok, evidence):
    R.append((claim, "BESTÄTIGT" if ok else "WIDERLEGT", evidence))


# 1) Attributliste + required identisch über die Presets
identical = True
detail = []
for t in TYPES:
    sigs = []
    for p in PRESETS:
        d = api("/api/v1/attribute-defaults/%s/%s/" % (t, p), tok)
        attrs = d.get("attributes") or []
        sigs.append(tuple((a.get("name"), bool(a.get("required"))) for a in attrs))
    same = len(set(sigs)) == 1
    identical &= same
    detail.append("%s:%s" % (t, "gleich" if same else "ABWEICHEND"))
check("Attributliste+required über minimal/standard/extended identisch (11 Typen)",
      identical, "; ".join(detail[:6]) + " …")

# 2) priority fehlt als Attribut
d = api("/api/v1/attribute-defaults/Requirement/extended/", tok)
names = [a.get("name") for a in (d.get("attributes") or [])]
check("`priority` fehlt als Requirement-Attribut",
      "priority" not in names, "Attribute: " + ", ".join(names))
check("`rationale` fehlt als Requirement-Attribut", "rationale" not in names, "-")
check("`source` fehlt als Requirement-Attribut", "source" not in names, "-")
check("`uid` vorhanden, aber editable=%s" %
      [a.get("editable") for a in d["attributes"] if a.get("name") == "uid"],
      any(a.get("name") == "uid" and a.get("editable") is False for a in d["attributes"]),
      "kind/locked laut Bootstrap READ_ONLY_MODEL_FIELDS")

# 3) uid: help_text verspricht Autogenerierung
model_src = open(os.path.join(ROOT, "backend/persistence/models.py"), encoding="utf-8").read()
n_uid_help = len(re.findall(r'help_text="Unique identifier \(read-only, auto-generated\)"', model_src))
check("8 Modelle behaupten uid '(read-only, auto-generated)'", n_uid_help == 8, "%d Fundstellen" % n_uid_help)

# 4) kein Generator
gen = sh("grep -rn 'uid' backend/application backend/persistence backend/rest_api --include=*.py "
         "| grep -viE 'uuid|test' | grep -iE 'def .*uid|generate_uid|next_uid|assign_uid' | wc -l").strip()
check("KEINE uid-Generierungsfunktion im Produktivcode", gen == "0", "Treffer: %s" % gen)

# 5) Serializer read_only
serm = sh("grep -c 'uid = serializers.CharField(read_only=True' backend/rest_api/serializers.py").strip()
check("uid in Serializern read_only (Client kann es nicht setzen)", int(serm or 0) >= 8, "declarations: %s" % serm)

# 6) uid live leer
ws = api("/api/v1/workspaces/", tok)
WID = (ws.get("results") or ws)[0]["id"]
reqs = api("/api/v1/requirements/?workspace_id=%s&page_size=200" % WID, tok).get("results") or []
filled = sum(1 for r in reqs if r.get("uid"))
check("uid live: %d von %d Requirements gefüllt" % (filled, len(reqs)), filled == 0,
      "Workspace %s" % WID)

# 7) mandatory_fields pro Preset in registry.py
reg = open(os.path.join(ROOT, "backend/presets/registry.py"), encoding="utf-8").read()
check("mandatory_fields ist pro PRESET definiert (nicht pro Item-Typ)",
      'mandatory_fields=("title", "description", "acceptance_criteria", "priority")' in reg,
      "registry.py:170")

# 8) Baseline erfasst custom_fields
sc = open(os.path.join(ROOT, "backend/baseline/state_capture.py"), encoding="utf-8").read()
check("Baseline-State erfasst Artifact.custom_fields (inkl. 'rationale'-Beispiel im Docstring)",
      '"custom_fields": custom_fields or {}' in sc and "such as a \"rationale\"" in sc,
      "state_capture.py:46 + Docstring")

# 9) custom_fields leer in QS
tot = 0
for ep in ["requirements", "needs", "architecture", "testcases"]:
    rows = api("/api/v1/%s/?workspace_id=%s&page_size=200" % (ep, WID), tok).get("results") or []
    tot += sum(1 for r in rows if r.get("custom_fields"))
check("QS: 0 Artefakte mit custom_fields (Greenfield für Wert-Migration)", tot == 0,
      "geprüft: requirements/needs/architecture/testcases")

# 10) Interview-Alias
ad = open(os.path.join(ROOT, "backend/application/interview_artifact_adapters.py"), encoding="utf-8").read()
check("Interview-Adapter mappt rationale -> description",
      '_PROTOCOL_FIELD_ALIASES = {"rationale": "description"}' in ad, "interview_artifact_adapters.py:166")

print("%-72s %-11s %s" % ("AUSSAGE", "URTEIL", "BELEG"))
print("-" * 130)
for c, v, e in R:
    print("%-72s %-11s %s" % (c[:72], v, e[:60]))
print("\n%d/%d bestätigt" % (sum(1 for _, v, _ in R if v == "BESTÄTIGT"), len(R)))
