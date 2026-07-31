output "container_url" {
  description = "URL HTTPS publique du catalogue"
  value       = scaleway_container.this.public_endpoint
}

output "container_id" {
  description = "Identifiant regional du Serverless Container"
  value       = scaleway_container.this.id
}

output "registry_endpoint" {
  description = "Endpoint complet du namespace Scaleway Container Registry"
  value       = scaleway_registry_namespace.this.endpoint
}

output "resource_name" {
  description = "Nom commun des ressources Scaleway"
  value       = local.resource_name
}
