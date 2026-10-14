locals {
  topics = [
    "agentos-workflow-events",
    "agentos-scheduler-triggers",
    "agentos-mcp-validation",
    "agentos-recovery-events"
  ]
}

resource "google_pubsub_topic" "topics" {
  for_each = toset(local.topics)
  name     = each.key
  project  = var.project_id
}

# Pull subscriptions consumed by backend.worker through Pub/Sub StreamingPull.
resource "google_pubsub_subscription" "worker_pull_subs" {
  for_each = toset(local.topics)
  name     = "${each.key}-worker-sub"
  project  = var.project_id
  topic    = google_pubsub_topic.topics[each.key].name

  ack_deadline_seconds = 600 # 10 minutes

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}
