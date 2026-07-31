variable "environment" {
  description = "Nom de l'environnement de deploiement"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["prod"], var.environment)
    error_message = "L'environnement autorise est prod."
  }
}

variable "resource_prefix" {
  description = "Prefixe stable et globalement distinct des ressources Scaleway"
  type        = string
  default     = "spoint42-myebooks"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{2,31}$", var.resource_prefix))
    error_message = "resource_prefix doit contenir de 3 a 32 caracteres minuscules, chiffres ou tirets."
  }
}

variable "region" {
  description = "Region Scaleway"
  type        = string
  default     = "fr-par"
}

variable "zone" {
  description = "Zone Scaleway utilisee par le provider"
  type        = string
  default     = "fr-par-1"
}

variable "image" {
  description = "Reference immuable de l'image publiee dans Scaleway Container Registry"
  type        = string

  validation {
    condition = can(regex(
      "^rg\\.[a-z0-9-]+\\.scw\\.cloud/[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9_.-]+$",
      var.image,
    ))
    error_message = "image doit etre une reference taguee du Scaleway Container Registry."
  }
}

variable "google_drive_public_url" {
  description = "URL HTTPS du dossier Google Drive public contenant les EPUB"
  type        = string
  sensitive   = true

  validation {
    condition = can(regex(
      "^https://drive\\.google\\.com/drive/folders/[A-Za-z0-9_-]{20,}([?].*)?$",
      var.google_drive_public_url,
    ))
    error_message = "google_drive_public_url doit pointer vers un dossier public drive.google.com."
  }
}

variable "port" {
  description = "Port HTTP ecoute par myEbooks"
  type        = number
  default     = 8000
}

variable "min_scale" {
  description = "Nombre minimal d'instances, zero active le scale-to-zero"
  type        = number
  default     = 0

  validation {
    condition     = var.min_scale == 0
    error_message = "min_scale doit rester a 0 pour maitriser les couts."
  }
}

variable "max_scale" {
  description = "Nombre maximal d'instances"
  type        = number
  default     = 1

  validation {
    condition     = var.max_scale == 1
    error_message = "max_scale doit rester a 1 pour ce catalogue SQLite en lecture seule."
  }
}

variable "memory_limit_bytes" {
  description = "Memoire allouee au conteneur"
  type        = number
  default     = 268435456

  validation {
    condition     = contains([134217728, 268435456, 536870912], var.memory_limit_bytes)
    error_message = "La memoire doit valoir 128, 256 ou 512 Mio."
  }
}

variable "cpu_limit" {
  description = "Limite CPU en millicores, 140 correspond a 256 Mio"
  type        = number
  default     = 140
}
