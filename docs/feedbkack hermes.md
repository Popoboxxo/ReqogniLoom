  🔴 Kritische Bugs                                                                                                                       
                                                                                                                                            
    1. MCP: API-Key trägt keine User-Rollen durch                                                                                           
                                                                                                                                            
    Schweregrad: 🔴 KRITISCH                                                                                                                
                                                                                                                                            
      workspace.get_context → active_roles: []                                                                                              
      user.list → "Permission denied: role 'admin' required, user has ()"                                                                   
      requirement.create → "Role '()' does not permit write operations"                                                                     
                                                                                                                                            
    Der API-Key authentifiziert den User korrekt, aber die admin-Rolle wird nicht in den MCP-Kontext propagiert. Lesen funktioniert,        
    Schreiben nicht. REST API mit Bearer Token hat das Problem nicht.                                                                       
                                                                                                                                            
    Fix: API-Key-Authentifizierung muss die User-Rollen aus der DB laden und in den MCP-Context einbetten.                                  
                                                                                                                                            
    2. REST: /api/v1/needs/derive-requirements/ → HTTP 500                                                                                  
                                                                                                                                            
    Schweregrad: 🔴 KRITISCH                                                                                                                
                                                                                                                                            
      GET /api/v1/needs/derive-requirements/ → 500                                                                                          
      "['"derive-requirements" is not a valid UUID.']"                                                                                      
      POST → 405 Method Not Allowed                                                                                                         
                                                                                                                                            
    Die URL-Routing-Reihenfolge matcht derive-requirements als pk (UUID), bevor der benannte Endpoint greift. Django URL-Konfiguration      
    muss die benannte Route VOR den generischen <uuid:pk>-Pattern definieren.                                                               
                                                                                                                                            
    3. REST: Needs können nicht erstellt werden                                                                                             
                                                                                                                                            
    Schweregrad: 🔴 KRITISCH                                                                                                                
                                                                                                                                            
      ─ json                                                                                                                                
      {"workspace_id": "..."} → "Workspace None not found"                                                                                  
      {"workspace": "..."}    → "workspace_id is required"                                                                                  
                                                                                                                                            
    Der Serializer akzeptiert keinen der beiden Feldnamen korrekt für die Workspace-Zuordnung.                                              
                                                                                                                                            
    ────────────────────────────────────                                                                                                    
                                                                                                                                            
    🟠 Hohe Bugs                                                                                                                            
                                                                                                                                            
    4. MCP: 7 doppelte Tools in tools/list                                                                                                  
                                                                                                                                            
    Schweregrad: 🟠 HOCH                                                                                                                    
                                                                                                                                            
    Folgende Tools erscheinen je zweimal im Array:                                                                                          
                                                                                                                                            
    • traceability.query                                                                                                                    
    • artifact.search                                                                                                                       
    • artifact.get_tree                                                                                                                     
    • workspace.get_context                                                                                                                 
    • audit.query                                                                                                                           
    • events.dlq_list                                                                                                                       
    • events.dlq_replay                                                                                                                     
                                                                                                                                            
    5. MCP: Viele Tools haben generische kwargs-Schemas                                                                                     
                                                                                                                                            
    Schweregrad: 🟠 HOCH                                                                                                                    
                                                                                                                                            
    Nur requirement.*, prompt_template.get und ai_derivation.* haben saubere typed inputSchemas. Alle anderen (needs, architecture, test,   
    traceability, artifact, workspace, permissions, admin, audit, events, user, adr, risk, issue, glossary) nutzen {"kwargs": {"type":      
    "object"}} — für LLMs nicht sinnvoll nutzbar.                                                                                           
                                                                                                                                            
    6. UI: Failed to load attribute configs (2x Console Error)                                                                              
                                                                                                                                            
    Schweregrad: 🟠 HOCH                                                                                                                    
                                                                                                                                            
    Der /api/v1/attribute-visibility-configs/ Endpoint returned [] (leeres Array), was im Frontend einen Error auslöst. Entweder fehlen     
    Default-Configs oder das Frontend behandelt leere Arrays nicht.                                                                         
                                                                                                                                            
    7. SSE-Transport nicht funktional                                                                                                       
                                                                                                                                            
    Schweregrad: 🟠 HOCH                                                                                                                    
                                                                                                                                            
    /api/v1/mcp/ mit Accept: text/event-stream returned JSON statt SSE-Events. Der SSE-Transport ist deklariert ("transports": ["http",     
    "sse", "stdio"]), aber nicht implementiert.                                                                                             
                                                                                                                                            
    ────────────────────────────────────                                                                                                    
                                                                                                                                            
    🟡 Mittlere Issues                                                                                                                      
                                                                                                                                            
      ─ json                                                                                                                                
      {"provider": "ollama", "base_url": "", "model_name": "", "api_key_is_set": false}                                                     
      ─ json                                                                                                                                
      {"provider": "ollama", "base_url": "", "model_name": "", "api_key_is_set": false}                                                     
                                                                                                                                            
    Alle AI-Features (Derive, Decompose, Validate, Suggest) können nicht funktionieren. Ollama-Base-URL fehlt.                              
                                                                                                                                            
    9. Workspace Language-Inkonsistenz                                                                                                      
                                                                                                                                            
    „Krasser Workspace" zeigt UI: "DE", aber API: "language": "en".                                                                         
                                                                                                                                            
    10. GET /api/v1/api-keys/{id}/ → 405 Method Not Allowed                                                                                 
                                                                                                                                            
    API-Key-Detail kann nicht via GET abgerufen werden. Nur POST (create) und GET (list) funktionieren.                                     
                                                                                                                                            
    11. change_reason-Pflicht bei Extended Preset                                                                                           
                                                                                                                                            
    Gut dokumentiert aber die Fehlermeldung könnte hilfreicher sein: Statt "change_reason required" könnte stehen: "Workspace 'Krasser      
    Workspace' (extended preset) requires change_reason for all modifications".                                                             
                                                                                                                                            
    ────────────────────────────────────                                                                                                    
                                                                                                                                            
    📊 Zusammenfassung                                                                                                                      
                                                                                                                                            
                           Anzahl                                                                                                           
      ───────────────────  ─────────────────────                                                                                            
      🔴 Kritisch          3                                                                                                                
      🟠 Hoch              4                                                                                                                
      🟡 Mittel            4                                                                                                                
      MCP-Tools            39 (32 unique)                                                                                                   
      Getestete Endpunkte  20+                                                                                                              
      Test-Modi            MCP, REST, Browser UI                                                                                            
                                                                                                                                            
    Fazit: ReqFlow ist ein beeindruckend umfangreicher POC mit nativer MCP-Integration. Die kritischen Bugs (Rollen-Propagation,            
    Need-Routing, Need-Creation) sollten vor einem produktiven Einsatz behoben werden. Die MCP-Tool-Duplikate und generischen Schemas       
    erschweren LLM-Nutzung erheblich.                              