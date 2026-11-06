/* Generated from Python response models. Do not edit. */

export type IncidentId = string;
export type Action = "acknowledge" | "request_recovery_review";
export type OutboxId = string | null;

export interface ActionResult {
  incident_id: IncidentId;
  action: Action;
  outbox_id?: OutboxId;
}
