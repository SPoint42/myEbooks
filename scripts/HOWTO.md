# HOWTO — indexer, publier et redéployer manuellement

Ce guide décompose les quatre opérations réalisées par `./scripts/index_publish_deploy` afin de
pouvoir les lancer et les contrôler séparément :

1. indexer les EPUB et PDF du Drive public dans `./data` ;
2. pousser le commit de `main` utilisé par le catalogue ;
3. publier SQLite et les couvertures dans une GitHub Release ;
4. déclencher le workflow de déploiement Scaleway avec le tag de cette Release.

Toutes les commandes sont à lancer depuis le même terminal. Ne lancez pas
`./scripts/index_publish_deploy` en parallèle de cette procédure.

## 1. Se placer dans le dépôt

```bash
cd /Users/s.gioria/perso/github.com/SPoint42/myEbooks
```

Définir les valeurs utilisées dans la suite :

```bash
MYEBOOKS_DRIVE_URL='https://drive.google.com/drive/folders/1WeqHFZQ0zl0Oy5u6JiabChlIGx3D5sie?usp=sharing'
MYEBOOKS_REPOSITORY='SPoint42/myEbooks'
```

Ces variables ne sont valables que dans le terminal courant. Les apostrophes évitent que le
shell interprète le `?` de l'URL.

## 2. Vérifier les prérequis

Vérifier que les commandes nécessaires sont présentes :

```bash
command -v git
command -v gh
command -v sqlite3
command -v python3
```

Vérifier l'authentification GitHub :

```bash
gh api user --jq .login
```

Si cette commande échoue :

```bash
gh auth login
```

Vérifier que l'on travaille bien depuis la racine attendue, sur `main`, avec le dépôt SSH
attendu :

```bash
git rev-parse --show-toplevel
git branch --show-current
git remote get-url origin
git status --short --branch
```

Les résultats attendus sont respectivement :

```text
/Users/s.gioria/perso/github.com/SPoint42/myEbooks
main
git@github.com:SPoint42/myEbooks.git
## main...origin/main
```

Le dernier résultat peut signaler que la branche est en avance ou en retard. Il ne doit pas
lister de fichier modifié ou non suivi au moment de la publication. Commiter volontairement les
changements à conserver avant de continuer ; ne pas utiliser `git add .` sans vérifier leur
contenu.

## 3. Vérifier qu'aucune indexation n'écrit dans le catalogue

Arrêter auparavant `./start_dev` ou toute autre indexation avec `Ctrl+C`.

Afficher les dernières exécutions connues :

```bash
sqlite3 -header -column ./data/myebooks.sqlite3 \
  "SELECT id, status, started_at, completed_at, discovered, indexed, unchanged, failed, removed, error FROM sync_runs ORDER BY id DESC LIMIT 5;"
```

Si le dernier statut est `running`, chercher d'abord un processus réellement actif :

```bash
pgrep -fl 'start_dev|index_catalog|myebooks.catalog_cli|uvicorn'
lsof ./data/myebooks.sqlite3
```

- Si un processus est actif, l'arrêter proprement et attendre qu'il rende la main.
- Si aucun processus n'écrit dans le catalogue, le statut peut provenir d'une exécution
  interrompue. Il ne faut pas corriger directement `sync_runs` avec une requête SQL.
- Ne jamais indexer et publier en parallèle : la base et les couvertures doivent représenter le
  même instantané.

Si `./data/myebooks.sqlite3` n'existe pas encore, la commande SQLite échoue normalement ;
l'indexation suivante créera la base.

## 4. Indexer les EPUB et PDF du Drive public

Lancer l'indexation incrémentale :

```bash
./scripts/index_catalog \
  --drive-url "$MYEBOOKS_DRIVE_URL" \
  --data ./data \
  --extensions epub,pdf
```

Une indexation incrémentale ne reparcourt pas les livres inchangés. Pour forcer exceptionnellement
la réanalyse de tous les fichiers, ajouter `--force` à la commande précédente.

La commande doit se terminer par un résumé du type :

```text
Indexation terminée : N indexé(s), N inchangé(s), N en erreur, N supprimé(s), sur N livre(s).
```

Contrôler ensuite l'intégrité de SQLite :

```bash
sqlite3 ./data/myebooks.sqlite3 'PRAGMA quick_check;'
```

Le résultat attendu est `ok`. Vérifier le dernier traitement :

```bash
sqlite3 -header -column ./data/myebooks.sqlite3 \
  "SELECT id, status, started_at, completed_at, discovered, indexed, unchanged, failed, removed, error FROM sync_runs ORDER BY id DESC LIMIT 1;"
```

Le statut attendu est `completed`. Contrôler enfin les livres disponibles par format et les
éventuelles erreurs de métadonnées :

```bash
sqlite3 -header -column ./data/myebooks.sqlite3 \
  "SELECT file_format, COUNT(*) AS available_books FROM books WHERE available = 1 GROUP BY file_format ORDER BY file_format;"

sqlite3 -header -column ./data/myebooks.sqlite3 \
  "SELECT file_format, COUNT(*) AS parse_errors FROM books WHERE available = 1 AND parse_error IS NOT NULL GROUP BY file_format ORDER BY file_format;"
```

Les erreurs de métadonnées n'empêchent pas nécessairement la publication, mais elles doivent être
comprises avant de continuer.

## 5. Pousser le code qui sera associé au catalogue

Les données de `./data` sont ignorées par Git. Après l'indexation, vérifier que le dépôt est
toujours propre et que le commit voulu est bien sur `main` :

```bash
git status --short --branch
git log -1 --oneline
git branch --show-current
git remote get-url origin
```

S'il reste des changements de code ou de documentation voulus, les relire, les commiter, puis
revenir à cette étape. La publication refusera un worktree sale.

Pousser le commit courant par SSH :

```bash
git push origin main
```

Contrôler que le commit local et celui de GitHub sont identiques :

```bash
git fetch origin main
git rev-parse HEAD
git rev-parse origin/main
```

Les deux SHA doivent être identiques. Cette étape est importante : la Release créée ensuite sera
rattachée au commit courant, et le workflow Scaleway vérifiera que ce commit appartient à
`origin/main`.

## 6. Publier l'index et les couvertures

Publier l'état déjà indexé de `./data`, sans relire le Drive :

```bash
./scripts/publish_catalog --skip-index --data ./data
```

Cette commande :

- exporte une copie cohérente de `data/myebooks.sqlite3` ;
- copie uniquement les couvertures référencées ;
- génère une archive et son checksum SHA-256 dans `./dist` ;
- prépare le contenu dans `./deploy/catalog` ;
- crée une GitHub Release préliminaire `catalog-YYYYMMDDTHHMMSSZ` rattachée à `HEAD`.

Elle ne publie aucun EPUB ni PDF source. À la fin, relever le tag affiché ici :

```text
Catalogue publié dans la GitHub Release catalog-YYYYMMDDTHHMMSSZ
```

Le conserver dans une variable en remplaçant la valeur par le tag réellement affiché :

```bash
MYEBOOKS_CATALOG_TAG='catalog-YYYYMMDDTHHMMSSZ'
```

Vérifier la Release avant tout déploiement :

```bash
gh release view "$MYEBOOKS_CATALOG_TAG" \
  --repo "$MYEBOOKS_REPOSITORY" \
  --json tagName,targetCommitish,isPrerelease,url
```

`tagName` doit être le tag choisi, `targetCommitish` doit correspondre au SHA de `HEAD` et
`isPrerelease` doit valoir `true`.

### Cas exceptionnel : un ancien statut reste `running`

Sans `--force-publish`, la publication demande l'arrêt propre de l'indexation et attend au maximum
300 secondes. N'utiliser la commande suivante qu'après avoir vérifié avec `pgrep` et `lsof`
qu'aucun processus ne modifie SQLite ou les couvertures :

```bash
./scripts/publish_catalog --skip-index --force-publish --data ./data
```

`--force-publish` ignore seulement le statut `running` ; il ne désactive pas les contrôles
d'intégrité. Il ne doit jamais servir à prendre un instantané pendant une vraie indexation.

## 7. Déployer cette Release sur Scaleway

La commande suivante vérifie l'existence de la Release, déclenche le workflow GitHub Actions et
attend son résultat :

```bash
MYEBOOKS_GITHUB_REPOSITORY="$MYEBOOKS_REPOSITORY" \
  ./scripts/deploy_scaleway \
  --tag "$MYEBOOKS_CATALOG_TAG" \
  --watch
```

Le déploiement s'effectue dans GitHub Actions, pas directement depuis le Mac. Le workflow :

1. vérifie la Release et son commit source ;
2. télécharge et contrôle l'archive du catalogue ;
3. lance le lint et les tests ;
4. construit et analyse l'image ;
5. pousse l'image dans le registre Scaleway ;
6. applique Terraform ;
7. appelle le point de santé public `/health`.

### Variante : piloter GitHub Actions sans `deploy_scaleway`

Pour exécuter explicitement les mêmes commandes GitHub que le script :

```bash
gh workflow run deploy-scaleway.yml \
  --repo "$MYEBOOKS_REPOSITORY" \
  --ref main \
  --field "catalog_tag=$MYEBOOKS_CATALOG_TAG"
```

Lister les exécutions afin de choisir celle qui vient d'être créée :

```bash
gh run list \
  --repo "$MYEBOOKS_REPOSITORY" \
  --workflow deploy-scaleway.yml \
  --event workflow_dispatch \
  --limit 5
```

Copier son identifiant numérique dans une variable, puis la suivre :

```bash
MYEBOOKS_RUN_ID='IDENTIFIANT_NUMERIQUE'

gh run watch "$MYEBOOKS_RUN_ID" \
  --repo "$MYEBOOKS_REPOSITORY" \
  --exit-status
```

Afficher le résultat détaillé :

```bash
gh run view "$MYEBOOKS_RUN_ID" \
  --repo "$MYEBOOKS_REPOSITORY" \
  --json status,conclusion,url,headSha
```

En cas d'échec, afficher uniquement les logs des étapes en erreur :

```bash
gh run view "$MYEBOOKS_RUN_ID" \
  --repo "$MYEBOOKS_REPOSITORY" \
  --log-failed
```

Le résultat attendu est `status: completed` et `conclusion: success`. Le résumé de l'exécution
GitHub contient l'URL Scaleway déployée ; le workflow a déjà validé son endpoint `/health`.

## 8. Reprendre proprement après un échec

- **Échec d'indexation :** ne rien publier. Corriger la cause puis relancer uniquement l'étape 4.
- **Indexation réussie, publication non commencée :** reprendre à l'étape 5.
- **Release créée mais tag perdu :** la retrouver avec
  `gh release list --repo "$MYEBOOKS_REPOSITORY" --limit 10` ; ne pas republier inutilement.
- **Release créée, déploiement échoué :** diagnostiquer les logs puis redéployer le même tag. Il
  n'est pas nécessaire de réindexer ni de créer une nouvelle Release si son contenu est correct.
- **Nouveau commit après la Release :** ne pas supposer que la Release contient ce nouveau code.
  Réindexer si nécessaire, puis créer une nouvelle Release liée au nouveau commit.

## Résumé minimal

Une fois les prérequis et l'absence d'indexation active vérifiés, le chemin nominal tient dans les
commandes suivantes :

```bash
cd /Users/s.gioria/perso/github.com/SPoint42/myEbooks

MYEBOOKS_DRIVE_URL='https://drive.google.com/drive/folders/1WeqHFZQ0zl0Oy5u6JiabChlIGx3D5sie?usp=sharing'
MYEBOOKS_REPOSITORY='SPoint42/myEbooks'

./scripts/index_catalog \
  --drive-url "$MYEBOOKS_DRIVE_URL" \
  --data ./data \
  --extensions epub,pdf

git status --short --branch
git push origin main

./scripts/publish_catalog --skip-index --data ./data

MYEBOOKS_CATALOG_TAG='catalog-YYYYMMDDTHHMMSSZ'

MYEBOOKS_GITHUB_REPOSITORY="$MYEBOOKS_REPOSITORY" \
  ./scripts/deploy_scaleway --tag "$MYEBOOKS_CATALOG_TAG" --watch
```
