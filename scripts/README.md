# Scripts du projet

Les scripts opérationnels de `myEbooks` sont regroupés dans ce répertoire.

- `start_dev` prépare l’environnement Python et lance le serveur de développement avec une
  bibliothèque locale. Son option `--kobo` ouvre l’écoute sur le réseau local et affiche
  l’adresse simplifiée `/kobo` à saisir sur la liseuse. L’option `--drive-url` remplace la
  bibliothèque locale par un dossier Google Drive public.

Le fichier `../start_dev` est uniquement un point d’entrée court permettant d’exécuter
`./start_dev` depuis la racine du dépôt.
