# myEbooks

`myEbooks` est une petite bibliothèque Web pour les fichiers PDF et EPUB stockés dans un
dossier Google Drive partagé par lien. Un script exécuté sur le Mac extrait le titre, l’auteur,
l’année, l’ISBN et la couverture. L’application Web ouvre ensuite ce catalogue SQLite en lecture
seule : aucune indexation ne peut être déclenchée depuis le serveur.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![License](https://img.shields.io/badge/license-MIT-156B52)

## Fonctionnalités

- galerie Web responsive, recherche, filtre par auteur et pagination de 10 livres par page ;
- page d’accueil classée du livre le plus récemment indexé au plus ancien ;
- extraction des métadonnées, de l’ISBN et de la couverture des EPUB et PDF ;
- indexation locale incrémentale par checksum ou date de modification ;
- accès Google Drive strictement en lecture seule, par lien public ou compte de service ;
- téléchargement direct du PDF ou de l’EPUB depuis une Kobo ;
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

Le lanceur crée `.venv` si nécessaire, indexe localement
`/Users/s.gioria/goinfre/cambook`, puis démarre l’application en lecture seule sur
<http://127.0.0.1:8000>. Les lancements suivants sont incrémentaux.

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

L’indexation se termine avant le démarrage du serveur et sa progression apparaît dans le
terminal. Aucun endpoint ou bouton d’indexation n’existe dans `/`, `/kobo` ou ailleurs dans
l’application Web.

Le listing public ne fournit ni date de modification ni checksum. Utilisez `--force-index`
lorsqu’un fichier a été remplacé sur Drive en conservant le même identifiant.

## Construire le catalogue de déploiement

Pour indexer le Drive sans démarrer le serveur, générer l’archive et préparer l’image Docker :

```bash
./scripts/build_catalog \
  --drive-url 'https://drive.google.com/drive/folders/1WeqHFZQ0zl0Oy5u6JiabChlIGx3D5sie?usp=sharing'
```

Le script produit :

- `data/myebooks.sqlite3` et `data/covers/`, cache incrémental local ;
- `dist/myebooks-catalog-YYYYMMDDTHHMMSSZ.tar.gz`, artefact transportable ;
- le fichier `.sha256` associé ;
- `deploy/catalog/`, contenu incorporé à l’image Scaleway.

L’archive contient uniquement SQLite, un manifeste et les vignettes référencées. Aucun EPUB ou
PDF n’est copié dans l’artefact. La base exportée est une copie SQLite cohérente, sans journal
WAL, contrôlée avant sa mise en archive.

Pour mettre uniquement à jour le cache local :

```bash
./scripts/index_catalog \
  --drive-url 'https://drive.google.com/drive/folders/1WeqHFZQ0zl0Oy5u6JiabChlIGx3D5sie?usp=sharing'
```

Les scripts acceptent également `--library /chemin/vers/les/ebooks`, `--fake`, `--data` et
`--force`.

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

## Télécharger directement sur une Kobo

1. Ouvrez le navigateur expérimental de la Kobo.
2. Saisissez l’adresse du serveur.
3. Recherchez un livre avec le formulaire HTML.
4. Touchez **Télécharger sur Kobo**.

L’application récupère le fichier depuis Drive puis le sert avec son nom d’origine et le bon
type MIME. Les EPUB et PDF doivent être dépourvus d’Adobe DRM. Selon le modèle de Kobo, un
redémarrage ou une resynchronisation de la bibliothèque peut être nécessaire.

Ne rendez pas l’application publique sans contrôle d’accès : toute personne disposant de son
URL pourrait télécharger les livres indexés.

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
    Extracteur PDF ou EPUB ──────► vignettes
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

Les tests couvrent notamment l’extraction PDF/EPUB, les connecteurs Drive, le cache incrémental,
la création et la vérification de l’artefact, le runtime SQLite en lecture seule, le classement
des derniers livres indexés, la pagination et les téléchargements Kobo.

## Limites connues

- aucun OCR pour les ISBN présents uniquement dans l’image d’un PDF scanné ;
- les PDF protégés par mot de passe ne sont pas pris en charge ;
- aucune authentification utilisateur intégrée ;
- une nouvelle indexation n’est visible en production qu’après publication du catalogue et
  construction d’une nouvelle image.

## Licence

MIT — voir [LICENSE](LICENSE).
