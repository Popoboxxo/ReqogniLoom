"""ARCH-L1-011 AuthAndTenancy — "Zahnbürste SysEng" demo seed (E2E fixture).

Seeds the multi-level SysEng demo workspace that
``e2e/tests/toothbrush-syseng.spec.ts`` asserts against: a full L0-L4
decomposition with requirements, architecture elements, trace links, risks,
issues, ADRs, glossary terms, ICDs, test cases and test runs.

This used to live at ``backend/seed_toothbrush.py`` and was invoked by the spec
via ``docker compose exec -T backend python seed_toothbrush.py``. That only ever
worked against a local compose stack — the E2E CI job runs the backend as a bare
``manage.py runserver`` process on the runner, with no compose project to exec
into, so the spec failed on every CI run. As a management command it is seeded
from the workflow like ``seed_demo``, and the spec looks the workspace up by
name over the API.

Idempotent: re-running returns the existing workspace instead of creating a
second one, so a local ``make e2e`` loop does not accumulate duplicates.

Usage:
    python manage.py seed_toothbrush
"""
from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.provisioning import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_USERNAME
from persistence.middleware import set_request_tenant, clear_request_tenant
from persistence.models import Tenant, User, Workspace, ElementType, RequirementType, MoSCoWPriority, StakeholderNeed, Artifact
from application.workspace_service import WorkspaceService
from application.requirement_service import RequirementService
from application.architecture_service import ArchitectureService
from application.trace_link_service import TraceLinkService
from application.risk_service import RiskService
from application.issue_service import IssueService
from application.adr_service import AdrService
from application.glossary_service import GlossaryService
from application.test_service import TestService
from application.test_run_service import TestRunService
from icd.services import create_icd, IcdCreateDTO

WORKSPACE_NAME = "Zahnbürste SysEng Demo"


def run():
    print("Starting Zahnbürste SysEng Demo seeding...")
    # Seed into the *admin's* tenant, not Tenant.objects.first(). The E2E suite
    # logs in as this admin and finds the workspace through the tenant-scoped
    # /api/v1/workspaces/ list, so seeding into whatever tenant happens to sort
    # first produces a workspace the spec can never see (row-level isolation,
    # ADR-03). On a dev database with leftover tenants that is exactly what
    # happened.
    user = User.objects.filter(username=DEFAULT_ADMIN_USERNAME).first()
    if user is None:
        user = User.objects.first()
    if user is not None:
        tenant = Tenant.objects.filter(id=user.tenant_id).first()
    else:
        tenant = Tenant.objects.first()

    if tenant is None:
        tenant = Tenant.objects.create(name="Default Tenant")
    if user is None:
        user = User.objects.create(
            email=DEFAULT_ADMIN_EMAIL,
            username=DEFAULT_ADMIN_USERNAME,
            tenant=tenant,
        )

    ctx = AuthContext(
        tenant_id=tenant.id,
        user_id=user.id,
        # REQ-L2-AT-003/ADR-L3-AT002-01: the RBAC matrix only recognises the
        # four hard-coded role strings (admin/editor/viewer/approver, see
        # auth_tenancy/models.py ROLE_*). "tenant_admin" was never one of
        # them and used to pass only because _assert_write_permission()
        # allowed unrecognised roles by default; #99/#100/#102 (commit
        # 9e58ddd) made that check fail-closed, so this seed script must use
        # the real admin role string to keep writing.
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN
    )

    # COMP-PL-006: activate the Postgres RLS session variable + thread-local
    # app-layer filter for this tenant. Outside of a request, no middleware
    # runs set_request_tenant() for us, so every direct model write below
    # (e.g. the Artifact.objects.create() calls for StakeholderNeed) would
    # otherwise be rejected by the "new row violates row-level security
    # policy" Postgres policy (COMP-PL-006, migration 0003_rls_policies).
    set_request_tenant(tenant.id)

    existing = Workspace.objects.filter(
        tenant_id=tenant.id, name=WORKSPACE_NAME
    ).first()
    if existing is not None:
        print(f"Workspace created with ID: {existing.id}")
        print("Seeding skipped — workspace already present.")
        clear_request_tenant()
        return

    ws_svc = WorkspaceService()
    print("Creating Workspace...")
    ws = ws_svc.create_workspace(ctx=ctx, name=WORKSPACE_NAME, preset="extended", terminology_profile="se_mode")
    ws_id = ws.id
    print(f"Workspace created with ID: {ws_id}")
    
    # Initialize Services
    req_svc = RequirementService()
    arch_svc = ArchitectureService()
    link_svc = TraceLinkService()
    risk_svc = RiskService()
    issue_svc = IssueService()
    adr_svc = AdrService()
    glossary_svc = GlossaryService()
    test_svc = TestService()
    test_run_svc = TestRunService()
    
    print("Creating Glossary Terms...")
    terms = [
        ("BLDC", "Brushless DC Motor - Ein bürstenloser Gleichstrommotor für hohe Effizienz."),
        ("IPX7", "Schutz gegen zeitweiliges Untertauchen in Wasser."),
        ("BLE", "Bluetooth Low Energy - Ein Funkstandard für energiesparende Datenübertragung."),
        ("MCU", "Microcontroller Unit - Der Hauptprozessor der Zahnbürste."),
        ("PCBA", "Printed Circuit Board Assembly - Bestückte Leiterplatte."),
    ]
    for term, definition in terms:
        glossary_svc.create(ctx=ctx, workspace_id=ws_id, term=term, definition=definition)
    
    # 1. Stakeholder Needs
    needs_data = [
        ("N-01", "Gründliche Reinigung", "Entfernt Plaque besser als Handzahnbürste"),
        ("N-02", "Akkulaufzeit", "Mindestens 2 Wochen bei 2x täglicher Nutzung"),
        ("N-03", "Wasserdicht", "Komplett wasserdicht nach IPX7"),
        ("N-04", "Andruckkontrolle", "Warnt Nutzer bei zu starkem Druck"),
        ("N-05", "Putz-Coaching App", "Begleit-App für Putz-Statistiken via Bluetooth"),
        ("N-06", "Austauschbare Köpfe", "Einfacher Bürstenkopf-Wechsel (Click-on)"),
        ("N-07", "Reise-Etui", "Etui mit integrierter Ladefunktion"),
        ("N-08", "Leises Betriebsgeräusch", "Unter 60 dB im Betrieb"),
        ("N-09", "Ergonomie", "Rutschfester Griff auch bei Nässe"),
        ("N-10", "Nachhaltigkeit", "Reparierbarkeit des Akkus"),
        ("N-11", "Gewicht", "Die Zahnbürste darf maximal 150g wiegen"),
        ("N-12", "Ladezeit", "Eine vollständige Akkuladung darf maximal 4 Stunden dauern"),
        ("N-13", "Ersatzteilverfügbarkeit", "Ersatzteile müssen mindestens 5 Jahre verfügbar sein"),
        ("N-14", "Zahnfleisch-Schutz", "Spezielle Borsten für empfindliches Zahnfleisch"),
        ("N-15", "Reinigungsmodi", "Mindestens 3 verschiedene Modi (Standard, Sensitiv, Weiß)"),
        ("N-16", "Design & Ästhetik", "Premium-Look, in Schwarz und Weiß verfügbar"),
        ("N-17", "Zertifizierungen", "CE und FCC Zertifizierung für globalen Markt"),
        ("N-18", "Verpackung", "100% plastikfreie Verpackung"),
        ("N-19", "Robustheit", "Falltest aus 1,5m Höhe ohne Funktionsverlust"),
        ("N-20", "Kinder-Modus", "Sicherheitsmodus mit reduzierter Kraft für Kinder")
    ]
    
    needs = []
    print("Creating Stakeholder Needs...")
    for title, desc, details in needs_data:
        artifact = Artifact.objects.create(
            workspace_id=ws_id,
            artifact_type="StakeholderNeed",
            tenant_id=tenant.id,
            created_by_id=user.id,
        )
        n = StakeholderNeed.objects.create(
            artifact=artifact,
            tenant_id=tenant.id,
            title=title,
            description=details,
            moscow_priority=MoSCoWPriority.MUST,
            created_by_id=user.id
        )
        needs.append(n)
        
    # 2. Architecture Elements
    archs = {}
    
    def create_arch(key, title, el_type, parent_key=None):
        parent_id = archs[parent_key].id if parent_key else None
        a = arch_svc.create_architecture_element(workspace_id=ws_id, title=title, ctx=ctx, element_type=el_type, parent_id=parent_id)
        archs[key] = a
        return a
        
    print("Creating Architecture Elements...")
    sys1 = create_arch("SYS", "Smart Toothbrush System", ElementType.SUBSYSTEM)
    create_arch("SS_HANDLE", "Handstück", ElementType.SUBSYSTEM, "SYS")
    create_arch("SS_HEAD", "Bürstenkopf", ElementType.SUBSYSTEM, "SYS")
    create_arch("SS_BASE", "Ladestation", ElementType.SUBSYSTEM, "SYS")
    create_arch("SS_APP", "Putz-Coaching App", ElementType.SUBSYSTEM, "SYS")
    create_arch("A_MOTOR", "Motor Assembly", ElementType.COMPONENT, "SS_HANDLE")
    create_arch("A_BATTERY", "Batterie Assembly", ElementType.COMPONENT, "SS_HANDLE")
    create_arch("A_PCBA", "Main PCBA", ElementType.COMPONENT, "SS_HANDLE")
    create_arch("A_HOUSING", "Gehäuse", ElementType.COMPONENT, "SS_HANDLE")
    create_arch("A_BRISTLES", "Borsten-Block", ElementType.COMPONENT, "SS_HEAD")
    create_arch("A_INDUCTIVE", "Induktionsspule", ElementType.COMPONENT, "SS_BASE")
    create_arch("C_BLDC", "BLDC Motor", ElementType.COMPONENT, "A_MOTOR")
    create_arch("C_SHAFT", "Antriebswelle", ElementType.COMPONENT, "A_MOTOR")
    create_arch("C_CELL", "Li-Ion Zelle 18650", ElementType.COMPONENT, "A_BATTERY")
    create_arch("C_MCU", "Microcontroller STM32", ElementType.COMPONENT, "A_PCBA")
    create_arch("C_BLE", "Bluetooth IC", ElementType.COMPONENT, "A_PCBA")
    create_arch("C_SENSOR", "Drucksensor", ElementType.COMPONENT, "A_PCBA")
    create_arch("P_MAGNET", "Rotor-Magnet", ElementType.COMPONENT, "C_BLDC")
    create_arch("P_COIL", "Stator-Spule", ElementType.COMPONENT, "C_BLDC")
    create_arch("P_SEAL", "Dichtungsring", ElementType.COMPONENT, "A_HOUSING")
    create_arch("P_BUTTON", "Gummiknopf", ElementType.COMPONENT, "A_HOUSING")
    create_arch("P_LED", "Status-LED", ElementType.COMPONENT, "A_PCBA")
    create_arch("SW_PWM", "Motor PWM Modul", ElementType.MODULE, "C_MCU")
    create_arch("SW_BLE", "BLE Stack", ElementType.MODULE, "C_MCU")
    create_arch("SW_BMS", "Battery Management", ElementType.MODULE, "C_MCU")
    create_arch("SW_UI", "UI Logik", ElementType.MODULE, "C_MCU")
    create_arch("SW_PRESSURE", "Druckauswertung", ElementType.MODULE, "C_MCU")

    create_arch("A_TRAVEL_CASE", "Reise-Etui", ElementType.COMPONENT, "SS_BASE")
    create_arch("C_CASE_BATTERY", "Etui Powerbank", ElementType.COMPONENT, "A_TRAVEL_CASE")
    create_arch("C_CASE_PCBA", "Etui Ladeelektronik", ElementType.COMPONENT, "A_TRAVEL_CASE")
    create_arch("P_CASE_HINGE", "Scharnier", ElementType.COMPONENT, "A_TRAVEL_CASE")
    create_arch("SW_APP_DASH", "App Dashboard", ElementType.MODULE, "SS_APP")
    create_arch("SW_APP_SYNC", "App Sync Manager", ElementType.MODULE, "SS_APP")
    
    # 3. Requirements (180+)
    print("Creating Requirements...")
    reqs = {}
    
    def create_req(key, title, parent_need=None, parent_req=None, allocated_arch=None):
        r = req_svc.create_requirement(workspace_id=ws_id, title=title, ctx=ctx, type=RequirementType.SYREQ)
        reqs[key] = r
        if parent_need:
            link_svc.create_trace_link(source_id=r.artifact_id, target_id=parent_need.artifact_id, link_type="satisfies", ctx=ctx)
        if parent_req:
            link_svc.create_trace_link(source_id=r.artifact_id, target_id=parent_req.artifact_id, link_type="derives-from", ctx=ctx)
        if allocated_arch:
            link_svc.create_trace_link(source_id=r.artifact_id, target_id=allocated_arch.artifact_id, link_type="allocated-to", ctx=ctx)
        return r

    realistic_l1 = [
        "Der BLDC-Motor muss eine Drehzahl von 5000 RPM erreichen.",
        "Die Akkuladezeit darf 3 Stunden nicht überschreiten.",
        "Das Gehäuse muss nach IPX7 wasserdicht sein.",
        "Der Drucksensor muss bei > 2.5N auslösen.",
        "Die Bluetooth-Verbindung muss bis 10m stabil sein.",
        "Die Geräuschemission darf 60 dB(A) nicht überschreiten.",
        "Das Etui muss die Zahnbürste induktiv laden können.",
        "Die App muss wöchentliche Putz-Reports generieren.",
        "Der Bürstenkopf muss Vibrationen von 300Hz aushalten.",
        "Der Ladestrom darf 1A nicht überschreiten."
    ]

    for i, n in enumerate(needs):
        for j in range(2):
            text = realistic_l1[(i * 2 + j) % len(realistic_l1)]
            create_req(f"L1_{i}_{j}", text, parent_need=n, allocated_arch=archs["SYS"])

    realistic_l2 = [
        "Die MCU muss den PWM-Kanal 1 für die Motorsteuerung verwenden.",
        "Das Batterie-Management-System muss Überladung bei 4.2V verhindern.",
        "Die Dichtung am Schalter muss einem Wasserdruck von 1 bar standhalten.",
        "Der Analog-Digital-Wandler muss den Drucksensor mit 12-Bit Auflösung abtasten.",
        "Der BLE Stack muss im Advertising Mode weniger als 1mA Strom verbrauchen.",
        "Die Spule muss eine Induktivität von 10µH aufweisen.",
        "Das Reise-Etui muss aus kratzfestem Polycarbonat bestehen."
    ]

    l1_keys = [k for k in reqs.keys() if k.startswith("L1_")]
    for i, l1k in enumerate(l1_keys):
        for j in range(3):
            arch_key = ["SS_HANDLE", "SS_HEAD", "SS_BASE", "SS_APP"][j % 4]
            text = realistic_l2[(i * 3 + j) % len(realistic_l2)]
            create_req(f"L2_{i}_{j}", text, parent_req=reqs[l1k], allocated_arch=archs[arch_key])
            
    realistic_l3 = [
        "Widerstand R1 muss 10kOhm mit 1% Toleranz betragen.",
        "Die Leiterplatte (PCBA) muss 4 Lagen Kupfer (35µm) aufweisen.",
        "Der Rotor-Magnet muss aus Neodym (NdFeB) N42 bestehen.",
        "Die Gummierung des Griffes muss einen Reibungskoeffizienten >0.8 aufweisen.",
        "Die Firmware muss per OTA Update aktualisierbar sein.",
        "Das UI-Dashboard muss in React Native implementiert werden."
    ]

    l2_keys = [k for k in reqs.keys() if k.startswith("L2_")]
    for i, l2k in enumerate(l2_keys):
        for j in range(2):
            arch_options = list(archs.values())[5:]
            arch_key = list(archs.keys())[5 + ((i+j) % (len(archs)-5))]
            text = realistic_l3[(i * 2 + j) % len(realistic_l3)]
            create_req(f"L3_{i}_{j}", text, parent_req=reqs[l2k], allocated_arch=archs[arch_key])

    realistic_l4 = [
        "Das OTA-Modul muss AES-256 Verschlüsselung nutzen.",
        "Die Bluetooth-Paketgröße muss auf 256 Bytes limitiert sein.",
        "Das Neodym-Material muss eine Koerzitivfeldstärke von >800 kA/m haben.",
        "Der Widerstand R1 muss vom Typ SMD 0603 sein.",
        "Das Spritzguss-Werkzeug für die Gummierung muss eine Toleranz von 0.1mm aufweisen."
    ]

    l3_keys = [k for k in reqs.keys() if k.startswith("L3_")]
    for i, l3k in enumerate(l3_keys):
        for j in range(1):
            arch_options = list(archs.values())[10:]
            arch_key = list(archs.keys())[10 + ((i+j) % (len(archs)-10))]
            text = realistic_l4[(i + j) % len(realistic_l4)]
            create_req(f"L4_{i}_{j}", text, parent_req=reqs[l3k], allocated_arch=archs[arch_key])

    realistic_l5 = [
        "Der C-Code für das OTA-Modul muss MISRA-C kompatibel sein.",
        "Der Compiler-Optimierungsgrad muss -O2 betragen.",
        "Die Lötpaste für SMD 0603 muss bleifrei (RoHS-konform) sein.",
        "Das Magnet-Sinterverfahren muss bei 1100°C unter Vakuum erfolgen."
    ]

    l4_keys = [k for k in reqs.keys() if k.startswith("L4_")]
    for i, l4k in enumerate(l4_keys):
        for j in range(1):
            arch_options = list(archs.values())[-5:]
            arch_key = list(archs.keys())[-5 + ((i+j) % 5)]
            text = realistic_l5[(i + j) % len(realistic_l5)]
            create_req(f"L5_{i}_{j}", text, parent_req=reqs[l4k], allocated_arch=archs[arch_key])

    # 4. ICDs (90+)
    print("Creating Interfaces (ICDs)...")
    icds = []
    arch_keys = list(archs.keys())
    icd_names = ["SPI Data Link", "Power Line 5V", "Mechanical Mount", "I2C Sensor Bus", "BLE RF Link", "Inductive Energy Transfer", "UART Debug"]
    for i in range(95):
        src_idx = i % (len(arch_keys) // 2)
        tgt_idx = (len(arch_keys) // 2) + (i % (len(arch_keys) - len(arch_keys) // 2))
        src_key = arch_keys[src_idx]
        tgt_key = arch_keys[tgt_idx]
        payload = IcdCreateDTO(
            tenant_id=tenant.id,
            workspace_id=ws_id,
            name=f"{icd_names[i % len(icd_names)]} ({src_key} -> {tgt_key})",
            source_element_id=archs[src_key].id,
            target_element_id=archs[tgt_key].id,
            direction="unidirectional",
            interface_type="mechanical" if i % 2 == 0 else "electrical",
            semantic_description="Auto-generierte Schnittstelle zur Verifikation",
            created_by_id=user.id
        )
        res = create_icd(payload)
        icds.append(res)
        
    # 5. Risks (20+)
    print("Creating Risks...")
    risk_texts = ["Wassereintritt am Schalter", "Akku-Überhitzung beim Laden", "Verlust der Bluetooth-Verbindung", "Abnutzung der Rotorwelle", "Ausfall des Drucksensors"]
    for i in range(22):
        r = risk_svc.create_risk(
            workspace_id=ws_id,
            title=risk_texts[i % len(risk_texts)],
            probability="medium",
            impact="high",
            ctx=ctx,
            description="Mögliches Risiko während der Produktlebensdauer bei intensiver Nutzung.",
            category="technical",
            status="Identified"
        )
        req_key = list(reqs.keys())[i % len(reqs)]
        # REQ-L2-TE-020: RiskService.create_risk now creates the backing Artifact
        # via a proper OneToOne FK — use r.artifact_id instead of the former
        # UUID-identity hack (Artifact.objects.create(id=r.id, ...)).
        link_svc.create_trace_link(source_id=r.artifact_id, target_id=reqs[req_key].artifact_id, link_type="traces", ctx=ctx)

    # 6. Issues (50+)
    print("Creating Issues...")
    issue_texts = ["Spaltmaß am Gehäuse zu groß", "PWM Frequenz verursacht Pfeifen", "Firmware OTA bricht ab", "Batterieanzeige ungenau", "Etui schließt nicht bündig"]
    for i in range(55):
        iss = issue_svc.create_issue(
            workspace_id=ws_id,
            title=issue_texts[i % len(issue_texts)],
            status="Open",
            severity="high",
            ctx=ctx,
            description="Problem aufgetreten während der Integrationstests der Vorserie."
        )
        arch_key = arch_keys[i % len(arch_keys)]
        # REQ-L2-TE-020: IssueService.create_issue now creates the backing
        # Artifact via a proper OneToOne FK — use iss.artifact_id instead of the
        # former UUID-identity hack (Artifact.objects.create(id=iss.id, ...)).
        link_svc.create_trace_link(source_id=iss.artifact_id, target_id=archs[arch_key].artifact_id, link_type="traces", ctx=ctx)

    # 7. ADRs (10+)
    print("Creating ADRs...")
    adr_texts = ["Verwendung von BLE 5.2 statt 5.0", "Wechsel auf Cortex-M4 MCU", "Gehäuse aus rPET Material", "Implementierung von OTA via App", "Wegfall der Ladeanzeige-LED am Etui"]
    for i in range(12):
        adr = adr_svc.create_adr(
            workspace_id=ws_id,
            title=adr_texts[i % len(adr_texts)],
            status="Approved",
            description="Entscheidung getroffen aufgrund von Kosten vs. Nutzen Analyse sowie Lieferketten-Stabilität.",
            ctx=ctx
        )
        arch_key = arch_keys[i % len(arch_keys)]
        # REQ-L2-TE-020: AdrService.create_adr already creates the backing
        # Artifact via a proper OneToOne FK — use adr.artifact_id instead of the
        # former UUID-identity hack (which created a second, orphan Artifact).
        link_svc.create_trace_link(source_id=adr.artifact_id, target_id=archs[arch_key].artifact_id, link_type="documents", ctx=ctx)

    print("Creating TestCases and TestRuns...")
    test_cases = []
    for i, req in enumerate(list(reqs.values())[:30]):
        tc = test_svc.create_test_case(
            workspace_id=ws_id,
            title=f"Test für: {req.title}",
            ctx=ctx,
            description="Automatisiert generierter Testfall zur Verifikation.",
            test_type="System"
        )
        link_svc.create_trace_link(source_id=tc.artifact_id, target_id=req.artifact_id, link_type="verifies", ctx=ctx)
        test_cases.append(tc)

    tr1 = test_run_svc.create_test_run(
        workspace_id=ws_id,
        name="Nightly Build Test Run",
        ctx=ctx,
        test_case_ids=[tc.id for tc in test_cases[:15]]
    )
    tr2 = test_run_svc.create_test_run(
        workspace_id=ws_id,
        name="Release Candidate 1.0",
        ctx=ctx,
        test_case_ids=[tc.id for tc in test_cases[15:30]]
    )
    
    for tc in test_cases[:10]:
        test_run_svc.add_result(test_run_id=tr1.id, test_case_id=tc.id, status="passed", ctx=ctx, message="Test erfolgreich durchlaufen.")
    for tc in test_cases[10:15]:
        test_run_svc.add_result(test_run_id=tr1.id, test_case_id=tc.id, status="failed", ctx=ctx, message="Timeout nach 5 Sekunden.")

    clear_request_tenant()
    print("Seeding completed successfully!")


class Command(BaseCommand):
    help = "Seed the 'Zahnbürste SysEng Demo' workspace used by the E2E suite."

    def handle(self, *args: Any, **options: Any) -> None:
        run()
