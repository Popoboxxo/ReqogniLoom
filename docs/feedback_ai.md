 🔴 Kritisch (muss sofort gefixt werden)                                                                                                 
                                                                                                                                            
      #    Bug                       Surface    Details                                                                           Fix       
      ───  ────────────────────────  ─────────  ────────────────────────────────────────────────────────────────────────────────  ───       
      1    ADR CRUD nicht            MCP +      'AdrService' object has no attribute 'create' — alle 4 Tools                                
           implementiert             REST       (create/read/update/delete) registriert aber Backend stub                                   
      2    Risk CRUD nicht           MCP +      Gleiches Problem wie ADR — RiskService fehlen die Methoden                                  
           implementiert             REST                                                                                                   
      3    Issue CRUD unvollständig  MCP +      Nur issue.create funktioniert (mit severity), read/update/delete sind stub                  
                                     REST                                                                                                   
      4    Delete-Operationen tot    REST       DELETE /api/v1/requirements/{id} → leere Response. Kein Löschen möglich                     
      5    Issue Status-Change       REST + UI  PATCH /api/v1/issues/{id} mit status → wird ignoriert. Braucht transitions/                 
           kaputt                               Endpoint                                                                                    
                                                                                                                                            
    🟠 Hoch (nächste Priorität)                                                                                                             
                                                                                                                                            
      #    Bug                     Surface  Details                                                                               Fix       
      ───  ──────────────────────  ───────  ────────────────────────────────────────────────────────────────────────────────────  ───       
      6    Kein REST Trace-Links   REST     POST /api/v1/trace-links/ → 404. Links nur via MCP möglich                                      
           Endpoint                                                                                                                         
      7    ReqIF Reimport bricht   Backend  Test test_reimport_same_document_is_idempotent failed — importiert gleiches Dokument            
                                            mit neuen IDs statt existierende zu matchen                                                     
      8    Diagram API Feldname    REST     Erwartet name statt title (inkonsistent zu allen anderen Entities)                              
           falsch                                                                                                                           
      9    Needs API inkonsistent  REST     Create/List unter /workspaces/{id}/needs/ aber Detail/Update/Delete unter                       
                                            /api/v1/needs/{id}/                                                                             
      10   Frontend-Tests zu       CI       Vitest braucht >300s für ~500 Tests — timeoutet in CI                                           
           langsam                                                                                                                          
                                                                                                                                            
    🟡 Mittel (sollte gefixt werden)                                                                                                        
                                                                                                                                            
      #    Bug                               Surface   Details                                                                              
      ───  ────────────────────────────────  ────────  ────────────────────────────────────────────────────────────                         
      11   DEBUG=True im Sandbox-Deployment  Security  Django Debug-Info (SECRET_KEY, DB-Passwort) im Error-Output                          
      12   Backend-Test schreibt in /app     Backend   .pytest_cache Permission denied weil als root vs app-user                            
      13   Keine Input-Validation bei Länge  API       Keine Maximallängen für title/description → potenzieller DoS                         
                                                                                                                                            
    🔵 Bereits in diesem Run gefixt                                                                                                         
                                                                                                                                            
      Bug                                     Fix                                                          Commit                           
      ──────────────────────────────────────  ───────────────────────────────────────────────────────────  ────────────────                 
      B2: Auth-State bei Navigation verloren  AUTH_COOKIE_SECURE=* → Python Pitfall bool("False") = True`  ✅ .env editiert                 
                                                                                                                                            
    ────────────────────────────────────                                                                                                    
                                                                                                                                            
    💡 Quick-Fix Vorschlag für die Top 3                                                                                                    
                                                                                                                                            
    ADR Service (in backend/application/services/adr_service.py):                                                                           
                                                                                                                                            
      ─ python                                                                                                                              
      # Aktuell: Fehlende Methoden → ergänzen:                                                                                              
      class AdrService:                                                                                                                     
          def create(self, data, actor): return self.artifact_service.create(data, actor)                                                   
          def get(self, id, actor): return self.artifact_service.get(id, actor)                                                             
          def update(self, id, data, actor): return self.artifact_service.update(id, data, actor)                                           
          def delete(self, id, actor): return self.artifact_service.delete(id, actor)                                                       
                                                                                                                                            
    Delete Endpoint (in backend/rest_api/views.py):                                                                                         
                                                                                                                                            
      ─ python                                                                                                                              
      # DELETE fehlt vermutlich im Viewset:                                                                                                 
      # `http_method_names` auf `['get', 'post', 'patch', 'delete']` setzen                                                                 
                                                                                                                                            
    Diagram Feldname (in backend/rest_api/serializers.py):                                                                                  
                                                                                                                                            
      ─ python                                                                                                                              
      # `name` → `title` im Serializer oder im Viewset mappen                                                                               
                                                                                                                                            
    Soll ich die Fixes direkt im Code auf der Sandbox durchführen und neu deployen?  