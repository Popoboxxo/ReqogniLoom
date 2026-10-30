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
    python manage.py seed_toothbrush --backfill-se-attributes   # existing workspace
"""
from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from application.actor_service import ActorService
from application.adr_service import AdrService
from application.architecture_service import ArchitectureService
from application.artifact_attribute_gateway import (
    ArtifactAttributeGateway,
    AttributeValues,
)
from application.attribute_definition_service import AttributeDefinitionNotFound
from application.glossary_service import GlossaryService
from application.issue_service import IssueService
from application.requirement_service import RequirementService
from application.risk_service import RiskService
from application.test_run_service import TestRunService
from application.test_service import TestService
from application.trace_link_service import TraceLinkService
from application.workspace_service import WorkspaceService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.provisioning import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_USERNAME
from icd.services import IcdCreateDTO, create_icd
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Actor,
    Artifact,
    ElementType,
    MoSCoWPriority,
    Requirement,
    RequirementType,
    StakeholderNeed,
    Tenant,
    User,
    Workspace,
)

WORKSPACE_NAME = "Zahnbürste SysEng Demo"

#: Plan B / WP B1 (B1-T2): SE content per requirement title.
#:
#: Every title in ``realistic_l1`` … ``realistic_l5`` maps to a deterministic
#: ``(acceptance_criteria, rationale)`` pair. The criteria are measurable
#: ("Gegeben … wenn … dann …" with a quantity and its target), derived from the
#: title text itself; the rationale states the engineering reason and names the
#: driving stakeholder need where one exists. Titles (and therefore the
#: hierarchy the E2E spec asserts) are untouched — this is content, not shape.
SE_ATTRIBUTES_BY_TITLE: dict[str, tuple[str, str]] = {
    # ---- L1 System requirements -------------------------------------------------
    "Der BLDC-Motor muss eine Drehzahl von 5000 RPM erreichen.": (
        "Gegeben der BLDC-Motor im Nennbetrieb, wenn die Nenndrehzahl angelegt "
        "wird, dann liegt die gemessene Drehzahl über 10 min Dauerlauf bei "
        "5000 RPM ± 2 %.",
        "Die Reinigungsleistung folgt der Antriebsdrehzahl; 5000 RPM ist der aus "
        "Stakeholder-Need N-01 (gründliche Reinigung) abgeleitete Sollwert.",
    ),
    "Die Akkuladezeit darf 3 Stunden nicht überschreiten.": (
        "Gegeben ein entladener Akku, wenn er an der Ladestation vollständig "
        "geladen wird, dann ist die Ladezeit ≤ 180 min (Messung mit "
        "Leistungsmessgerät, Abtastung 1 Hz).",
        "Need N-12 fordert maximal 4 h Ladezeit; auf Systemebene wird mit 3 h "
        "eine Reserve für Reisen eingehalten.",
    ),
    "Das Gehäuse muss nach IPX7 wasserdicht sein.": (
        "Gegeben ein geschlossenes Gehäuse, wenn es 30 min bei 1 m Wassertiefe "
        "getaucht wird, dann dringt kein Wasser ein (IPX7-Prüfung: Sichtprüfung "
        "+ Isolationsmessung).",
        "Need N-03 fordert IPX7; die Dichtheit ist Voraussetzung für die "
        "Reinigung unter fließendem Wasser.",
    ),
    "Der Drucksensor muss bei > 2.5N auslösen.": (
        "Gegeben der montierte Drucksensor, wenn eine Kraft von 2,6 N auf die "
        "Borsten wirkt, dann wird ein Auslösesignal ausgegeben (Kraftmessdose, "
        "10 Wiederholungen).",
        "Need N-04 verlangt eine Andruckwarnung; der Schwellwert 2,5 N ist der "
        "Grenzwert für gesundes Zähneputzen.",
    ),
    "Die Bluetooth-Verbindung muss bis 10m stabil sein.": (
        "Gegeben eine freie Sichtverbindung, wenn die Zahnbürste bis 10 m von "
        "der App entfernt ist, dann bleibt die BLE-Verbindung 5 min ohne Abriss "
        "(RSSI ≥ -85 dBm).",
        "Need N-05 verlangt eine Begleit-App; 10 m deckt die typische Nutzung "
        "im Badezimmer ab.",
    ),
    "Die Geräuschemission darf 60 dB(A) nicht überschreiten.": (
        "Gegeben der Betrieb im Standardmodus, wenn der Schalldruckpegel in "
        "30 cm Abstand gemessen wird, dann liegt er ≤ 60 dB(A).",
        "Need N-08 fordert unter 60 dB; der Wert begrenzt die Motor- und "
        "Getriebeauslegung.",
    ),
    "Das Etui muss die Zahnbürste induktiv laden können.": (
        "Gegeben die Zahnbürste auf dem Etui, wenn das Etui mit Strom versorgt "
        "wird, dann lädt die Zahnbürste mit ≥ 1 W induktiv (Messung über 30 min).",
        "Need N-07 fordert ein Etui mit Ladefunktion; die induktive Kopplung "
        "vermeidet offene Kontakte.",
    ),
    "Die App muss wöchentliche Putz-Reports generieren.": (
        "Gegeben mindestens sieben aufgezeichnete Putzsessions, wenn die App den "
        "Wochenreport erzeugt, dann enthält er alle sieben Tage mit Putzdauer und "
        "Abdeckung.",
        "Need N-05 fordert Putz-Statistiken; der Wochenreport ist das sichtbare "
        "Ergebnis der Datenerfassung.",
    ),
    "Der Bürstenkopf muss Vibrationen von 300Hz aushalten.": (
        "Gegeben der montierte Bürstenkopf, wenn er 10 min mit 300 Hz bei 2 mm "
        "Hub angeregt wird, dann tritt kein Ermüdungsbruch und kein Lockern der "
        "Borsten auf.",
        "Die Borsten müssen die Nennfrequenz des Antriebs dauerhaft übertragen; "
        "Need N-14 (Zahnfleisch-Schutz) setzt formstabile Borsten voraus.",
    ),
    "Der Ladestrom darf 1A nicht überschreiten.": (
        "Gegeben der Ladevorgang, wenn der Ladestrom über 30 min gemessen wird, "
        "dann liegt er ≤ 1,0 A (Stromzange, Abtastung 1 Hz).",
        "Begrenzt die Verlustleistung und schützt die Li-Ion-Zelle; leitet sich "
        "aus Need N-12 (Ladezeit) ab.",
    ),
    # ---- L2 Subsystem requirements ----------------------------------------------
    "Die MCU muss den PWM-Kanal 1 für die Motorsteuerung verwenden.": (
        "Gegeben die MCU im Motorbetrieb, wenn das PWM-Signal geprüft wird, dann "
        "liegt der Motor-Treiber ausschließlich auf Kanal 1 (Oszilloskop, alle "
        "anderen Kanäle inaktiv).",
        "Kanal 1 ist im Pinplan für den Motor-Treiber reserviert; die feste "
        "Zuordnung verhindert Fehlkonfigurationen in der Firmware.",
    ),
    "Das Batterie-Management-System muss Überladung bei 4.2V verhindern.": (
        "Gegeben eine Ladespannung von 4,3 V, wenn der BMS-Test 5 min läuft, dann "
        "schaltet das BMS den Ladepfad bei 4,2 V ± 1 % ab.",
        "Überladung ist das Hauptrisiko der Li-Ion-Zelle; der Abschaltpunkt "
        "4,2 V folgt aus dem Zell-Datenblatt.",
    ),
    "Die Dichtung am Schalter muss einem Wasserdruck von 1 bar standhalten.": (
        "Gegeben die Schalterdichtung, wenn sie 10 min mit 1 bar beaufschlagt "
        "wird, dann bleibt sie dicht (Druckabfall < 0,05 bar).",
        "Der Schalter ist die kritischste Durchführung im Gehäuse; die Dichtung "
        "trägt die IPX7-Anforderung aus L1.",
    ),
    "Der Analog-Digital-Wandler muss den Drucksensor mit 12-Bit Auflösung abtasten.": (
        "Gegeben der Drucksensor am ADC, wenn eine Referenzspannung von 3,3 V "
        "anliegt, dann wird der Messwert mit 12 Bit (Auflösung ≤ 0,8 mV) "
        "digitalisiert.",
        "Die 12-Bit-Auflösung ist nötig, um die 2,5-N-Schwelle aus L1 mit "
        "ausreichender Toleranz zu erkennen.",
    ),
    "Der BLE Stack muss im Advertising Mode weniger als 1mA Strom verbrauchen.": (
        "Gegeben der BLE-Stack im Advertising Mode, wenn der Strom über 60 s "
        "gemessen wird, dann liegt der Mittelwert < 1 mA.",
        "Advertising läuft dauerhaft und dominiert den Ruhestrom; der Wert "
        "sichert Need N-02 (zwei Wochen Akkulaufzeit).",
    ),
    "Die Spule muss eine Induktivität von 10µH aufweisen.": (
        "Gegeben die montierte Induktionsspule, wenn die Induktivität bei 100 kHz "
        "gemessen wird, dann beträgt sie 10 µH ± 10 %.",
        "Die Induktivität bestimmt die Resonanzfrequenz des Ladekreises und damit "
        "den Wirkungsgrad der induktiven Ladung aus L1.",
    ),
    "Das Reise-Etui muss aus kratzfestem Polycarbonat bestehen.": (
        "Gegeben ein Etui-Gehäuse, wenn es 500 Zyklen mit 1 kg Last und 500 g "
        "Sand beaufschlagt wird, dann sind Kratzer ≤ 0,1 mm tief (Sichtprüfung "
        "unter Normlicht).",
        "Need N-07 verlangt ein Reise-Etui; Polycarbonat liefert die geforderte "
        "Kratzfestigkeit bei geringem Gewicht.",
    ),
    # ---- L3 Component requirements ----------------------------------------------
    "Widerstand R1 muss 10kOhm mit 1% Toleranz betragen.": (
        "Gegeben der bestückte Widerstand R1, wenn er bei 25 °C gemessen wird, "
        "dann liegt sein Wert bei 10 kΩ ± 1 %.",
        "R1 ist der Referenzwiderstand der Druckmessung; 1 % Toleranz hält den "
        "Messfehler innerhalb der ADC-Spezifikation.",
    ),
    "Die Leiterplatte (PCBA) muss 4 Lagen Kupfer (35µm) aufweisen.": (
        "Gegeben ein PCBA-Querschnitt, wenn die Kupferlagen im Schliff gezählt "
        "werden, dann sind 4 Lagen mit je 35 µm Kupfer vorhanden.",
        "Vier Lagen trennen HF (BLE), Leistung (Motor) und Sensorik; 35 µm "
        "tragen den Ladestrom aus L1.",
    ),
    "Der Rotor-Magnet muss aus Neodym (NdFeB) N42 bestehen.": (
        "Gegeben ein Rotor-Magnetenmuster, wenn die Materialanalyse (EDX) "
        "durchgeführt wird, dann ist NdFeB der Güteklasse N42 nachgewiesen.",
        "Die Magnetgüte bestimmt das Drehmoment; N42 erfüllt die "
        "Drehzahlanforderung aus L1 bei kompakter Bauform.",
    ),
    "Die Gummierung des Griffes muss einen Reibungskoeffizienten >0.8 aufweisen.": (
        "Gegeben der Griff im nassen Zustand, wenn die Reibkraft mit 5 N "
        "Normalkraft gemessen wird, dann ist der Reibungskoeffizient > 0,8.",
        "Need N-09 fordert einen rutschfesten Griff; der nasse Zustand ist der "
        "ungünstigste Betriebsfall.",
    ),
    "Die Firmware muss per OTA Update aktualisierbar sein.": (
        "Gegeben eine Zahnbürste mit Firmware v1.0, wenn ein OTA-Paket "
        "übertragen wird, dann ist die neue Firmware nach ≤ 5 min aktiv und die "
        "Version wird in der App angezeigt.",
        "Field-Updates vermeiden Rückrufe; die Update-Fähigkeit ist "
        "Voraussetzung für die App-Funktionen aus Need N-05.",
    ),
    "Das UI-Dashboard muss in React Native implementiert werden.": (
        "Gegeben das App-Repository, wenn der Build erzeugt wird, dann liegen "
        "≥ 95 % des UI-Codes in React-Native-Komponenten (Dateitypen-Zählung im "
        "Build-Report).",
        "Eine einheitliche React-Native-Codebasis bedient iOS und Android und "
        "hält die Wartungskosten der Coaching-App niedrig.",
    ),
    # ---- L4 Presentation requirements -------------------------------------------
    "Das OTA-Modul muss AES-256 Verschlüsselung nutzen.": (
        "Gegeben ein OTA-Paket, wenn es mit dem hinterlegten Schlüssel geprüft "
        "wird, dann ist es AES-256-verschlüsselt und ohne gültigen Schlüssel "
        "nicht entschlüsselbar (Negativtest).",
        "Firmware ist ein Angriffsziel; die Verschlüsselung schützt Integrität "
        "und Vertraulichkeit der Updates aus L3.",
    ),
    "Die Bluetooth-Paketgröße muss auf 256 Bytes limitiert sein.": (
        "Gegeben eine BLE-Übertragung, wenn ein Datenpaket erzeugt wird, dann "
        "ist seine Nutzlast ≤ 256 Byte (Payload-Dump im Test).",
        "Die Paketgröße begrenzt die Latenz der Putzdatenübertragung und passt "
        "in das BLE-ATT-Fenster.",
    ),
    "Das Neodym-Material muss eine Koerzitivfeldstärke von >800 kA/m haben.": (
        "Gegeben ein Materialmuster des Rotor-Magneten, wenn die "
        "Koerzitivfeldstärke im Hysteresemessgerät gemessen wird, dann liegt sie "
        "> 800 kA/m.",
        "Die Koerzitivfeldstärke sichert die Entmagnetisierungsfestigkeit bei "
        "Motortemperaturen über 80 °C.",
    ),
    "Der Widerstand R1 muss vom Typ SMD 0603 sein.": (
        "Gegeben der Bestückungsplan, wenn die Bauteillage von R1 geprüft wird, "
        "dann ist das Gehäuse SMD 0603 (Bestückungsprüfung, CAD-Abgleich).",
        "0603 ist die Standardbauform der PCBA und sichert die Bestückbarkeit "
        "bei hoher Packungsdichte.",
    ),
    "Das Spritzguss-Werkzeug für die Gummierung muss eine Toleranz von 0.1mm aufweisen.": (
        "Gegeben das Spritzguss-Werkzeug, wenn ein Musterteil vermessen wird, "
        "dann liegt die Maßabweichung der Gummierung ≤ 0,1 mm (KMG-Messung, "
        "5 Teile).",
        "Die Werkzeugtoleranz bestimmt die Passgenauigkeit der Gummierung und "
        "damit die Rutschfestigkeit aus L3.",
    ),
    # ---- L5 Implementation requirements -----------------------------------------
    "Der C-Code für das OTA-Modul muss MISRA-C kompatibel sein.": (
        "Gegeben der C-Quellcode des OTA-Moduls, wenn der statische Analysator "
        "(MISRA-C-Prüfer) läuft, dann werden 0 Pflichtregel-Verstöße gemeldet.",
        "MISRA-C reduziert Sprachfeatures mit unsicherem Laufzeitverhalten — "
        "kritisch für sicherheitsrelevante Firmware-Updates.",
    ),
    "Der Compiler-Optimierungsgrad muss -O2 betragen.": (
        "Gegeben das Build-Skript, wenn die Release-Firmware gebaut wird, dann "
        "ist die Compiler-Optimierungsstufe -O2 (Build-Log).",
        "-O2 liefert die nötige Rechenleistung für Regelung und BLE bei "
        "akzeptabler Codegröße.",
    ),
    "Die Lötpaste für SMD 0603 muss bleifrei (RoHS-konform) sein.": (
        "Gegeben eine Lötpastenprobe, wenn die Röntgenfluoreszenzanalyse "
        "durchgeführt wird, dann liegt der Bleigehalt < 0,1 % (RoHS-Grenzwert).",
        "RoHS-Konformität ist Einfuhrvoraussetzung für den EU-Markt "
        "(Need N-17, Zertifizierungen).",
    ),
    "Das Magnet-Sinterverfahren muss bei 1100°C unter Vakuum erfolgen.": (
        "Gegeben das Sinterverfahren, wenn der Prozess 120 min läuft, dann liegt "
        "die Ofentemperatur konstant bei 1100 °C ± 10 K unter Vakuum "
        "≤ 10⁻³ mbar (Prozesslog).",
        "Das Sinterprofil bestimmt Dichte und Koerzitivfeldstärke des Magneten; "
        "Vakuum verhindert Oxidation.",
    ),
}

#: B1-T2: verification method per cascade level (values from
#: ``persistence.models.VerificationMethod``). L5 rows carry ``level=None``
#: (``RequirementLevel`` spans L1-L4 only), so level 5 is reached via the
#: ``None`` fallback in :func:`_level_of`.
VERIFICATION_METHOD_BY_LEVEL: dict[int, str] = {
    1: "Test",
    2: "Test",
    3: "Analysis",
    4: "Inspection",
    5: "Review",
}

#: B1-T2: priority per cascade level (scale of the Requirement attribute
#: definition: low | medium | high | critical).
PRIORITY_BY_LEVEL: dict[int, str] = {
    1: "high",
    2: "medium",
    3: "medium",
    4: "low",
    5: "low",
}


def _level_of(requirement: Requirement) -> int:
    """Return the cascade level for the SE-attribute tables.

    ``Requirement.level`` spans L1-L4 only; L5 (implementation) rows keep
    ``level=None`` and are mapped to 5, exactly like the seed's own L5 block.
    """
    level = requirement.level
    return level if level in PRIORITY_BY_LEVEL else 5


def _write_system_fields(
    ctx: AuthContext,
    requirement: Requirement,
    actor: Actor,
    *,
    priority: str | None = None,
) -> None:
    """Fill ``owner``/``priority`` on the requirement's backing Artifact.

    Only *empty* values are written, so the same helper serves creation (both
    empty) and the idempotent backfill. The gateway is the single write seam
    REST and MCP use, so the seed cannot produce attribute state a transport
    could not produce itself. A stack without bootstrapped attribute
    definitions (self-init skipped and the E2E workflow's explicit
    ``bootstrap_attribute_definitions`` runs *after* this seed) has nothing to
    validate against; the gateway then raises
    ``AttributeDefinitionNotFound`` and the two Artifact columns are written
    directly — the same rows the gateway would persist.
    """
    core: dict[str, Any] = {}
    if requirement.artifact.owner_id is None:
        core["owner"] = {"kind": "user", "id": str(actor.id)}
    if priority is not None and not (requirement.artifact.priority or "").strip():
        core["priority"] = priority
    if not core:
        return
    try:
        ArtifactAttributeGateway().write(
            ctx, "Requirement", requirement, AttributeValues(core=dict(core))
        )
    except AttributeDefinitionNotFound:
        fallback: dict[str, Any] = {}
        if "owner" in core:
            fallback["owner"] = actor
        if "priority" in core:
            fallback["priority"] = priority
        Artifact.unscoped.filter(id=requirement.artifact_id).update(**fallback)


def _resolve_tenant_and_user() -> tuple[Tenant, User]:
    """Resolve the admin's tenant/user, bootstrapping both when absent."""
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
    return tenant, user


def _build_auth_context(tenant: Tenant, user: User) -> AuthContext:
    """Build the seeding auth context for the resolved tenant/user."""
    return AuthContext(
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


def _find_existing_workspace(tenant: Tenant) -> Workspace | None:
    """Return the already seeded demo workspace, if a previous run created it."""
    return Workspace.objects.filter(
        tenant_id=tenant.id, name=WORKSPACE_NAME
    ).first()


def _create_workspace(ctx: AuthContext) -> Workspace:
    """Create the demo workspace and echo its ID."""
    print("Creating Workspace...")
    ws = WorkspaceService().create_workspace(ctx=ctx, name=WORKSPACE_NAME, preset="extended", terminology_profile="se_mode")
    print(f"Workspace created with ID: {ws.id}")
    return ws


def _create_glossary(ctx: AuthContext, ws_id: Any) -> None:
    """Seed the demo glossary terms."""
    print("Creating Glossary Terms...")
    svc = GlossaryService()
    terms = [
        ("BLDC", "Brushless DC Motor - Ein bürstenloser Gleichstrommotor für hohe Effizienz."),
        ("IPX7", "Schutz gegen zeitweiliges Untertauchen in Wasser."),
        ("BLE", "Bluetooth Low Energy - Ein Funkstandard für energiesparende Datenübertragung."),
        ("MCU", "Microcontroller Unit - Der Hauptprozessor der Zahnbürste."),
        ("PCBA", "Printed Circuit Board Assembly - Bestückte Leiterplatte."),
    ]
    for term, definition in terms:
        svc.create(ctx=ctx, workspace_id=ws_id, term=term, definition=definition)


def _create_stakeholder_needs(
    ctx: AuthContext, ws_id: Any, tenant: Tenant, user: User
) -> list[Any]:
    """Create the L0 stakeholder needs driving the requirement cascade."""
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
            # G1.3/#1402: denormalized workspace back-reference; without it the
            # seeded needs are exempt from uq_stakeholder_need_workspace_uid.
            workspace_id=ws_id,
            title=title,
            description=details,
            moscow_priority=MoSCoWPriority.MUST,
            created_by_id=user.id
        )
        needs.append(n)
    return needs


def _create_architecture(ctx: AuthContext, ws_id: Any) -> dict[str, Any]:
    """Create the L1-L3 architecture decomposition, keyed by internal name."""
    archs: dict[str, Any] = {}

    def create_arch(key, title, el_type, parent_key=None):
        parent_id = archs[parent_key].id if parent_key else None
        a = ArchitectureService().create_architecture_element(workspace_id=ws_id, title=title, ctx=ctx, element_type=el_type, parent_id=parent_id)
        archs[key] = a
        return a

    print("Creating Architecture Elements...")
    create_arch("SYS", "Smart Toothbrush System", ElementType.SUBSYSTEM)
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
    return archs


def _create_requirements(
    ctx: AuthContext,
    ws_id: Any,
    needs: list[Any],
    archs: dict[str, Any],
    user: User,
) -> dict[str, Any]:
    """Create the L1-L5 requirements with derivation and allocation trace links.

    Plan B / WP B1 (B1-T2): every requirement is created with its measurable
    acceptance criteria, its rationale and the level's verification method, and
    the backing Artifact receives an owner (the seeding admin) and a priority —
    so the fixture demonstrates SE content, not just hierarchy.
    """
    print("Creating Requirements...")
    req_svc = RequirementService()
    link_svc = TraceLinkService()
    reqs: dict[str, Any] = {}
    # One Actor per run: resolving it per requirement would create/query the
    # same row 880 times.
    actor = ActorService().get_or_create_for_user(ctx, user.id)

    def create_req(key, title, parent_need=None, parent_req=None, allocated_arch=None, level=1):
        acceptance_criteria, rationale = SE_ATTRIBUTES_BY_TITLE[title]
        r = req_svc.create_requirement(
            workspace_id=ws_id,
            title=title,
            ctx=ctx,
            type=RequirementType.SYREQ,
            acceptance_criteria=acceptance_criteria,
            rationale=rationale,
            verification_method=VERIFICATION_METHOD_BY_LEVEL[level],
        )
        # #1288: mirror the free text into the structured criteria list, the
        # same single-criterion shape migration 0113 imported it with.
        r.acceptance_criteria_items = [
            {"text": acceptance_criteria, "fulfilled": False, "evidence_ref": None}
        ]
        r.save(update_fields=["acceptance_criteria_items", "modified_at"])
        reqs[key] = r
        _write_system_fields(ctx, r, actor, priority=PRIORITY_BY_LEVEL[level])
        if parent_need:
            # The retired ArchitectureElement -> Requirement satisfaction key:
            # a Requirement pointing at the Need it came from is a derivation,
            # so the migration rewrote these rows to derives-from with their
            # endpoints left alone (child -> parent).
            link_svc.create_trace_link(source_id=r.artifact_id, target_id=parent_need.artifact.id, link_type="derives-from", ctx=ctx)
        if parent_req:
            link_svc.create_trace_link(source_id=r.artifact_id, target_id=parent_req.artifact.id, link_type="derives-from", ctx=ctx)
        if allocated_arch:
            link_svc.create_trace_link(source_id=r.artifact_id, target_id=allocated_arch.artifact.id, link_type="allocated-to", ctx=ctx)
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
            create_req(f"L1_{i}_{j}", text, parent_need=n, allocated_arch=archs["SYS"], level=1)

    realistic_l2 = [
        "Die MCU muss den PWM-Kanal 1 für die Motorsteuerung verwenden.",
        "Das Batterie-Management-System muss Überladung bei 4.2V verhindern.",
        "Die Dichtung am Schalter muss einem Wasserdruck von 1 bar standhalten.",
        "Der Analog-Digital-Wandler muss den Drucksensor mit 12-Bit Auflösung abtasten.",
        "Der BLE Stack muss im Advertising Mode weniger als 1mA Strom verbrauchen.",
        "Die Spule muss eine Induktivität von 10µH aufweisen.",
        "Das Reise-Etui muss aus kratzfestem Polycarbonat bestehen."
    ]

    l1_keys = [k for k in reqs if k.startswith("L1_")]
    for i, l1k in enumerate(l1_keys):
        for j in range(3):
            arch_key = ["SS_HANDLE", "SS_HEAD", "SS_BASE", "SS_APP"][j % 4]
            text = realistic_l2[(i * 3 + j) % len(realistic_l2)]
            create_req(f"L2_{i}_{j}", text, parent_req=reqs[l1k], allocated_arch=archs[arch_key], level=2)

    realistic_l3 = [
        "Widerstand R1 muss 10kOhm mit 1% Toleranz betragen.",
        "Die Leiterplatte (PCBA) muss 4 Lagen Kupfer (35µm) aufweisen.",
        "Der Rotor-Magnet muss aus Neodym (NdFeB) N42 bestehen.",
        "Die Gummierung des Griffes muss einen Reibungskoeffizienten >0.8 aufweisen.",
        "Die Firmware muss per OTA Update aktualisierbar sein.",
        "Das UI-Dashboard muss in React Native implementiert werden."
    ]

    l2_keys = [k for k in reqs if k.startswith("L2_")]
    for i, l2k in enumerate(l2_keys):
        for j in range(2):
            arch_key = list(archs.keys())[5 + ((i+j) % (len(archs)-5))]
            text = realistic_l3[(i * 2 + j) % len(realistic_l3)]
            create_req(f"L3_{i}_{j}", text, parent_req=reqs[l2k], allocated_arch=archs[arch_key], level=3)

    realistic_l4 = [
        "Das OTA-Modul muss AES-256 Verschlüsselung nutzen.",
        "Die Bluetooth-Paketgröße muss auf 256 Bytes limitiert sein.",
        "Das Neodym-Material muss eine Koerzitivfeldstärke von >800 kA/m haben.",
        "Der Widerstand R1 muss vom Typ SMD 0603 sein.",
        "Das Spritzguss-Werkzeug für die Gummierung muss eine Toleranz von 0.1mm aufweisen."
    ]

    l3_keys = [k for k in reqs if k.startswith("L3_")]
    for i, l3k in enumerate(l3_keys):
        for j in range(1):
            arch_key = list(archs.keys())[10 + ((i+j) % (len(archs)-10))]
            text = realistic_l4[(i + j) % len(realistic_l4)]
            create_req(f"L4_{i}_{j}", text, parent_req=reqs[l3k], allocated_arch=archs[arch_key], level=4)

    realistic_l5 = [
        "Der C-Code für das OTA-Modul muss MISRA-C kompatibel sein.",
        "Der Compiler-Optimierungsgrad muss -O2 betragen.",
        "Die Lötpaste für SMD 0603 muss bleifrei (RoHS-konform) sein.",
        "Das Magnet-Sinterverfahren muss bei 1100°C unter Vakuum erfolgen."
    ]

    l4_keys = [k for k in reqs if k.startswith("L4_")]
    for i, l4k in enumerate(l4_keys):
        for j in range(1):
            arch_key = list(archs.keys())[-5 + ((i+j) % 5)]
            text = realistic_l5[(i + j) % len(realistic_l5)]
            create_req(f"L5_{i}_{j}", text, parent_req=reqs[l4k], allocated_arch=archs[arch_key], level=5)
    return reqs


def _create_icds(
    ctx: AuthContext, ws_id: Any, archs: dict[str, Any], tenant: Tenant, user: User
) -> None:
    """Create the 95 demo interfaces between architecture elements."""
    print("Creating Interfaces (ICDs)...")
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
        create_icd(payload)


def _create_risks(ctx: AuthContext, ws_id: Any, reqs: dict[str, Any]) -> None:
    """Create the 22 demo risks, each mitigating one requirement."""
    print("Creating Risks...")
    risk_svc = RiskService()
    link_svc = TraceLinkService()
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
        )
        req_key = list(reqs.keys())[i % len(reqs)]
        # REQ-L2-TE-020: RiskService.create_risk now creates the backing Artifact
        # via a proper OneToOne FK — use r.artifact_id instead of the former
        # UUID-identity hack (Artifact.objects.create(id=r.id, ...)).
        link_svc.create_trace_link(source_id=r.artifact_id, target_id=reqs[req_key].artifact_id, link_type="mitigates", ctx=ctx)


def _create_issues(ctx: AuthContext, ws_id: Any, archs: dict[str, Any]) -> None:
    """Create the 55 demo issues, each referencing an architecture element."""
    print("Creating Issues...")
    issue_svc = IssueService()
    link_svc = TraceLinkService()
    issue_texts = ["Spaltmaß am Gehäuse zu groß", "PWM Frequenz verursacht Pfeifen", "Firmware OTA bricht ab", "Batterieanzeige ungenau", "Etui schließt nicht bündig"]
    for i in range(55):
        iss = issue_svc.create_issue(
            workspace_id=ws_id,
            title=issue_texts[i % len(issue_texts)],
            severity="high",
            ctx=ctx,
            description="Problem aufgetreten während der Integrationstests der Vorserie."
        )
        arch_key = list(archs.keys())[i % len(archs.keys())]
        # REQ-L2-TE-020: IssueService.create_issue now creates the backing
        # Artifact via a proper OneToOne FK — use iss.artifact_id instead of
        # the former UUID-identity hack (Artifact.objects.create(id=iss.id, ...)).
        link_svc.create_trace_link(source_id=iss.artifact_id, target_id=archs[arch_key].artifact_id, link_type="references", ctx=ctx)


def _create_adrs(ctx: AuthContext, ws_id: Any, archs: dict[str, Any]) -> None:
    """Create the 12 demo ADRs, each deciding on an architecture element."""
    print("Creating ADRs...")
    adr_svc = AdrService()
    link_svc = TraceLinkService()
    adr_texts = ["Verwendung von BLE 5.2 statt 5.0", "Wechsel auf Cortex-M4 MCU", "Gehäuse aus rPET Material", "Implementierung von OTA via App", "Wegfall der Ladeanzeige-LED am Etui"]
    for i in range(12):
        adr = adr_svc.create_adr(
            workspace_id=ws_id,
            title=adr_texts[i % len(adr_texts)],
            description="Entscheidung getroffen aufgrund von Kosten vs. Nutzen Analyse sowie Lieferketten-Stabilität.",
            ctx=ctx
        )
        arch_key = list(archs.keys())[i % len(archs.keys())]
        # REQ-L2-TE-020: AdrService.create_adr already creates the backing
        # Artifact via a proper OneToOne FK — use adr.artifact_id instead of
        # the former UUID-identity hack (which created a second, orphan Artifact).
        link_svc.create_trace_link(source_id=adr.artifact_id, target_id=archs[arch_key].artifact_id, link_type="decides", ctx=ctx)


def _create_testcases_and_runs(ctx: AuthContext, ws_id: Any, reqs: dict[str, Any]) -> None:
    """Create test cases for the first 30 requirements and two test runs."""
    print("Creating TestCases and TestRuns...")
    test_svc = TestService()
    link_svc = TraceLinkService()
    test_run_svc = TestRunService()
    test_cases = []
    for req in list(reqs.values())[:30]:
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
    test_run_svc.create_test_run(
        workspace_id=ws_id,
        name="Release Candidate 1.0",
        ctx=ctx,
        test_case_ids=[tc.id for tc in test_cases[15:30]]
    )

    for tc in test_cases[:10]:
        test_run_svc.add_result(test_run_id=tr1.id, test_case_id=tc.id, status="passed", ctx=ctx, message="Test erfolgreich durchlaufen.")
    for tc in test_cases[10:15]:
        test_run_svc.add_result(test_run_id=tr1.id, test_case_id=tc.id, status="failed", ctx=ctx, message="Timeout nach 5 Sekunden.")


def run():
    print("Starting Zahnbürste SysEng Demo seeding...")
    tenant, user = _resolve_tenant_and_user()
    ctx = _build_auth_context(tenant, user)

    # COMP-PL-006: activate the Postgres RLS session variable + thread-local
    # app-layer filter for this tenant. Outside of a request, no middleware
    # runs set_request_tenant() for us, so every direct model write below
    # (e.g. the Artifact.objects.create() calls for StakeholderNeed) would
    # otherwise be rejected by the "new row violates row-level security
    # policy" Postgres policy (COMP-PL-006, migration 0003_rls_policies).
    set_request_tenant(tenant.id)

    existing = _find_existing_workspace(tenant)
    if existing is not None:
        print(f"Workspace created with ID: {existing.id}")
        print("Seeding skipped — workspace already present.")
        clear_request_tenant()
        return

    ws = _create_workspace(ctx)
    _create_glossary(ctx, ws.id)
    needs = _create_stakeholder_needs(ctx, ws.id, tenant, user)
    archs = _create_architecture(ctx, ws.id)
    reqs = _create_requirements(ctx, ws.id, needs, archs, user)
    _create_icds(ctx, ws.id, archs, tenant, user)
    _create_risks(ctx, ws.id, reqs)
    _create_issues(ctx, ws.id, archs)
    _create_adrs(ctx, ws.id, archs)
    _create_testcases_and_runs(ctx, ws.id, reqs)
    clear_request_tenant()
    print("Seeding completed successfully!")


def backfill_se_attributes() -> None:
    """B1-T3: fill only the *empty* SE attributes of the existing workspace.

    A workspace seeded before B1-T2 has no acceptance criteria, rationale,
    verification method, owner or priority. This pass fills exactly those empty
    fields for every requirement whose title is in ``SE_ATTRIBUTES_BY_TITLE``;
    a value a human already set is never overwritten, which makes the pass
    idempotent (a second run reports ``0`` changed rows).

    The level-specific values come from ``PRIORITY_BY_LEVEL`` /
    ``VERIFICATION_METHOD_BY_LEVEL`` using the requirement's own
    ``Requirement.level`` (``None`` → 5). Deliberately **not** a
    ``priority_backfill.yaml`` AWMS run (R-B1-3): that plan maps MoSCoW values
    and would have to be finalised against ENT-B5 first.
    """
    tenant, user = _resolve_tenant_and_user()
    ctx = _build_auth_context(tenant, user)
    set_request_tenant(tenant.id)
    try:
        workspace = _find_existing_workspace(tenant)
        if workspace is None:
            print(f"Workspace '{WORKSPACE_NAME}' not found — nothing to backfill.")
            return

        actor = ActorService().get_or_create_for_user(ctx, user.id)
        req_svc = RequirementService()
        changed = 0
        already_complete = 0

        requirements = Requirement.objects.filter(
            artifact__workspace_id=workspace.id
        ).select_related("artifact").order_by("id")
        for requirement in requirements:
            attributes = SE_ATTRIBUTES_BY_TITLE.get(requirement.title)
            if attributes is None:
                # Titles outside the seed catalogue are left completely alone.
                continue
            acceptance_criteria, rationale = attributes
            level = _level_of(requirement)

            updates: dict[str, Any] = {}
            if not (requirement.acceptance_criteria or "").strip():
                updates["acceptance_criteria"] = acceptance_criteria
            if not (requirement.rationale or "").strip():
                updates["rationale"] = rationale
            if not requirement.verification_method:
                updates["verification_method"] = VERIFICATION_METHOD_BY_LEVEL[level]

            # Which system fields are still empty; the helper re-checks this
            # anyway, so a stale in-memory row cannot cause an overwrite.
            needs_owner = requirement.artifact.owner_id is None
            priority = (
                None
                if (requirement.artifact.priority or "").strip()
                else PRIORITY_BY_LEVEL[level]
            )

            if not updates and not needs_owner and priority is None:
                already_complete += 1
                continue

            if updates:
                req_svc.update_requirement(
                    requirement.id,
                    ctx=ctx,
                    change_reason="B1-T3: SE-Attribute nachgezogen (Seed-Backfill)",
                    **updates,
                )
            if "acceptance_criteria" in updates and not requirement.acceptance_criteria_items:
                # #1288: keep the structured list consistent with the free text,
                # exactly as creation does (migration 0113's single item shape).
                Requirement.objects.filter(id=requirement.id).update(
                    acceptance_criteria_items=[
                        {
                            "text": updates["acceptance_criteria"],
                            "fulfilled": False,
                            "evidence_ref": None,
                        }
                    ]
                )
            if needs_owner or priority is not None:
                _write_system_fields(ctx, requirement, actor, priority=priority)
            changed += 1

        print(f"Backfilled {changed} requirements ({already_complete} already complete).")
    finally:
        clear_request_tenant()


class Command(BaseCommand):
    help = "Seed the 'Zahnbürste SysEng Demo' workspace used by the E2E suite."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--backfill-se-attributes",
            action="store_true",
            default=False,
            help=(
                "Fill only the empty SE attributes (acceptance criteria, "
                "rationale, verification method, owner, priority) of the "
                "already seeded workspace. Idempotent."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options.get("backfill_se_attributes"):
            backfill_se_attributes()
            return
        run()
