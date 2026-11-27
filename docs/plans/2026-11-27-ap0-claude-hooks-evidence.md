---
type: EVIDENCE
title: "AP0: Claude-Code-Plugin-Hooks (UserPromptSubmit) — Messergebnisse"
status: done
date: 2026-11-27
author_agent: main_chat
language: de
parent_plan: "docs/plans/2026-11-26-interview-und-listen-modus.md"
---

# AP0: Claude-Code-Plugin-Hooks (`UserPromptSubmit`) — Messergebnisse

Zweck: Gate G1/D9 des Interview-/Listen-Plans. Die Spec vom 2026-11-21 stützt sich
auf Doku-Aussagen; hier wurde der Hook in einem echten Claude Code ausgeführt.

## Umgebung

| Punkt | Wert |
|---|---|
| Claude Code | `2.1.332` |
| Node | `v22.22.1` |
| Plugin | Wegwerf-Plugin `ap0-probe@inline`, geladen über `--plugin-dir` |
| Rechner | Linux, Repo `/home/hermes/repos/ReqogniLoom` |
| Auth | OAuth-Session abgelaufen; Modellaufrufe scheitern, **Hooks feuern trotzdem** |

Der Hook wurde über `claude -p "<prompt>" --plugin-dir /tmp/opencode/ap0-plugin`
ausgelöst. Er schreibt seinen Input nach `/tmp/opencode/ap0-hook.log`; stdout bleibt leer.

## Ergebnisse

| # | Test | Ergebnis | Beleg |
|---|---|---|---|
| A | Hook feuert (synchron, `type: command`) | **ja**, auch ohne gültige Auth | Log-Eintrag mit Payload |
| B | Payload | `session_id`, `transcript_path`, `cwd`, `prompt_id`, `permission_mode`, `hook_event_name`, `prompt` | Log |
| C | Env im Hook | `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA`, `CLAUDE_PROJECT_DIR` gesetzt; `CLAUDE_HOOK_EVENT` nicht gesetzt | Log |
| D | `async: true` blockiert nicht | **ja** (Wand 2,54 s vs. Basis 3,59 s) | Zeitmessung |
| E | Async-Hook überlebt das Prozessende | **nein** — bei `claude -p` wird der Hintergrundprozess beendet; `sleep-done` fehlt nach 3 s **und** nach 0,3 s + 2 s Wartezeit | Log |
| F | Synchroner Hook blockiert | **ja**, +3 s Schlaf schlagen voll auf die Wandzeit (5,63 s vs. 3,59 s Basis) | Zeitmessung |
| G | `type: http` | **ja**, POST mit identischem Body, `Content-Type: application/json`, User-Agent `axios/1.15.2` | HTTP-Log |
| H | HTTP blockiert | **ja**, kein `async`-Feld für HTTP-Hooks; ein langsamer Endpunkt würde den Zug aufhalten | Doku + Messung (schneller Endpunkt ≈ +0,1 s) |
| I | Lokales Slash-Kommando `/status` | **kein Hook-Feuer** (Kommando wird lokal beantwortet) | kein Log-Eintrag |
| J | Exit-Code 2 | **blockiert** den Prompt, stderr wird gezeigt, Attribution „This hook comes from the ap0-probe@inline plugin." | CLI-Ausgabe |
| K | Exit-Code 1 | **nicht blockierend** (fail-open) | CLI-Ausgabe |

## Konsequenzen für P4/D9

1. **Der Hook-Weg ist real und deterministisch** — G1 ist für Claude Code belegt.
   Der Hook feuert vor dem Modellaufruf, unabhängig von der Modell-Auth.
2. **`async: true` ist kein Verlässlichkeitsgarant.** Der Hintergrundprozess wird
   beim Beenden von `claude -p` gekillt. In einer interaktiven Sitzung lebt er
   länger, aber ein „einmal abgeschickt, kommt sicher an" gibt es nicht. Der
   Relay muss Nachrichten lokal persistent vormerken und beim nächsten Lauf
   nachsenden; „verwerfen statt bündeln" (H3 der Spec) ist damit endgültig vom Tisch.
3. **HTTP-Hooks sind synchron.** Als direkter Weg zum ReqogniLoom-Server ist
   `type: http` nur geeignet, wenn `suggestion.capture` **sofort** antwortet
   (z. B. 202 + Celery-Auftrag) und den LLM-Aufruf nicht im Request ausführt.
   Der heutige P2-Stand ruft das Modell inline auf — das würde jeden Prompt um
   Sekunden verzögern.
4. **D9-Empfehlung:** R2 (HTTP-Hook) mit einer **asynchronen Capture-Quote** auf
   dem Server; bis die existiert, R1 (kleines Relay-Skript, `async: true` +
   persistente Warteschlange). Beide Wege brauchen dieselbe lokale Vormerkung.
5. **Filter:** Lokale Slash-Kommandos feuern nicht; expandierende Kommandos und
   `/loop` müssen trotzdem gefiltert werden, weil sie als Prompt ankommen können.
   (`/loop` und Hintergrund-Berichte konnten ohne gültige Auth nicht geprüft werden.)
6. **Fail-open:** Exit 0/1 sind unschädlich, Exit 2 blockiert. Der Relay muss
   **immer** mit 0 enden und Fehler nur in eine Logdatei schreiben.

## Offene Punkte

- `/loop`- und Hintergrund-Bericht-Filter: ungeprüft (Auth erforderlich).
- `type: http` mit `async` gibt es nicht; die Entkopplung muss serverseitig
  (202 + Queue) oder über ein lokales Relay erfolgen.
- Der Async-Abbruch beim Prozessende ist in einer interaktiven Sitzung nicht
  abschließend vermessen; die persistente Vormerkung bleibt Pflicht.
- Der Hook-Input für eingefügte Inhalte (`pasted_content`-Tags) wurde nicht
  geprüft.

## Rohbelege (gekürzt)

Payload:
```json
{"session_id":"c58585af-...","transcript_path":"/home/hermes/.claude/projects/-tmp-opencode-ap0-run/c58585af-....jsonl","cwd":"/tmp/opencode/ap0-run","prompt_id":"34356d88-...","permission_mode":"default","hook_event_name":"UserPromptSubmit","prompt":"Say the single word: probe"}
```

Zeiten:
```text
Basis (kein Hook)       3,59 s
Synchron + 3 s Schlaf   5,63 s
Async + 3 s Schlaf      2,98 s   (kein sleep-done)
Async + 0,3 s Schlaf    2,54 s   (kein sleep-done nach 2 s Wartezeit)
HTTP (schnell)          3,69 s
```
