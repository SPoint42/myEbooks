# Scripts du projet

Les scripts opérationnels de `myEbooks` sont regroupés dans ce répertoire.

- `start_dev` prépare l’environnement Python, lance immédiatement le serveur Web puis met à
  jour SQLite en arrière-plan. Son option `--kobo` ouvre l’écoute sur le réseau local.
- `index_catalog` met uniquement à jour `data/myebooks.sqlite3` et les vignettes locales.
- `build_catalog` indexe puis génère une archive vérifiable dans `dist/` et prépare
  `deploy/catalog/` pour construire l’image Scaleway.
- `publish_catalog` réalise le même travail puis publie l’archive et son SHA-256 dans une
  GitHub Release avec `gh`. Son option `--skip-index` publie directement le cache `--data`
  existant sans contacter la source et arrête proprement une indexation locale active. Il ne
  publie jamais les fichiers EPUB/PDF.
- `install_catalog --tag catalog-YYYYMMDDTHHMMSSZ` récupère une Release, vérifie son SHA-256
  et installe son contenu dans `deploy/catalog/` avant un build Docker.
- `build_scaleway_image` construit localement l’image `linux/amd64` attendue par Scaleway, sans
  la publier dans un registre.
- `deploy_scaleway --tag catalog-YYYYMMDDTHHMMSSZ` déclenche explicitement le workflow GitHub
  Actions de déploiement. L’option `--watch` attend son résultat. Ce script nécessite que les
  secrets et variables de l’environnement GitHub `prod` soient déjà configurés.

Le fichier `../start_dev` est uniquement un point d’entrée court permettant d’exécuter
`./start_dev` depuis la racine du dépôt.
