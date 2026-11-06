/* Generated from Python response models. Do not edit. */

export type Id = string;
export type SessionKey = string;
export type ParentId = string;
export type Revision = number;
export type Goal = string;
export type Execution = string;
export type Supervision = string;
export type Notification = string;
export type Created = number;
export type CanCancel = boolean;
export type CancelPending = boolean;
export type Result = string | null;
export type ResultExcerpt = boolean;
export type RetryReason = string;
export type Seq = number;
export type At = number;
export type Kind = string;
export type Tool = string;
export type Status = string;
export type Outcome = string;
/**
 * @maxItems 64
 */
export type Observations = Evidence[];
export type Id1 = number;
export type Kind1 = string;
export type Status1 = string;
export type Created1 = number;
/**
 * @maxItems 128
 */
export type Events = HistoryEvent[];
/**
 * @maxItems 50
 */
export type Tasks = HistoryTask[];
export type NextCursor = string | null;

export interface HistoryPage {
  tasks: Tasks;
  next_cursor: NextCursor;
}
export interface HistoryTask {
  id: Id;
  session_key: SessionKey;
  parent_id: ParentId;
  revision: Revision;
  goal: Goal;
  execution: Execution;
  supervision: Supervision;
  notification: Notification;
  created: Created;
  can_cancel: CanCancel;
  cancel_pending: CancelPending;
  result: Result;
  result_excerpt: ResultExcerpt;
  retry_reason: RetryReason;
  observations: Observations;
  events: Events;
}
export interface Evidence {
  seq: Seq;
  at: At;
  kind: Kind;
  tool?: Tool;
  status?: Status;
  outcome?: Outcome;
}
export interface HistoryEvent {
  id: Id1;
  kind: Kind1;
  status: Status1;
  created: Created1;
}
