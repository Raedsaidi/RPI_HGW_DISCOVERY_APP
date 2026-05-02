# Discovery
POST   /api/v1/discovery/run              → Lancer discovery (WRITE)
GET    /api/v1/discovery/runs             → Liste runs (READ)
GET    /api/v1/discovery/runs/{id}        → Détail run (READ)
DELETE /api/v1/discovery/runs/{id}        → Supprimer run (WRITE)
GET    /api/v1/discovery/runs/{id}/errors → Erreurs run (READ)
GET    /api/v1/discovery/status           → Status courant

# Switches CRUD
GET    /api/v1/switches                   → Liste (READ)
POST   /api/v1/switches                   → Créer (WRITE)
GET    /api/v1/switches/{id}              → Détail (READ)
PUT    /api/v1/switches/{id}              → Modifier (WRITE)
DELETE /api/v1/switches/{id}              → Supprimer (WRITE)
GET    /api/v1/switches/{id}/rpis         → RPis de ce switch (READ)

# RPis
GET    /api/v1/rpis                       → Tous RPis (succès + échecs) (READ)
GET    /api/v1/rpis/{ip}                  → Détail RPi (READ)
GET    /api/v1/rpis/{ip}/facts            → Historique métriques (READ)
POST   /api/v1/rpis/credentials           → Soumettre credentials custom (WRITE)
DELETE /api/v1/rpis/{ip}/credentials      → Supprimer credentials custom (WRITE)

# HGWs
GET    /api/v1/hgws                       → Liste HGWs (READ)
GET    /api/v1/hgws/{ip}                  → Détail HGW (READ)
GET    /api/v1/hgws/{ip}/history          → Historique (READ)

# Topology
GET    /api/v1/topology                   → Topologie dernier run (READ)
GET    /api/v1/topology/{run_id}          → Topologie run spécifique (READ)

# Sync
GET    /api/v1/sync/status                → Config + statut scheduler (READ)
POST   /api/v1/sync/trigger               → Déclencher sync maintenant (WRITE)

# Health
GET    /health                            → Health check