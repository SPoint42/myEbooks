# myEbooks

`myEbooks` est une petite bibliothèque Web pour les fichiers EPUB et PDF stockés dans un
dossier Google Drive partagé par lien. Sur le Mac, l’application démarre immédiatement puis
extrait le titre, l’auteur, l’année, l’ISBN et la couverture en arrière-plan dans SQLite. L’image
Scaleway consomme ensuite un catalogue préconstruit en lecture seule. Aucun endpoint HTTP ne
permet de déclencher une indexation.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![License](https://img.shields.io/badge/license-MIT-156B52)

## Fonctionnalités

- galerie Web responsive, recherche, filtre par auteur et pagination de 10 livres par page ;
- page d’accueil classée du livre le plus récemment indexé au plus ancien ;
- sélection des formats à indexer avec une liste d’extensions (`epub`, `pdf`) ;
- extraction des métadonnées, de l’ISBN et de la couverture des EPUB et PDF ;
- indexation locale incrémentale par checksum ou date de modification ;
- accès Google Drive strictement en lecture seule, par lien public ou compte de service ;
- téléchargement direct de l’ebook depuis une Kobo ;
- interface HTML/CSS utilisable sans JavaScript ;
- catalogue SQLite et vignettes publiables comme artefact GitHub vérifié par SHA-256 ;
- runtime SQLite strictement en lecture seule et image Docker non-root pour Scaleway ;
- faux Drive intégré, tests automatisés et CI GitHub Actions.

## Tester avec la bibliothèque locale `cambook`

Prérequis : Python 3.11 ou plus récent.

```bash
cd /Users/s.gioria/perso/github.com/SPoint42/myEbooks
./start_dev
```

Le lanceur crée `.venv` si nécessaire et démarre l’application sur
<http://127.0.0.1:8000>. L’indexation de `/Users/s.gioria/goinfre/cambook` commence dans un
thread en arrière-plan : le site reste accessible avec le catalogue existant pendant la mise à
jour. Les lancements suivants sont incrémentaux.

Pour tout réanalyser :

```bash
./start_dev --force-index
```

Pour rendre l’application accessible à une Kobo sur le même Wi-Fi :

```bash
./start_dev --kobo
```

Le terminal affiche l’adresse `http://ADRESSE_IP:8000/kobo`. La page Kobo utilise du HTML
simple, des formulaires natifs et aucun JavaScript. Si macOS le demande, autorisez Python à
accepter les connexions entrantes.

Les options sont affichées par `./start_dev --help` :

```bash
./start_dev --library /autre/dossier --port 8080 --no-reload
```

## Utiliser le Google Drive public

Le dossier doit être partagé avec l’accès général **Tous les utilisateurs disposant du lien**
et le rôle **Lecteur**. Le propriétaire ne doit pas avoir désactivé le téléchargement.

```bash
./start_dev --kobo \
  --drive-url 'https://drive.google.com/drive/folders/1WeqHFZQ0zl0Oy5u6JiabChlIGx3D5sie?usp=sharing'
```

Le serveur répond immédiatement et la progression de l’indexation apparaît dans le terminal.
Les nouvelles entrées SQLite deviennent visibles au fil de leur traitement. Aucun endpoint ou
bouton d’indexation n’existe dans `/`, `/kobo` ou ailleurs dans l’application Web.

Le listing public ne fournit ni date de modification ni checksum. Utilisez `--force-index`
lorsqu’un fichier a été remplacé sur Drive en conservant le même identifiant.
Par défaut, seuls les EPUB sont indexés. Pour inclure aussi les PDF :

```bash
./start_dev --kobo --extensions epub,pdf \
  --drive-url 'https://drive.google.com/drive/folders/1WeqHFZQ0zl0Oy5u6JiabChlIGx3D5sie?usp=sharing'
```

## Construire le catalogue de déploiement

Pour indexer le Drive sans démarrer le serveur, générer l’archive et préparer l’image Docker :

```bash
./scripts/build_catalog \
  --extensions epub,pdf \
  --drive-url 'https://drive.google.com/drive/folders/1WeqHFZQ0zl0Oy5u6JiabChlIGx3D5sie?usp=sharing'
```

Le script produit :

- `data/myebooks.sqlite3` et `data/covers/`, cache incrémental local ;
- `dist/myebooks-catalog-YYYYMMDDTHHMMSSZ.tar.gz`, artefact transportable ;
- le fichier `.sha256` associé ;
- `deploy/catalog/`, contenu incorporé à l’image Scaleway.

L’archive contient uniquement SQLite, un manifeste et les vignettes référencées. Aucun fichier
EPUB ou PDF source n’est copié dans l’artefact. La base exportée est une copie SQLite cohérente, sans
journal WAL, contrôlée avant sa mise en archive.

Pour mettre uniquement à jour le cache local :

```bash
./scripts/index_catalog \
  --drive-url 'https://drive.google.com/drive/folders/1WeqHFZQ0zl0Oy5u6JiabChlIGx3D5sie?usp=sharing'
```

Les scripts acceptent également `--library /chemin/vers/les/ebooks`, `--fake`, `--data`,
`--force` et `--extensions epub,pdf`. La variable équivalente est
`EBOOK_INDEX_EXTENSIONS=epub,pdf`.

## Publier le catalogue comme artefact GitHub

Après avoir contrôlé le catalogue localement :

```bash
./scripts/publish_catalog \
  --drive-url 'https://drive.google.com/drive/folders/1WeqHFZQ0zl0Oy5u6JiabChlIGx3D5sie?usp=sharing'
```

La CLI `gh` doit être installée et authentifiée, et les changements de code doivent déjà être
commités. Le script crée une GitHub Release préliminaire nommée
`catalog-YYYYMMDDTHHMMSSZ`, contenant l’archive et son SHA-256. La publication est explicite :
`index_catalog` et `build_catalog` ne contactent jamais GitHub.

Si `./data` a déjà été complètement indexé, publier son état exact sans relire le Drive :

```bash
./scripts/publish_catalog --skip-index --data ./data
```

Ce mode n’accepte ni option de source ni `--force` et ne contacte aucun connecteur. Si une
indexation est active, il lui demande de s’arrêter proprement, attend la fin du livre en cours,
puis publie les données déjà acquises. Il contrôle ensuite l’intégrité de la base et la présence
de toutes les vignettes référencées.

Si le statut `running` est obsolète et que l’indexation est réellement terminée, forcer le
snapshot sans attendre ni envoyer de demande d’arrêt :

```bash
./scripts/publish_catalog --skip-index --force-publish --data ./data
```

Cet override ne désactive pas les contrôles d’intégrité. Ne l’utiliser que si aucun processus
n’écrit encore réellement dans `./data`.

Depuis un checkout propre, l’artefact peut être récupéré et contrôlé avec :

```bash
./scripts/install_catalog --tag catalog-YYYYMMDDTHHMMSSZ
```

Le checksum, le manifeste, la base SQLite, les chemins, le type et la taille de chaque entrée
sont vérifiés avant l’installation dans `deploy/catalog/`.

## Valider localement l’image Scaleway

Après `build_catalog` ou `install_catalog` :

```bash
./scripts/build_scaleway_image --tag myebooks:scaleway
docker run --rm -p 8000:8000 \
  -e EBOOK_SOURCE=google_public \
  -e GOOGLE_DRIVE_PUBLIC_URL='https://drive.google.com/drive/folders/1WeqHFZQ0zl0Oy5u6JiabChlIGx3D5sie?usp=sharing' \
  myebooks:scaleway
```

Le script force la plateforme `linux/amd64` attendue par Scaleway, y compris depuis un Mac Apple
Silicon. Le stage Docker `scaleway` refuse de se construire si SQLite, le manifeste ou le
répertoire des vignettes sont absents. Le serveur accepte la variable `PORT` fournie par une
plateforme serverless. Ces commandes ne publient aucune image et ne créent aucune ressource
Scaleway.

Pour tester l’image `runtime` avec le cache local monté en lecture seule :

```bash
docker compose up --build
```

## Déployer sur Scaleway avec GitHub Actions

Le workflow `Deploy myEbooks to Scaleway` réalise un déploiement manuel et reproductible. Il
associe toujours l’image au commit exact de la Release du catalogue, vérifie le catalogue, lance
les tests, construit le stage Docker `scaleway`, analyse l’image avec Trivy, la publie dans un
registre privé puis applique `deploy/terraform/`.

Le Serverless Container utilise 256 Mio, `min_scale = 0` et `max_scale = 1`. Il n’indexe rien :
SQLite et les vignettes sont incorporées à l’image et ouvertes en lecture seule. Son endpoint
HTTPS reste public afin que le navigateur Kobo puisse le consulter sans jeton Scaleway.

### Configuration GitHub à effectuer une seule fois

Dans **Settings → Environments**, créer l’environnement `prod`, l’autoriser uniquement depuis
`main`, puis ajouter les secrets suivants :

| Secret d’environnement | Valeur |
| --- | --- |
| `SCW_ACCESS_KEY` | Access key de l’application IAM Scaleway dédiée |
| `SCW_SECRET_KEY` | Secret key correspondant |
| `SCW_PROJECT_ID` | Identifiant du projet Scaleway cible |
| `SCW_ORGANIZATION_ID` | Identifiant de l’organisation Scaleway |

Ajouter ensuite ces variables dans le même environnement :

| Variable d’environnement | Valeur |
| --- | --- |
| `GOOGLE_DRIVE_PUBLIC_URL` | URL HTTPS du dossier Drive public |
| `SCW_TF_STATE_BUCKET` | Facultatif, défaut : `security-tools-tfstate` |

L’application IAM Scaleway utilisée par GitHub doit être limitée au projet cible et posséder
`ContainerRegistryFullAccess`, `ContainersFullAccess` et `ObjectStorageFullAccess`. La dernière
permission permet d’utiliser le bucket S3 comme backend Terraform. Le workflow stocke son état
avec la clé distincte `myebooks/prod/terraform.tfstate`.

### Premier déploiement

Les fichiers de déploiement doivent d’abord être commités et poussés sur `main`. Depuis ce
checkout propre, publier ensuite le catalogue :

```bash
./scripts/publish_catalog \
  --drive-url 'https://drive.google.com/drive/folders/1WeqHFZQ0zl0Oy5u6JiabChlIGx3D5sie?usp=sharing'
```

Noter le tag affiché, puis aller dans **Actions → Deploy myEbooks to Scaleway → Run workflow** et
saisir ce tag. La même opération peut être déclenchée depuis le Mac :

```bash
./scripts/deploy_scaleway --tag catalog-YYYYMMDDTHHMMSSZ --watch
```

Le workflow demande l’accès à l’environnement `prod` uniquement après avoir validé le tag,
testé le commit associé et vérifié l’archive. Son résumé fournit l’URL Scaleway finale. Tester
également `URL/health`, puis ouvrir cette URL dans le navigateur de la Kobo.

Pour publier une mise à jour déjà indexée dans `./data`, lancer
`./scripts/publish_catalog --skip-index --data ./data` — avec `--force-publish` uniquement pour
ignorer un statut actif obsolète — puis déployer le nouveau tag. Les
anciens tags d’image peuvent être supprimés périodiquement du Container Registry afin de limiter
le stockage facturé.

## Télécharger directement sur une Kobo

1. Ouvrez le navigateur expérimental de la Kobo.
2. Saisissez l’adresse du serveur.
3. Recherchez un livre avec le formulaire HTML.
4. Touchez **Télécharger sur Kobo**.

L’application récupère l’EPUB ou le PDF depuis Drive puis le sert avec son nom d’origine et le bon type
MIME. Le fichier doit être dépourvu d’Adobe DRM. Selon le modèle de Kobo, un redémarrage ou une
resynchronisation de la bibliothèque peut être nécessaire.

Ne rendez pas l’application publique sans contrôle d’accès : toute personne disposant de son
URL peut consulter la bibliothèque et télécharger les livres indexés. Le mode public est requis
par le déploiement actuel pour ne pas demander de jeton IAM dans le navigateur Kobo.

## Variante avec l’API Google Drive

Pour un dossier non public, utilisez un compte de service Google avec le scope
`https://www.googleapis.com/auth/drive.readonly`, puis configurez :

```bash
export EBOOK_SOURCE=google
export GOOGLE_SERVICE_ACCOUNT_FILE=/chemin/absolu/service-account.json
export GOOGLE_DRIVE_FOLDER_ID=identifiant_du_dossier
# Facultatif pour un véritable Drive partagé :
export GOOGLE_DRIVE_ID=identifiant_du_drive
./scripts/build_catalog
```

Le fichier JSON du compte de service doit rester hors du dépôt. Les variables disponibles sont
documentées dans [`.env.example`](.env.example).

## Flux des données

```text
Google Drive / dossier local
          │ script exécuté sur le Mac
          ▼
     Extracteur EPUB/PDF ────────► vignettes
          │
          └──────────────────────► SQLite
                                      │
                                      ▼
                       archive GitHub + SHA-256
                                      │
                                      ▼
                         image Web en lecture seule
```

Avec l’API Google Drive, le script compare le checksum, ou à défaut la date de modification,
avec la valeur enregistrée. Avec un lien public, il compare l’identifiant du fichier. Un livre
supprimé du périmètre disparaît lors de l’indexation suivante.

## Tests et qualité

```bash
python -m pip install -e '.[dev]'
ruff check .
pytest
```

Les tests couvrent notamment l’extraction EPUB/PDF, les connecteurs Drive, l’indexation de démarrage
en arrière-plan, la création et la vérification de l’artefact, le runtime SQLite en lecture seule,
le classement des derniers livres indexés, la pagination, les téléchargements Kobo et la
structure sécurisée du déploiement GitHub Actions/Terraform.

## Limites connues

- seuls les formats EPUB et PDF sont actuellement pris en charge ;
- aucune authentification utilisateur intégrée ;
- une nouvelle indexation n’est visible en production qu’après publication du catalogue et
  construction d’une nouvelle image.

## Licence

MIT — voir [LICENSE](LICENSE).
