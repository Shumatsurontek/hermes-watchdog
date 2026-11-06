/* Generated from Python response models. Do not edit. */

export type Version = 1;
export type RootId = string;
export type Created = number;
export type Updated = number;
export type Deleted = boolean;
export type RouteAvailable = boolean;
export type Workers = number;
export type Active = number;
export type Waiting = number;
export type Returned = number;
export type Attention = number;
export type SessionId = string;
export type ParentId = string;
export type RootId1 = string;
export type Label = string;
export type LabelExcerpt = boolean;
export type State = "active" | "returned" | "failed" | "interrupted" | "unknown";
export type Waiting1 = boolean;
export type Updated1 = number;
export type Gap = string;
export type ObservedErrors = number;
export type LastTool = string;
export type EventCount = number;
export type RetainedFrom = number;
/**
 * @maxItems 50
 */
export type Workers1 = Worker[];
export type Id = string;
export type RootId2 = string;
export type Kind = "human_input" | "related_failures" | "worker_failed" | "worker_interrupted";
export type Status = "open" | "acknowledged" | "follow_up_requested" | "resolved" | "withdrawn" | "grouped";
export type Revision = number;
export type Updated2 = number;
export type RecoveryAvailable = boolean;
/**
 * @maxItems 1000
 */
export type MemberIds = string[];
/**
 * @maxItems 50
 */
export type Tools = string[];
export type Kind1 = "recovery" | "opening";
export type State1 = "pending" | "sending" | "accepted" | "failed" | "unknown" | "withdrawn";
export type Attempts = number;
/**
 * @maxItems 3
 */
export type Delivery = Delivery1[];
/**
 * @maxItems 50
 */
export type Incidents = Incident[];
export type IncidentCount = number;
/**
 * @maxItems 10
 */
export type Missions = Mission[];
export type NextCursor = number | null;
export type TotalMissions = number;

export interface WorkPage {
  version?: Version;
  missions: Missions;
  next_cursor: NextCursor;
  total_missions: TotalMissions;
  health: Health;
}
export interface Mission {
  root_id: RootId;
  created: Created;
  updated: Updated;
  deleted: Deleted;
  route_available: RouteAvailable;
  counts: Counts;
  workers: Workers1;
  incidents: Incidents;
  incident_count: IncidentCount;
}
export interface Counts {
  workers: Workers;
  active: Active;
  waiting: Waiting;
  returned: Returned;
  attention: Attention;
}
export interface Worker {
  session_id: SessionId;
  parent_id: ParentId;
  root_id: RootId1;
  label: Label;
  label_excerpt: LabelExcerpt;
  state: State;
  waiting: Waiting1;
  updated: Updated1;
  gap: Gap;
  observed_errors: ObservedErrors;
  last_tool: LastTool;
  event_count: EventCount;
  retained_from: RetainedFrom;
}
export interface Incident {
  id: Id;
  root_id: RootId2;
  kind: Kind;
  status: Status;
  revision: Revision;
  updated: Updated2;
  recovery_available: RecoveryAvailable;
  member_ids: MemberIds;
  tools: Tools;
  delivery: Delivery;
}
export interface Delivery1 {
  kind: Kind1;
  state: State1;
  attempts: Attempts;
}
export interface Health {
  [k: string]: string;
}
