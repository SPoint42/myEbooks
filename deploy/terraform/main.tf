locals {
  resource_name = "${var.resource_prefix}-${var.environment}"
  common_tags   = ["myebooks", var.environment, "managed-by-terraform"]
}

resource "scaleway_registry_namespace" "this" {
  name      = local.resource_name
  region    = var.region
  is_public = false
}

resource "scaleway_container_namespace" "this" {
  name        = local.resource_name
  description = "myEbooks ${var.environment}"
  region      = var.region
}

resource "scaleway_container" "this" {
  name                   = local.resource_name
  description            = "Catalogue d'ebooks myEbooks en lecture seule"
  namespace_id           = scaleway_container_namespace.this.id
  image                  = var.image
  port                   = var.port
  cpu_limit              = var.cpu_limit
  memory_limit_bytes     = var.memory_limit_bytes
  min_scale              = var.min_scale
  max_scale              = var.max_scale
  timeout                = 600
  privacy                = "public"
  protocol               = "http1"
  https_connections_only = true
  tags                   = local.common_tags

  environment_variables = {
    EBOOK_SOURCE               = "google_public"
    EBOOK_DATA_DIR             = "/app/data"
    EBOOK_BACKGROUND_INDEX     = "0"
    EBOOK_FORCE_INDEX_ON_START = "0"
    GOOGLE_DRIVE_PUBLIC_URL    = var.google_drive_public_url
  }

  startup_probe {
    http {
      path = "/health"
    }
    failure_threshold = 20
    interval          = "5s"
    timeout           = "2s"
  }

  liveness_probe {
    http {
      path = "/health"
    }
    failure_threshold = 3
    interval          = "30s"
    timeout           = "5s"
  }

  scaling_option {
    concurrent_requests_threshold = 10
  }

  depends_on = [scaleway_registry_namespace.this]
}
