# Station Pilot Web

Application locale moderne de gestion de station-service, entièrement séparée de la version Streamlit. Elle utilise uniquement USD et LL/LBP.

## Points forts

- saisie complète du stock, des ventes, dépenses, crédits clients et caisses ;
- autant de clients à crédit et de remboursements que nécessaire par journée ;
- registre clients consolidé avec solde restant USD/LL, comptes soldés et historique des mouvements ;
- ajout d’un nouveau crédit ou encaissement directement depuis le compte d’un client existant ;
- consultation et modification d’une journée existante ;
- suppression sécurisée d’une ou plusieurs journées avec sauvegarde SQLite automatique préalable ;
- tableaux de bord par jour, semaine, mois et année ;
- histogrammes, courbes financières, courbes de stock, répartition des dépenses et barre rouge/verte du résultat ;
- vues historique synthétique, complète et ligne par ligne ;
- exports CSV et classeur Excel multi-feuilles ;
- sauvegarde double SQLite + CSV après chaque enregistrement.

Les graphiques en équivalent USD convertissent les montants LL avec le taux historique saisi pour chaque journée. Les montants d’origine USD et LL restent également visibles séparément.

## Technologies

- React + TypeScript + Vite pour l’interface ;
- Express pour l’API locale ;
- SQLite (`better-sqlite3`) pour la base ;
- Recharts pour les graphiques ;
- export Excel natif sans bibliothèque tableur vulnérable.

Prérequis : Node.js 18 ou plus récent et npm.

L’installation et le démarrage vérifient automatiquement que le module SQLite correspond à la version de Node.js active. Si vous changez de version de Node dans le même dossier, il sera reconstruit automatiquement.

## Démarrage recommandé

```bash
npm install
npm run build
npm start
```

Ouvrir ensuite <http://localhost:4174>.

Pour travailler en mode développement avec rechargement automatique :

```bash
npm run dev
```

Puis ouvrir <http://localhost:5173>.

## Données locales

La base et les sauvegardes automatiques se trouvent dans `server/data/` :

- `station.db` : base principale SQLite ;
- `station_data.csv` : rapport quotidien complet, avec chaque type de vente et dépense ;
- `station_credits.csv` : crédits vendus, client par client ;
- `station_credit_payments.csv` : crédits encaissés, client par client.

Les sauvegardes créées avant une suppression sont conservées dans `server/data/backups/`.

La nouvelle base est volontairement vide. Les fichiers CSV contiennent déjà les bons en-têtes. Le serveur écoute uniquement la machine locale par défaut. Pour un accès volontaire depuis le réseau local, démarrer avec `HOST=0.0.0.0 npm start` et protéger le réseau de la station.
