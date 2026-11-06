/* Generated from Python response models. Do not edit. */

export type TaskId = string;
export type Action = "cancel_queued";

export interface CancelResult {
  task_id: TaskId;
  action: Action;
}
