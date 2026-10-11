from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).parents[1]
WORKFLOW = PROJECT_DIR / ".github" / "workflows" / "deploy-scaleway.yml"
DOCKERFILE = PROJECT_DIR / "Dockerfile"
CONSTRAINTS = PROJECT_DIR / "constraints.txt"
TRIVY_IGNORE = PROJECT_DIR / ".trivyignore.yaml"
TERRAFORM_DIR = PROJECT_DIR / "deploy" / "terraform"
DEPLOY_SCRIPT = PROJECT_DIR / "scripts" / "deploy_scaleway"
FULL_DEPLOY_SCRIPT = PROJECT_DIR / "scripts" / "index_publish_deploy"


def test_deployment_workflow_is_manual_pinned_and_catalog_driven():
    workflow = WORKFLOW.read_text()

    assert "workflow_dispatch:" in workflow
    assert "catalog_tag:" in workflow
    assert "pull_request_target:" not in workflow
    assert "workflow_run:" not in workflow
    assert "environment: prod" in workflow
    assert "./scripts/install_catalog --tag \"$CATALOG_TAG\"" in workflow
    assert "--target scaleway" in workflow
    assert "terraform -chdir=\"$TERRAFORM_DIR\" apply" in workflow
    assert "EBOOK_BACKGROUND_INDEX" not in workflow
    assert "version: v0.74.0" in workflow
    assert "trivyignores: .trivyignore.yaml" in workflow

    action_references = re.findall(r"uses:\s+([^\s#]+)", workflow)
    assert action_references
    for reference in action_references:
        assert re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", reference), reference


def test_deployment_image_pins_base_updates_os_and_sets_security_dependency_floors():
    dockerfile = DOCKERFILE.read_text()
    constraints = CONSTRAINTS.read_text()

    assert (
        "FROM python:3.13.16-slim-trixie@"
        "sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f"
    ) in dockerfile
    assert "apt-get update" in dockerfile
    assert "apt-get upgrade --yes" in dockerfile
    assert "rm -rf /var/lib/apt/lists/*" in dockerfile
    assert "--constraint constraints.txt" in dockerfile
    assert "setuptools msgpack urllib3" in dockerfile
    assert "python -m pip check" in dockerfile
    assert "msgpack>=1.2.1" in constraints
    assert "setuptools>=78.1.1" in constraints
    assert "urllib3>=2.8.0" in constraints


def test_trivy_ignores_only_stale_base_sbom_packages_temporarily():
    trivy_ignore = TRIVY_IGNORE.read_text()

    assert "GHSA-6v7p-g79w-8964" in trivy_ignore
    assert "pkg:pypi/msgpack@1.1.2" in trivy_ignore
    assert "CVE-2025-47273" in trivy_ignore
    assert "pkg:pypi/setuptools@70.3.0" in trivy_ignore
    assert "CVE-2026-97687" in trivy_ignore
    assert "CVE-2026-97689" in trivy_ignore
    assert trivy_ignore.count("pkg:pypi/urllib3@2.7.0") == 2
    assert trivy_ignore.count("expired_at: 2026-11-11") == 4
    assert trivy_ignore.count("False positive from the pinned Python base image SBOM") == 4


def test_terraform_uses_read_only_scale_to_zero_runtime_and_current_fields():
    terraform = "\n".join(
        path.read_text() for path in sorted(TERRAFORM_DIR.glob("*.tf"))
    )

    assert 'is_public = false' in terraform
    assert 'privacy                = "public"' in terraform
    assert 'EBOOK_BACKGROUND_INDEX     = "0"' in terraform
    assert 'EBOOK_FORCE_INDEX_ON_START = "0"' in terraform
    assert 'EBOOK_SOURCE               = "google_public"' in terraform
    assert 'default     = 0' in terraform
    assert 'default     = 1' in terraform
    assert "memory_limit_bytes" in terraform
    assert "liveness_probe" in terraform
    assert "startup_probe" in terraform
    assert 'interval          = "5s"' in terraform
    assert "public_endpoint" in terraform

    assert "registry_image" not in terraform
    assert not re.search(r"\bmemory_limit\s*=", terraform)
    assert not re.search(r"\bdeploy\s*=", terraform)
    assert "domain_name" not in terraform


def test_deploy_script_is_executable_and_rejects_invalid_catalog_tag():
    assert os.access(DEPLOY_SCRIPT, os.X_OK)

    help_result = subprocess.run(
        [str(DEPLOY_SCRIPT), "--help"],
        cwd=PROJECT_DIR,
        capture_output=True,
        check=False,
        text=True,
    )
    assert help_result.returncode == 0
    assert "catalog-YYYYMMDDTHHMMSSZ" in help_result.stdout
    assert "--watch" in help_result.stdout

    invalid_result = subprocess.run(
        [str(DEPLOY_SCRIPT), "--tag", "catalog-latest"],
        cwd=PROJECT_DIR,
        capture_output=True,
        check=False,
        text=True,
    )
    assert invalid_result.returncode == 2
    assert "catalog-YYYYMMDDTHHMMSSZ" in invalid_result.stderr


def test_full_deploy_script_indexes_one_format_and_publishes_the_whole_catalog():
    assert os.access(FULL_DEPLOY_SCRIPT, os.X_OK)

    help_result = subprocess.run(
        [str(FULL_DEPLOY_SCRIPT), "--help"],
        cwd=PROJECT_DIR,
        capture_output=True,
        check=False,
        text=True,
    )
    assert help_result.returncode == 0
    assert "<epub|pdf>" in help_result.stdout

    missing_argument = subprocess.run(
        [str(FULL_DEPLOY_SCRIPT)],
        cwd=PROJECT_DIR,
        capture_output=True,
        check=False,
        text=True,
    )
    assert missing_argument.returncode == 2
    assert "exactement un format" in missing_argument.stderr

    invalid_format = subprocess.run(
        [str(FULL_DEPLOY_SCRIPT), "epub,pdf"],
        cwd=PROJECT_DIR,
        capture_output=True,
        check=False,
        text=True,
    )
    assert invalid_format.returncode == 2
    assert "format invalide" in invalid_format.stderr

    script = FULL_DEPLOY_SCRIPT.read_text()
    assert (
        "https://drive.google.com/drive/folders/"
        "1WeqHFZQ0zl0Oy5u6JiabChlIGx3D5sie?usp=sharing"
    ) in script
    assert '--extensions "$INDEX_EXTENSION"' in script
    assert "--preserve-unselected" in script
    assert '"${SCRIPT_DIR}/index_catalog"' in script
    assert 'git push origin "$EXPECTED_BRANCH"' in script
    assert '"${SCRIPT_DIR}/publish_catalog" --skip-index' in script
    assert '"${SCRIPT_DIR}/deploy_scaleway" --tag "$CATALOG_TAG" --watch' in script
    assert "git add" not in script
    assert "git commit" not in script
