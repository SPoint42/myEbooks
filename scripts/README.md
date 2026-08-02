# Scripts du projet

Les scripts opérationnels de `myEbooks` sont regroupés dans ce répertoire. Toutes les commandes
ci-dessous sont à lancer depuis la racine du dépôt :

```bash
cd /Users/s.gioria/perso/github.com/SPoint42/myEbooks
```

Pour afficher les options réellement disponibles sans exécuter une opération :

```bash
./scripts/NOM_DU_SCRIPT --help
```

La seule exception est `index_publish_deploy`, volontairement figé et sans aucun argument.

## Prérequis communs

- Python 3 est requis pour `start_dev` et les scripts de catalogue.
- L’environnement `.venv` et les dépendances Python sont créés automatiquement si nécessaire.
- L’accès à un Drive public nécessite une connexion réseau et un dossier partagé avec
  « Tous les utilisateurs disposant du lien ».
- Les commandes qui utilisent GitHub nécessitent la CLI `gh` installée et authentifiée :

  ```bash
  gh auth login
  gh auth status
  ```

- Les exemples utilisent EPUB par défaut. Ajouter `--extensions epub,pdf` pour traiter aussi les
  PDF, ou `--extensions pdf` pour ne traiter que les PDF.

Les options `--drive-url`, `--library` et `--fake` désignent trois sources différentes et ne
peuvent pas être combinées dans une même commande.

## `start_dev` : lancer l’application locale

Ce script prépare Python, démarre immédiatement le serveur Web, puis lance l’indexation en tâche
de fond. L’arrêt se fait avec `Ctrl+C`.

Le raccourci placé à la racine est la manière la plus simple de le lancer :

```bash
./start_dev
```

Sans option, il écoute sur <http://127.0.0.1:8000>, utilise `./data` et indexe le dossier local
`/Users/s.gioria/goinfre/cambook`. Pour rendre la commande portable, indiquer explicitement le
dossier :

```bash
./start_dev --library /chemin/vers/mes/ebooks
```

Pour indexer le Drive public :

```bash
./start_dev \
  --drive-url 'https://drive.google.com/drive/folders/IDENTIFIANT_DU_DOSSIER' \
  --extensions epub
```

Pour rendre le site accessible depuis une Kobo connectée au même Wi-Fi :

```bash
./start_dev --kobo --library /chemin/vers/mes/ebooks
```

ou avec le Drive :

```bash
./start_dev \
  --kobo \
  --drive-url 'https://drive.google.com/drive/folders/IDENTIFIANT_DU_DOSSIER'
```

Le script affiche l’adresse exacte à ouvrir sur la Kobo, sous la forme
`http://ADRESSE_IP_DU_MAC:8000/kobo`. Si macOS le demande, autoriser Python à accepter les
connexions entrantes.

Options courantes :

- `--host ADRESSE` et `--port PORT` changent l’adresse et le port d’écoute ;
- `--kobo` équivaut à écouter sur toutes les interfaces réseau avec `0.0.0.0` ;
- `--data DOSSIER` choisit l’emplacement de SQLite et des couvertures ;
- `--extensions epub,pdf` choisit les formats à indexer ;
- `--force-index` réanalyse tous les ebooks au démarrage ;
- `--no-reload` désactive le redémarrage automatique après une modification du code.

Le fichier `scripts/start_dev` contient l’implémentation ; le fichier `./start_dev` à la racine
ne fait que lui transmettre les arguments.

## `index_catalog` : mettre à jour uniquement le cache local

Ce script met à jour la base `data/myebooks.sqlite3` et les couvertures dans `data/covers/`. Il ne
démarre pas le serveur Web, ne construit pas d’archive et ne contacte pas GitHub.

Indexer un dossier local :

```bash
./scripts/index_catalog \
  --library /chemin/vers/mes/ebooks \
  --data ./data \
  --extensions epub
```

Indexer le Drive public :

```bash
./scripts/index_catalog \
  --drive-url 'https://drive.google.com/drive/folders/IDENTIFIANT_DU_DOSSIER' \
  --data ./data \
  --extensions epub
```

Créer rapidement un catalogue avec les données de démonstration :

```bash
./scripts/index_catalog --fake --data ./data
```

L’indexation est incrémentale. Les livres inchangés ne sont pas reparsés. Pour tout réanalyser :

```bash
./scripts/index_catalog \
  --drive-url 'https://drive.google.com/drive/folders/IDENTIFIANT_DU_DOSSIER' \
  --force
```

## `build_catalog` : préparer localement un artefact de déploiement

Ce script indexe la source, puis produit :

- `dist/myebooks-catalog-DATE.tar.gz` ;
- le fichier SHA-256 correspondant ;
- `deploy/catalog/`, utilisé ensuite par la construction de l’image Scaleway.

Il ne publie rien sur GitHub et ne déploie rien sur Scaleway.

Indexer le Drive puis construire le catalogue :

```bash
./scripts/build_catalog \
  --drive-url 'https://drive.google.com/drive/folders/IDENTIFIANT_DU_DOSSIER' \
  --data ./data \
  --extensions epub
```

Construire à partir d’un dossier local :

```bash
./scripts/build_catalog \
  --library /chemin/vers/mes/ebooks \
  --data ./data
```

Si `./data` vient déjà d’être indexé, construire exactement son état actuel sans recontacter la
source :

```bash
./scripts/build_catalog --skip-index --data ./data
```

Avec `--skip-index`, le script demande l’arrêt propre d’une éventuelle indexation active avant de
copier SQLite. Les options de source, `--extensions` et `--force` ne doivent alors pas être
ajoutées. `--output DOSSIER` permet de remplacer le répertoire `./dist`.

## `publish_catalog` : publier SQLite et les couvertures sur GitHub

Ce script réalise le même travail que `build_catalog`, puis crée une GitHub Release préliminaire
`catalog-YYYYMMDDTHHMMSSZ`. La Release contient seulement l’archive du catalogue et son checksum :
les fichiers EPUB et PDF sources ne sont jamais publiés.

Avant de le lancer :

1. vérifier `gh auth status` ;
2. commiter et pousser les changements de code ;
3. vérifier que `git status --short` est vide.

Indexer le Drive puis publier le résultat :

```bash
./scripts/publish_catalog \
  --drive-url 'https://drive.google.com/drive/folders/IDENTIFIANT_DU_DOSSIER' \
  --data ./data \
  --extensions epub
```

Si l’indexation locale est déjà terminée, publier telle quelle la base et les couvertures de
`./data`, sans relire le Drive :

```bash
./scripts/publish_catalog --skip-index --data ./data
```

Si une indexation est active, cette dernière commande demande son arrêt puis attend la fin du
livre en cours. Si le statut `running` est obsolète ou si l’indexation est bloquée avant tout
traitement, il est possible de forcer le snapshot :

```bash
./scripts/publish_catalog --skip-index --force-publish --data ./data
```

`--force-publish` ne désactive pas les contrôles d’intégrité, mais il ne faut l’utiliser que si
aucun processus n’est réellement en train de modifier SQLite ou les couvertures. À la fin, le
script affiche le tag et l’URL de la Release. Cette publication ne déclenche pas automatiquement
le déploiement Scaleway.

## `install_catalog` : récupérer un catalogue publié

Ce script télécharge une Release de catalogue avec `gh`, vérifie son checksum, son manifeste, sa
base SQLite et ses chemins, puis installe le résultat dans `deploy/catalog/`.

Lister les Releases disponibles :

```bash
gh release list
```

Installer une Release précise :

```bash
./scripts/install_catalog --tag catalog-20260801T194011Z
```

Le tag est obligatoire et doit respecter exactement le format `catalog-YYYYMMDDTHHMMSSZ`. Le
contenu existant de `deploy/catalog/` est remplacé seulement après validation complète de
l’archive téléchargée.

## `build_scaleway_image` : construire l’image localement

Ce script construit l’image `linux/amd64` attendue par Scaleway à partir du contenu de
`deploy/catalog/`. Il choisit Podman s’il est disponible, sinon Docker. L’image reste locale et
n’est envoyée dans aucun registre.

Il faut d’abord exécuter `build_catalog` ou `install_catalog`, puis démarrer le moteur de
conteneurs. Avec Podman sur macOS :

```bash
podman machine start
./scripts/build_scaleway_image
```

Choisir un autre nom d’image :

```bash
./scripts/build_scaleway_image --tag myebooks:scaleway-test
```

Forcer le moteur utilisé :

```bash
MYEBOOKS_CONTAINER_ENGINE=docker ./scripts/build_scaleway_image
```

Les variables `MYEBOOKS_IMAGE_TAG` et `MYEBOOKS_CONTAINER_ENGINE` sont les équivalents des options
de configuration du script.

## `deploy_scaleway` : déclencher le déploiement GitHub Actions

Ce script déclenche explicitement le workflow `deploy-scaleway.yml`. Il ne construit pas l’image
sur le Mac et ne contacte pas directement Scaleway. Les secrets et variables de l’environnement
GitHub `prod` doivent déjà être configurés.

Déclencher le déploiement sans attendre sa fin :

```bash
./scripts/deploy_scaleway --tag catalog-20260801T194011Z
```

Déclencher le déploiement et suivre son résultat dans le terminal :

```bash
./scripts/deploy_scaleway \
  --tag catalog-20260801T194011Z \
  --watch
```

Le tag doit correspondre à une Release existante. Pour utiliser un fork ou un autre dépôt :

```bash
MYEBOOKS_GITHUB_REPOSITORY=organisation/depot \
  ./scripts/deploy_scaleway --tag catalog-20260801T194011Z --watch
```

## `index_publish_deploy` : tout indexer, publier et déployer

Ce script sans argument réalise tout le cycle de production dans cet ordre :

1. indexation incrémentale des EPUB et PDF du Drive public ;
2. push du commit courant de `main` vers GitHub avec la clé SSH ;
3. publication de SQLite et des couvertures dans une nouvelle GitHub Release ;
4. déclenchement du déploiement Scaleway et attente du résultat de GitHub Actions.

Le Drive est fixé directement dans le script :

```text
https://drive.google.com/drive/folders/1WeqHFZQ0zl0Oy5u6JiabChlIGx3D5sie?usp=sharing
```

Il se lance simplement depuis la racine du dépôt :

```bash
./scripts/index_publish_deploy
```

Le script ne prend aucune option, pas même `--help`. Avant son lancement :

- arrêter `./start_dev` afin qu’aucune autre indexation ne soit active ;
- commiter tous les changements ;
- rester sur la branche `main` avec un dépôt propre ;
- vérifier que `origin` vaut `git@github.com:SPoint42/myEbooks.git` ;
- vérifier l’authentification avec `gh api user`.

Le script ne crée volontairement aucun commit automatique : cela évite d’ajouter par erreur un
fichier local, une donnée sensible ou une modification inachevée. Il s’arrête dès qu’une étape
échoue et ne déclenche donc pas Scaleway si l’indexation ou la publication a échoué.

## `_run_catalog` : composant interne

`scripts/_run_catalog` est le lanceur commun utilisé par `index_catalog`, `build_catalog`,
`publish_catalog` et `install_catalog`. Il prépare l’environnement Python puis appelle la CLI du
projet. Il n’est normalement pas nécessaire de l’exécuter directement.

## Enchaînements usuels

Tester seulement en local :

```bash
./start_dev --library /chemin/vers/mes/ebooks
```

Indexer, puis publier ultérieurement le cache obtenu :

```bash
./scripts/index_catalog --drive-url 'URL_DU_DRIVE' --data ./data
./scripts/publish_catalog --skip-index --data ./data
```

Récupérer un catalogue et vérifier localement que l’image Scaleway se construit :

```bash
./scripts/install_catalog --tag catalog-YYYYMMDDTHHMMSSZ
./scripts/build_scaleway_image --tag myebooks:scaleway-test
```

Publier puis déployer sont deux opérations séparées :

```bash
./scripts/publish_catalog --skip-index --data ./data
./scripts/deploy_scaleway --tag catalog-YYYYMMDDTHHMMSSZ --watch
```

Effectuer tout le cycle de production avec le Drive configuré pour ce projet :

```bash
./scripts/index_publish_deploy
```
