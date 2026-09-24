# Bluepencil-Integration in ReqogniLoom

> **Status: implementierter Host-/Loader-Pfad für dieQS- und Debug-Umgebung.** Dieses Dokument
> beschreibt den aktuellen Stand im Frontend, nicht einen Plugin- oder MCP-Mechanismus. Hermes,
> MCP und die Bluepencil-Host-Bridge sind getrennte Integrationspunkte.

Stand der geprüften Browser-Assets: bluepencil `0.1.0-alpha.2` unter
`frontend/public/bluepencil/latest/`. Der Sidecar ist der vendorisierte alpha.1-Stand unter
`deploy/bluepencil/server.js`.

## 1. Zweck und Betriebsgrenzen

Bluepencil ist eine optionale Review-Notiz-Schicht über der SPA. Sie ist **kein Service der
Produkt-Domäne**, keine eigene Benutzerverwaltung und keine Plugin-Registrierung. Im aktuellen
Setup ist der Store ein debug-only Sidecar mit einer JSON-Datei.

Die Schicht ist standardmäßig aus. Für den Betrieb müssen zwei Schalter passen:

| Umgebung | Schalter | Wirkung |
|---|---|---|
| Compose-Entwicklung | `COMPOSE_PROFILES=bluepencil` | startet `bluepencil:8787` |
| Compose-Entwicklung | `BLUEPENCIL_ENABLED=1` in der Root-`.env` | setzt im Dev-Override `VITE_BLUEPENCIL_ENABLED=1` |
| Produktions-Image | Build-Arg `VITE_BLUEPENCIL_ENABLED=1` | kompiliert den Loader mit aktivem Build-Guard |
| Sidecar/Loader | `BLUEPENCIL_ENVIRONMENT=dev\|staging\|live` bzw. `VITE_BLUEPENCIL_ENVIRONMENT` | muss auf beiden Seiten übereinstimmen; Default `dev` |

`VITE_BLUEPENCIL_ENABLED` wird nur als exakter String `1` akzeptiert. `BLUEPENCIL_ENABLED` ist
nur die Dev-Override-Variable; ein laufendes Vite-Dev-Server-Prozess liest sie erst beim Start.
Ein Produktions-Image liest den Guard beim Build und nicht über eine spätere Laufzeitumgebung.
`BLUEPENCIL_URL` kann in der lokalen Vite-Konfiguration den Proxy-Zielhost überschreiben; der
Frontend-Endpunkt bleibt `/bluepencil/api`.

Der Sidecar ist absichtlich **DEBUG/QS-only**. Er hat keine Benutzer-Authentifizierung, keine
Mandantentrennung und keine Audit- oder Rollenprüfung. Alle Nutzer, die den Sidecar erreichen,
können den gemeinsamen JSON-Store lesen und schreiben. Ein produktiver Store muss die normale
DRF-Authentifizierung, TenantContext/RLS, RBAC und serverseitige Validierung durchsetzen; diese
Backend-Implementierung ist nicht Teil dieses Pfades.

## 2. Loader- und Host-Bridge-Vertrag

Der Frontend-Bootstrap installiert `window.rfBluepencil` vor dem Loader-Script. Der Loader hängt
das Script nur nach erfolgreichem same-origin Health-Probe an. `attach.js` liest die folgenden
Pfade, wenn der Vendored Custom Element connected:

| Script-Attribut | Globaler Pfad | Verhalten |
|---|---|---|
| `data-identity` | `rfBluepencil.identity` | `identity.getUser()` liefert `{ name, id? }` oder `null` |
| `data-headers-from` | `rfBluepencil.headers` | synchrones `Record<string,string>` pro Sidecar-Anfrage |
| `data-gate` | `rfBluepencil.gate` | boolescher UI-Schalter |
| `data-route-from` | `rfBluepencil.routeFor` | synchroner Routing-Schlüssel |
| `data-endpoint` | — | `/bluepencil/api` |
| `data-route` | — | `url` als Fallback, falls `route-from` nicht geliefert wird |

`routeFor` bevorzugt den nächsten `[data-rf-view]`-Vorfahren und fällt auf
`window.location.pathname` zurück. Das ist nur Metadatenbildung für die Notizroute. Es ist keine
Autorisierung, kein Tenant-Kontext und keine Zugriffskontrolle.

Die Brücke verwendet stabile Wrapper-Funktionen. Dadurch können Login, Session-Restore und ein
Profil-Update die Identity-Quelle ändern, obwohl das Custom Element seine Referenzen beim
Verbinden eingefroren hat. `buildRef` bleibt als Host-Feld für einen zukünftigen Bundle-Vertrag
vorhanden, ist im aktuellen `attach.js` aber nicht über `data-build-ref` erreichbar. Der Loader
setzt deshalb bewusst kein `data-build-ref`.

### Lebenszyklus und Race-Invarianten

1. `index.tsx` installiert die Host-Globale synchron und startet den Installationsversuch ohne
   Render-Blockierung.
2. Ein laufender Health-Probe-Vorgang wird als einzelner In-flight-Vorgang geteilt. Ein zweiter
   Aufruf wartet auf denselben Vorgang und erzeugt höchstens ein Loader-Script.
3. Logout oder ein anderer Teardown erhöht die Loader-Lifecycle-Generation und markiert einen
   ausstehenden Attach-Auftrag als zurückgezogen. Ein frischer Installationsversuch wartet auf den
   Abschluss des zurückgezogenen Attach-Auftrags.
4. Der vendorte Loader sendet keine Instanz-ID. Falls der Fünf-Sekunden-Timeout vor dem
   Abschluss des Vendor-Vorgangs greift, bleibt ein Reattach für dieses Dokument deaktiviert und ein
   später nachlaufendes Element oder ein später gesetzter Attach-Handle wird entfernt. Nach diesem
   Timeout ist ein Page-Reload erforderlich; es wird keine nicht deterministische Session-Isolierung
   behauptet.
5. Logout entfernt Script und `<bluepencil-notes>`, ruft `bluepencilAttach.destroy()` auf, löscht
   den Attach-Handle und setzt `window.rfBluepencil` sowie die Identity-Quelle zurück. Ein
   anschließender Login oder Session-Restore setzt die Identity und startet die Layer-Installation
   erneut, sofern kein Attach-Timeout den Reattach für dieses Dokument gesperrt hat.

Die Auth-Race-Grenze ist damit: ein Restore-, Login- oder Profilcallback darf Identity nur
veröffentlichen, wenn seine Auth-Generation noch aktuell ist. Ein verspäteter Callback kann nach
Logout keine alte Session wiederherstellen.

## 3. Auth, Cookies und CSRF

ReqogniLoom verwendet für die SPA-Session das httpOnly-Cookie `reqogniloom_access` (REQ-052). Der
Frontend-Bundle-Code hat keinen JS-lesbaren Bearer-Token. Der Root-relative Endpoint läuft über
denselben Origin; der Browser sendet das Session-Cookie bei Same-Origin-Anfragen automatisch.
Login- und Logout-Anfragen werden pro Auth-Provider in Aufrufreihenfolge serialisiert, damit ein
verspätetes `Set-Cookie` nicht den abschließenden Cookie-Zustand überschreibt. Ein neuer Login oder
Logout bricht einen ausstehenden Login ab; ein Login-Timeout versucht zusätzlich, eine bereits
serverseitig gesetzte Session-Cookie per Logout zu kompensieren. API-401-Refresh und -Retry sind an
eine Session-Generation gebunden, damit eine alte Antwort nicht die neu angemeldete Session zerstört.

Die Host-Bridge setzt **keinen** `Authorization`-Header. Sie liest stattdessen bei jedem Aufruf das
lesbare `csrftoken`-Cookie und übergibt es als `X-CSRFToken`, sofern vorhanden. Das entspricht dem
Cookie/CSRF-Verhalten des zentralen API-Clients und ist eine Vorwärtskompatibilität für einen
DRF-Store mit CSRF-Schutz.

Der aktuelle Sidecar validiert weder `reqogniloom_access` noch `X-CSRFToken`; die Übergabe des
CSRF-Headers ist dort daher keine Autorisierungsfunktion. Ein Cookie-Transport allein macht den
Sidecar nicht sicher. Die UI-Schicht und die Root-relative Proxy-Konfiguration ersetzen keine
serverseitige Authentifizierung.

## 4. UI-Gate und Sicherheitsgrenze

`gate()` liefert in diesem Repository bewusst `true`. Es gibt keine separate Reviewer-Rolle, und
eine erfundene Rolle wäre eine falsche Berechtigungsannahme. Das Gate steuert nur, ob die
Annotations affordance in der Oberfläche erscheint; anonyme Besucher werden dadurch nicht
zuverlässig autorisiert.

Die hostseitige Identity und `routeFor` sind ausschließlich Autor-/Routing-Metadaten. Sie sind
**keine** Authentifizierung, **keine** Rollenprüfung und **keine** Mandantentrennung. Der Sidecar
besitzt keine Benutzer- oder Tenant-Isolation. Diese Grenze darf bei einer späteren Umstellung auf
einen Produktionsspeicher nicht in einen UI-Gate- oder Header-Check verlagert werden.

## 5. Build-Pin und Asset-Integrität

`latest.json` und die beiden Dateien unter `frontend/public/bluepencil/latest/` werden als
versionierter Vendored-Satz ausgeliefert:

- Manifest-Version: `0.1.0-alpha.2`
- Element: `bluepencil.element.min.js`
- SHA-256: `bb159b42d441abed7721c38ef76ba0c575315843adcf952f0e18b6706f60accf`

`attach.js` lädt das Manifest und setzt bei verfügbarem `crypto.subtle` den
Integritätsvergleich. In einem sicheren Browser-Kontext wird deshalb `data-integrity="true"` gesetzt.
Auf einem unsicheren LAN-Origin ohne WebCrypto lässt der Loader den Integritätsvergleich bewusst
aus und warnt einmal sichtbar; ein fehlgeschlagener Integritätscheck darf nicht den gesamten Layer
stillschweigend verhindern.

Der Produktions-Build muss Bluepencil ausdrücklich mit
`--build-arg VITE_BLUEPENCIL_ENABLED=1` bauen. `BLUEPENCIL_ENABLED` im laufenden Container
reaktiviert einen bereits gebauten Production-Bundle nicht. Ein Upgrade von Browser-Assets,
Manifest und Hash muss gemeinsam erfolgen.

## 6. HTTP-Vertrag des Sidecars

Der Sidecar läuft mit `--base /bluepencil/api` und stellt folgende relative Endpunkte bereit:

| Methode | Pfad | Verwendung |
|---|---|---|
| GET | `/bluepencil/api/health` | `{ ok, status, version }` |
| GET | `/bluepencil/api/notes` | Notizen mit Route-, Intent-, Typ-, Session-, Source-, Environment-, Status- und Zeitfiltern |
| POST | `/bluepencil/api/notes` | Notiz anlegen |
| PATCH | `/bluepencil/api/notes/{id}` | Notizfelder ändern |
| POST | `/bluepencil/api/notes/{id}/messages` | Antwort/Review-Nachricht anhängen |
| POST | `/bluepencil/api/notes/bulk-delete` | Löschen mit `{ ids?, filter?, confirm: true }` |
| GET | `/bluepencil/api/sessions` | Sessions |
| GET | `/bluepencil/api/bundle` | kanonischer Export |
| GET | `/bluepencil/api/journal` | optionale Historie |

Der Sidecar schreibt in `/data/notes.json` im Compose-Volume `bluepencil_data`. Die
Compose-Umgebung setzt Store, Port, Base-Path und Environment; der Sidecar veröffentlicht keinen
Host-Port. `make bluepencil` startet nur den optionalen Sidecar. `make bluepencil-down` stoppt nur
diesen Sidecar und lässt die übrigen Dienste laufen.

## 7. Verifikation

Die fokussierten Regressionstests prüfen Bridge-Header, Identity-Mapping, Gate, Routepfade,
In-flight-Install-Invalidierung, doppelte Probe-Vermeidung sowie Logout→Login:

```text
cd frontend
npx vitest run src/api/client.test.ts src/test/bluepencil-loader.test.ts src/test/bluepencil-loader-timeout.test.ts src/test/bluepencil-host.test.ts src/test/AuthContext.bluepencil.test.tsx src/test/AuthContext.login-timeout.test.tsx
npm run lint
npx tsc --noEmit -p tsconfig.json
```

Der optionale Playwright-Spec `e2e/tests/bluepencil.spec.ts` prüft den realen Sidecar-Roundtrip nur,
wenn Sidecar und Frontend-Build explizit aktiviert sind. Ohne Sidecar wird jeder Test sichtbar mit
einer konkreten Begründung übersprungen; ein fehlender Browser darf den CI-Lauf nicht stillschweigend
als Erfolg behandeln.

## 8. Nicht-Ziele und Ausbau

Der Sidecar ist kein Produktionspfad. Ein späterer DRF-Service benötigt
Tenant-FK, RLS, Authentifizierung, Rollenprüfung, CSRF- und Fehlerverträgen. Der Frontend-Host-
Vertrag kann dafür weiterverwendet werden, aber Identity, Route-Metadaten und das UI-Gate dürfen
nicht als Ersatz für diese Server-Regeln behandelt werden.
