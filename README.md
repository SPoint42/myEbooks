# myEbooks

`myEbooks` est une petite bibliothèque Web auto-hébergée pour les fichiers PDF et EPUB
stockés dans un dossier ou un Drive partagé Google. L’application extrait le titre,
l’auteur, l’année, l’ISBN et la couverture lorsqu’ils sont présents, puis conserve le
résultat dans SQLite pour ne pas reparcourir les fichiers inchangés.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![License](https://img.shields.io/badge/license-MIT-156B52)

## Fonctionnalités du MVP

- galerie Web responsive, recherche instantanée par titre, auteur ou ISBN ;
- extraction des métadonnées Dublin Core et de la couverture des EPUB ;
- extraction des métadonnées, de l’ISBN textuel et rendu de la première page des PDF ;
- indexation à la demande, incrémentale par checksum ou date de modification ;
- cache SQLite pour les métadonnées et cache local pour les vignettes ;
- accès Google Drive strictement en lecture seule ;
- faux Drive intégré avec un vrai PDF et un vrai EPUB pour essayer le MVP immédiatement ;
- tests unitaires et d’intégration, CI GitHub Actions et image Docker non-root.

## Essai immédiat avec le faux Drive

Prérequis : Python 3.11 ou plus récent.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
EBOOK_SOURCE=fake uvicorn myebooks.main:app --reload
```

Ouvrez <http://127.0.0.1:8000>, puis cliquez sur **Indexer le Drive**. Deux livres de
démonstration apparaissent. Ils ont été générés puis analysés par les mêmes extracteurs que
les fichiers réels.

Avec Docker :

```bash
docker compose up --build
```

## Connexion à Google Drive

L’intégration utilise un compte de service Google et le scope
`https://www.googleapis.com/auth/drive.readonly`.

1. Dans Google Cloud, créez ou choisissez un projet et activez **Google Drive API**.
2. Créez un compte de service, puis téléchargez sa clé JSON dans un emplacement privé,
   hors du dépôt Git.
3. Partagez le dossier ou le Drive avec l’adresse e-mail du compte de service en lui donnant
   le rôle **Lecteur**.
4. Récupérez l’identifiant du dossier dans son URL. Pour un véritable Drive partagé, vous
   pouvez aussi renseigner son identifiant afin d’accélérer les requêtes.
5. Lancez l’application :

```bash
export EBOOK_SOURCE=google
export GOOGLE_SERVICE_ACCOUNT_FILE=/chemin/absolu/service-account.json
export GOOGLE_DRIVE_FOLDER_ID=1AbCDEF_identifiant_du_dossier
# Facultatif si le dossier appartient à un Drive partagé :
export GOOGLE_DRIVE_ID=0AExampleIdentifiantDrive
uvicorn myebooks.main:app --host 127.0.0.1 --port 8000
```

Si seul `GOOGLE_DRIVE_ID` est défini, tous les PDF et EPUB du Drive partagé sont listés.
Si `GOOGLE_DRIVE_FOLDER_ID` est défini, ses sous-dossiers sont parcourus récursivement.

Les variables disponibles sont documentées dans [`.env.example`](.env.example). Le fichier
JSON du compte de service ne doit jamais être commité.

## Fonctionnement de l’indexation

```text
Google Drive / Fake Drive
          │ liste + téléchargement temporaire
          ▼
    Extracteur PDF ou EPUB ──────► vignette dans data/covers/
          │
          └──────────────────────► métadonnées dans SQLite
```

À chaque demande, le backend compare le checksum Drive — ou à défaut la date de
modification — avec la valeur enregistrée. Seuls les fichiers nouveaux ou modifiés sont
téléchargés et analysés. Une option **Tout réanalyser** est disponible dans l’interface.
Un livre supprimé du périmètre Drive disparaît de la bibliothèque lors de la synchronisation
suivante.

Les ebooks complets restent en mémoire uniquement pendant leur analyse et ne sont pas
enregistrés sur le serveur. Les téléchargements et archives EPUB sont bornés pour limiter les
fichiers excessifs et les bombes de décompression.

## Tests et qualité

```bash
python -m pip install -e '.[dev]'
ruff check .
pytest
```

Les tests couvrent l’extraction PDF/EPUB, la validation ISBN, le rejet d’une archive EPUB
avec traversée de chemin, le cache incrémental, la suppression d’un livre et le parcours Web
avec protection CSRF.

## Limites connues du MVP

- aucun OCR : un ISBN présent uniquement dans l’image d’un PDF scanné ne sera pas détecté ;
- les PDF protégés par mot de passe ne sont pas pris en charge ;
- aucune authentification utilisateur : exposez l’application uniquement sur un réseau de
  confiance, ou placez-la derrière un reverse proxy avec authentification ;
- l’indexation s’exécute en tâche de fond dans le processus Web, sans file de travaux dédiée.

## Licence

MIT — voir [LICENSE](LICENSE).
