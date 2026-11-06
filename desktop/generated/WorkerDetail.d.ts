/* Generated from Python response models. Do not edit. */

export type SessionId = string;
export type ParentId = string;
export type RootId = string;
export type Label = string;
export type LabelExcerpt = boolean;
export type State = "active" | "returned" | "failed" | "interrupted" | "unknown";
export type Waiting = boolean;
export type Updated = number;
export type Gap = string;
export type ObservedErrors = number;
export type LastTool = string;
export type EventCount = number;
export type RetainedFrom = number;
export type Seq = number;
export type At = number;
export type Kind = string;
export type Tool = string;
export type Status = string;
export type Outcome = string;
/**
 * @maxItems 64
 */
export type Evidence = Evidence1[];

export interface WorkerDetail {
  worker: Worker;
  evidence: Evidence;
}
export interface Worker {
  session_id: SessionId;
  parent_id: ParentId;
  root_id: RootId;
  label: Label;
  label_excerpt: LabelExcerpt;
  state: State;
  waiting: Waiting;
  updated: Updated;
  gap: Gap;
  observed_errors: ObservedErrors;
  last_tool: LastTool;
  event_count: EventCount;
  retained_from: RetainedFrom;
}
export interface Evidence1 {
  seq: Seq;
  at: At;
  kind: Kind;
  tool?: Tool;
  status?: Status;
  outcome?: Outcome;
}
