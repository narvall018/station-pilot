# Station Pilot

Application de gestion quotidienne pour station-service, centrée sur une interface Streamlit claire et rapide.

## Fonctionnalités

- clôture journalière avec continuité du stock et des caisses ;
- suivi séparé des montants USD et LL ;
- ventes, dépenses, crédits clients et remboursements ;
- tableau de bord avec indicateurs et graphiques ;
- historique, exports Excel et sauvegardes CSV locales ;
- thèmes clair et sombre.

## Lancer l’application Streamlit

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

L’application est ensuite disponible sur `http://localhost:8501`.

## Données

Les bases SQLite, fichiers CSV, sauvegardes et secrets ne sont pas versionnés. Ils restent locaux et sont créés automatiquement lorsque l’application démarre.

Pour un déploiement permanent dans le cloud, utilisez une base de données externe durable : le stockage local d’un hébergement Streamlit peut être réinitialisé.

## Version web

Une version React/Vite complémentaire est disponible dans `station_pilot_web/`.
