# Station Pilot

Application de gestion quotidienne pour station-service, centrée sur une interface Streamlit claire et rapide.

## Fonctionnalités

- clôture journalière avec continuité du stock et des caisses ;
- suivi séparé des montants USD et LL ;
- ventes, dépenses, crédits clients et remboursements ;
- tableau de bord avec indicateurs et graphiques ;
- historique, exports Excel et sauvegardes CSV sur GitHub ;
- thèmes clair et sombre.

## Lancer l’application Streamlit

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

L’application est ensuite disponible sur `http://localhost:8501`.

## Stockage permanent sur GitHub

Le code (ce dépôt) peut être public. Les données sont enregistrées à part, dans
la branche `data` du dépôt **privé** `station-pilot-data` :

- `data/station_data.csv` ;
- `data/station_credits.csv` ;
- `data/station_credit_payments.csv`.

Les trois fichiers sont mis à jour ensemble dans un commit GitHub. La base SQLite
utilisée par l’application n’est qu’un cache temporaire reconstruit depuis ces CSV.
L’application refuse de fonctionner si le dépôt de données est public, car les
fichiers contiennent des données métier.

Le dépôt de données doit avoir une branche `main` (créez-le avec un README) : la
branche `data` est créée automatiquement au premier lancement.

Dans Streamlit Community Cloud, ouvrez **App settings > Secrets** et ajoutez :

```toml
[app_access]
password = "MOT_DE_PASSE_DE_L_APP"

[github_storage]
token = "NOUVEAU_TOKEN_GITHUB"
owner = "narvall018"
repo = "station-pilot-data"
branch = "data"
```

Utilisez un fine-grained personal access token limité au dépôt
`station-pilot-data`, avec la permission **Contents: Read and write**. Ne placez
jamais le vrai token dans un fichier suivi par Git.

Pour un lancement local, les mêmes valeurs peuvent être placées dans
`.streamlit/secrets.toml`, qui est ignoré par Git.

## Version web

Une version React/Vite complémentaire est disponible dans `station_pilot_web/`.
