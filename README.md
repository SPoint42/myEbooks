# myEbooks

`myEbooks` est une petite bibliothèque Web auto-hébergée pour les fichiers PDF et EPUB
stockés dans un dossier Google Drive partagé par lien. L’application extrait le titre,
l’auteur, l’année, l’ISBN et la couverture lorsqu’ils sont présents, puis conserve le
résultat dans SQLite pour ne pas reparcourir les fichiers inchangés.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![License](https://img.shields.io/badge/license-MIT-156B52)

## Fonctionnalités du MVP

- galerie Web responsive, recherche, filtre par auteur et pagination de 10 livres par page ;
- extraction des métadonnées Dublin Core et de la couverture des EPUB ;
- extraction des métadonnées, de l’ISBN textuel et rendu de la première page des PDF ;
- indexation à la demande, incrémentale par checksum ou date de modification ;
- cache SQLite pour les métadonnées et cache local pour les vignettes ;
- accès Google Drive strictement en lecture seule ;
- configuration d’un dossier public avec son seul lien, sans compte Google ;
- téléchargement direct du PDF ou de l’EPUB depuis une liseuse Kobo ;
- interface HTML/CSS utilisable sans JavaScript ;
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

Ouvrez <http://127.0.0.1:8000/pandaIndexKobo>, puis cliquez sur **Indexer la bibliothèque**.
La bibliothèque publique reste accessible sur <http://127.0.0.1:8000>. Deux livres de
démonstration apparaissent. Ils ont été générés puis analysés par les mêmes extracteurs que
les fichiers réels.

Avec Docker :

```bash
docker compose up --build
```

## Tester avec un dossier local

Le mode `local` lit récursivement un dossier en lecture seule. Les PDF et EPUB restent à leur
emplacement d’origine ; seules les métadonnées et les couvertures sont enregistrées dans le
répertoire de données de l’application.

Pour utiliser la bibliothèque de test `cambook` sur cette machine :

```bash
cd /Users/s.gioria/perso/github.com/SPoint42/myEbooks
./start_dev
```

Le lanceur racine délègue à [`scripts/start_dev`](scripts/start_dev), où sont regroupés les
scripts du projet. Il crée `.venv` si nécessaire, installe les dépendances lors du premier
lancement ou après une modification de `pyproject.toml`, puis utilise par défaut
`/Users/s.gioria/goinfre/cambook`.

Ouvrez <http://127.0.0.1:8000/pandaIndexKobo> pour lancer l’indexation. La bibliothèque publique
reste accessible sur <http://127.0.0.1:8000>. Dans ce mode, seuls les fichiers du dossier local
configuré sont analysés.

Pour ouvrir également l’application depuis une Kobo connectée au même Wi-Fi, lancez :

```bash
./start_dev --kobo
```

Le script écoute alors sur le réseau local, détecte l’adresse IP du Mac et affiche directement
l’URL `http://ADRESSE_IP:8000/kobo` à saisir dans le navigateur de la liseuse. Cette page dédiée
utilise des boutons de formulaire pointant vers des URL terminant par `.epub` ou `.pdf`, du HTML
simple et aucun JavaScript.
Si macOS affiche une demande de pare-feu, autorisez Python à accepter les connexions entrantes.

Les options disponibles sont affichées avec `./start_dev --help`. Par exemple :

```bash
./start_dev --library /autre/dossier --port 8080 --no-reload
```

## Connexion par un lien Google Drive public

Le dossier doit être partagé avec l’accès général **Tous les utilisateurs disposant du lien**
et le rôle **Lecteur**. Vérifiez aussi que le téléchargement n’a pas été désactivé par le
propriétaire.

Copiez simplement l’URL du dossier puis lancez l’application :

```bash
./start_dev --kobo \
  --drive-url 'https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWx'
```

`--drive-url` sélectionne automatiquement la source `google_public`. Pour une utilisation sans
Kobo, retirez simplement l’option `--kobo` et ouvrez <http://127.0.0.1:8000>.

La commande et sa progression sont regroupées sur la page non liée `/pandaIndexKobo`. Aucun
bouton ni état d’indexation n’apparaît dans les bibliothèques `/` et `/kobo`.

Ce mode parcourt récursivement le dossier public avec `gdown`. Il ne nécessite ni compte de
service, ni clé Google Cloud. Le listing public ne fournit toutefois pas la date de
modification ou le checksum : utilisez **Tout réanalyser** lorsqu’un fichier a été remplacé
sur Drive en conservant le même identifiant.

## Télécharger directement sur une Kobo

1. Connectez la Kobo au même réseau que le serveur `myEbooks`.
2. Ouvrez le navigateur expérimental de la Kobo et saisissez l’adresse du serveur, par
   exemple `http://192.168.1.20:8000`.
3. Recherchez un livre avec le formulaire HTML.
4. Touchez **Télécharger sur Kobo**.

L’application récupère le fichier depuis Drive puis le sert avec son nom d’origine, le bon
type MIME et une réponse HTTP de téléchargement. Aucun JavaScript n’est nécessaire. Les
EPUB et PDF doivent être dépourvus d’Adobe DRM ; les fichiers protégés nécessitent Adobe
Digital Editions. Selon le modèle et son micrologiciel, un redémarrage ou une resynchronisation
de la bibliothèque peut être nécessaire après un téléchargement depuis le navigateur.

Ne rendez pas l’application accessible depuis Internet sans authentification : toute personne
ayant accès à son URL pourrait télécharger les livres indexés.

## Connexion par l’API Google Drive

Cette variante, utile pour un dossier non public, utilise un compte de service Google et le scope
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
Google Drive public / API / Fake Drive
          │ liste + téléchargement temporaire
          ▼
    Extracteur PDF ou EPUB ──────► vignette dans data/covers/
          │
          └──────────────────────► métadonnées dans SQLite
```

Avec l’API Google Drive, le backend compare le checksum — ou à défaut la date de modification —
avec la valeur enregistrée. Avec un lien public, il compare l’identifiant du fichier. Seuls les
fichiers nouveaux ou identifiés comme modifiés sont téléchargés et analysés. Une option
**Tout réanalyser** est disponible dans l’interface.
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
avec traversée de chemin, les connecteurs Drive API et public, le cache incrémental, la
suppression d’un livre, le téléchargement Kobo et le parcours Web avec protection CSRF.

## Limites connues du MVP

- aucun OCR : un ISBN présent uniquement dans l’image d’un PDF scanné ne sera pas détecté ;
- les PDF protégés par mot de passe ne sont pas pris en charge ;
- aucune authentification utilisateur : exposez l’application uniquement sur un réseau de
  confiance, ou placez-la derrière un reverse proxy avec authentification ;
- l’indexation s’exécute en tâche de fond dans le processus Web, sans file de travaux dédiée.

## Licence

MIT — voir [LICENSE](LICENSE).
