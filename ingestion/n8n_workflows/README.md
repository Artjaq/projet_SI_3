# Ingestion n8n – workflows CSV/SQLite → MinIO

Workflows d'ingestion locale : lecture des fichiers Kaggle bruts et push vers
le bucket `raw-data` de MinIO (Bastion, IP Tailscale).

---

## Prérequis

| Prérequis | Vérification |
|---|---|
| Docker + Docker Compose v2 | `docker compose version` |
| Tailscale actif | MinIO joignable : `curl http://10.14.190.18:9000/minio/health/live` → 200 |
| Fichier `.env` à la racine | Contient `MINIO_*` et `N8N_BASIC_AUTH_*` |
| Datasets dans `data/` | `data/vgsales.csv` et `data/igdb.sqlite` (voir `data/README.md`) |

---

## Lancer n8n

```bash
# Depuis le dossier ingestion/n8n_workflows/
docker compose up -d
```

n8n est prêt quand les logs affichent `Editor is now accessible via: http://localhost:5678`.

```bash
# Suivre les logs
docker compose logs -f n8n

# Arrêter sans supprimer les données
docker compose down
```

---

## Accès à l'interface

**URL** : http://localhost:5678

Login/mot de passe : ceux définis dans `N8N_BASIC_AUTH_USER` / `N8N_BASIC_AUTH_PASSWORD` du `.env`.

---

## Créer et exporter un workflow

### Dans n8n

1. Créer le workflow (ex: lecture CSV → nœud HTTP PUT vers MinIO).
2. Tester manuellement via le bouton **Execute Workflow**.
3. Une fois validé : menu **⋮ → Download** (en haut à droite du workflow).

### Sauvegarder dans ce dossier

Nommer le fichier selon la convention :

```
wf_<source>_to_minio.json
```

Exemples :

| Source | Fichier |
|---|---|
| Video Game Sales (CSV) | `wf_vgsales_csv_to_minio.json` |
| IGDB Dataset (SQLite) | `wf_igdb_sqlite_to_minio.json` |

Déposer le JSON exporté ici (`ingestion/n8n_workflows/`) et le commiter.

### Ré-importer un workflow

Menu **Workflows → Import from file** → sélectionner le `.json`.

---

## Fichiers de données dans le container

Le dossier `data/` racine est monté en lecture seule dans n8n :

| Chemin local | Chemin dans le container |
|---|---|
| `data/vgsales.csv` | `/data/vgsales.csv` |
| `data/igdb.sqlite` | `/data/igdb.sqlite` |

Dans les nœuds n8n, utiliser le chemin `/data/<fichier>`.
