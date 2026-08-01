from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

from .catalog import (
    CATALOG_TAG,
    build_catalog_artifact,
    index_library,
    install_catalog_archive,
    publish_catalog_release,
)
from .config import Settings, parse_index_extensions
from .sources import create_source

PROJECT_DIR = Path(__file__).resolve().parents[2]


def _parse_extension_argument(raw: str) -> frozenset[str]:
    try:
        return parse_index_extensions(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--drive-url", help="URL HTTPS du dossier Google Drive public")
    sources.add_argument("--library", type=Path, help="Dossier local de fichiers EPUB/PDF")
    sources.add_argument("--fake", action="store_true", help="Utilise les deux ebooks de démo")
    parser.add_argument(
        "--data",
        type=Path,
        default=PROJECT_DIR / "data",
        help="Cache local SQLite et vignettes (défaut : ./data)",
    )
    parser.add_argument("--force", action="store_true", help="Réanalyse tous les fichiers")
    parser.add_argument(
        "--extensions",
        type=_parse_extension_argument,
        metavar="LISTE",
        help="Extensions à indexer, séparées par des virgules (défaut : epub)",
    )


def _settings_from_arguments(arguments: argparse.Namespace) -> Settings:
    data_dir = arguments.data.expanduser().resolve()
    index_extensions = arguments.extensions or parse_index_extensions(
        os.getenv("EBOOK_INDEX_EXTENSIONS", "epub")
    )
    if arguments.drive_url:
        settings = Settings(
            data_dir=data_dir,
            source="google_public",
            google_drive_public_url=arguments.drive_url,
            index_extensions=index_extensions,
        )
    elif arguments.library:
        settings = Settings(
            data_dir=data_dir,
            source="local",
            local_library_dir=arguments.library.expanduser().resolve(),
            index_extensions=index_extensions,
        )
    elif arguments.fake:
        settings = Settings(
            data_dir=data_dir,
            source="fake",
            index_extensions=index_extensions,
        )
    else:
        os.environ["EBOOK_DATA_DIR"] = str(data_dir)
        settings = Settings.from_env()
        settings = replace(settings, index_extensions=index_extensions)
    settings.validate()
    return settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="myebooks-catalog",
        description="Indexe localement les ebooks et construit le catalogue de déploiement.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    index_parser = commands.add_parser("index", help="Met à jour la base SQLite locale")
    _add_source_arguments(index_parser)

    build_parser = commands.add_parser(
        "build",
        help="Indexe puis génère l'artefact SQLite et vignettes",
        description="Indexe puis génère l'artefact SQLite, les vignettes et leur checksum.",
    )
    _add_source_arguments(build_parser)
    build_parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_DIR / "dist",
        help="Répertoire des archives (défaut : ./dist)",
    )
    build_parser.add_argument(
        "--publish",
        action="store_true",
        help="Publie l'archive comme GitHub Release avec gh",
    )
    build_parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Publie uniquement le cache --data existant, sans contacter la source",
    )
    build_parser.add_argument(
        "--force-publish",
        action="store_true",
        help="Ignore un statut d'indexation active avec --skip-index",
    )

    install_parser = commands.add_parser(
        "install", help="Télécharge et vérifie un artefact GitHub avant le build Docker"
    )
    install_parser.add_argument("--tag", required=True, help="Tag catalog-YYYYMMDDTHHMMSSZ")
    return parser


def _install_from_github(tag: str) -> None:
    if not CATALOG_TAG.fullmatch(tag):
        raise ValueError("Le tag doit respecter catalog-YYYYMMDDTHHMMSSZ")
    if shutil.which("gh") is None:
        raise RuntimeError("La commande gh est requise pour installer un catalogue GitHub")
    with tempfile.TemporaryDirectory(prefix="myebooks-release-") as temporary:
        download_dir = Path(temporary)
        subprocess.run(
            [
                "gh",
                "release",
                "download",
                tag,
                "--pattern",
                "myebooks-catalog-*.tar.gz*",
                "--dir",
                str(download_dir),
            ],
            cwd=PROJECT_DIR,
            check=True,
        )
        archives = sorted(download_dir.glob("*.tar.gz"))
        checksums = sorted(download_dir.glob("*.tar.gz.sha256"))
        if len(archives) != 1 or len(checksums) != 1:
            raise RuntimeError("La Release doit contenir une archive et son checksum")
        install_catalog_archive(
            archives[0], checksums[0], staged_catalog=PROJECT_DIR / "deploy" / "catalog"
        )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = _parser()
    arguments = parser.parse_args(argv)

    if arguments.command == "install":
        _install_from_github(arguments.tag)
        print(f"Catalogue {arguments.tag} installé dans deploy/catalog")
        return 0

    if arguments.command == "index":
        settings = _settings_from_arguments(arguments)
        source = create_source(settings)
        result = index_library(settings, source, force=arguments.force)
        print(
            f"Indexation terminée : {result.indexed} indexé(s), "
            f"{result.unchanged} inchangé(s), {result.failed} en erreur, "
            f"{result.removed} supprimé(s), sur {result.discovered} livre(s)."
        )
        return 0

    if arguments.force_publish and not arguments.skip_index:
        parser.error("--force-publish nécessite --skip-index")
    if arguments.skip_index:
        if (
            arguments.drive_url
            or arguments.library
            or arguments.fake
            or arguments.force
            or arguments.extensions is not None
        ):
            parser.error(
                "--skip-index ne peut pas être combiné avec une source, --extensions "
                "ou --force ; "
                "utilisez seulement --data et éventuellement --output."
            )
        settings = Settings(data_dir=arguments.data.expanduser().resolve())
        source = None
    else:
        settings = _settings_from_arguments(arguments)
        source = create_source(settings)

    artifact = build_catalog_artifact(
        settings,
        source,
        output_dir=arguments.output.expanduser().resolve(),
        staged_catalog=PROJECT_DIR / "deploy" / "catalog",
        force=arguments.force,
        skip_index=arguments.skip_index,
        force_publish=arguments.force_publish,
    )
    print(f"Catalogue généré : {artifact.archive_path}")
    print(f"Checksum SHA-256 : {artifact.checksum_path}")
    print(f"Image Scaleway prête à construire depuis : {artifact.staged_catalog}")
    if arguments.publish:
        tag = publish_catalog_release(artifact, project_dir=PROJECT_DIR)
        print(f"Catalogue publié dans la GitHub Release {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
