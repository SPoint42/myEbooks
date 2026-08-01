from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).parents[1]
WORKFLOW = PROJECT_DIR / ".github" / "workflows" / "deploy-scaleway.yml"
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

    action_references = re.findall(r"uses:\s+([^\s#]+)", workflow)
    assert action_references
    for reference in action_references:
        assert re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", reference), reference


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


def test_full_deploy_script_is_fixed_safe_and_uses_the_public_drive():
    assert os.access(FULL_DEPLOY_SCRIPT, os.X_OK)

    unexpected_argument = subprocess.run(
        [str(FULL_DEPLOY_SCRIPT), "--help"],
        cwd=PROJECT_DIR,
        capture_output=True,
        check=False,
        text=True,
    )
    assert unexpected_argument.returncode == 2
    assert "ne prend aucun argument" in unexpected_argument.stderr

    script = FULL_DEPLOY_SCRIPT.read_text()
    assert (
        "https://drive.google.com/drive/folders/"
        "1WeqHFZQ0zl0Oy5u6JiabChlIGx3D5sie?usp=sharing"
    ) in script
    assert 'INDEX_EXTENSIONS="epub"' in script
    assert '"${SCRIPT_DIR}/index_catalog"' in script
    assert 'git push origin "$EXPECTED_BRANCH"' in script
    assert '"${SCRIPT_DIR}/publish_catalog" --skip-index' in script
    assert '"${SCRIPT_DIR}/deploy_scaleway" --tag "$CATALOG_TAG" --watch' in script
    assert "git add" not in script
    assert "git commit" not in script
