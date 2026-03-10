export type SchedulePreset = 'daily' | 'weekly' | 'monthly';
export type OpaSeverity = 'block' | 'warn';

export interface SummarySettings {
  repeatEnabled: boolean;
  intervalHours: number;
  lastRun: string;
}

export interface Schedule {
  id: number;
  title: string;
  preset: SchedulePreset;
  dayOfWeek?: number;
  dayOfMonth?: number;
  time: string;
  includeRange: boolean;
}

export type EventSettingsKey =
  | 'sh-malicious-network' | 'sh-unauthorized-access'
  | 'sh-anomalous-behavior' | 'sh-recon' | 'sh-exfiltration'
  | 'sh-external-access' | 'sh-unused-access'
  | 'sh-network' | 'sh-data-protection' | 'sh-iam'
  | 'sh-logging' | 'sh-compute' | 'sh-database'
  | 'sh-vulnerability'
  | 'ah-ec2-maint' | 'ah-rds-maint' | 'ah-other-maint'
  | 'ah-ec2-retire' | 'ah-ebs-issue' | 'ah-rds-hw'
  | 'ah-service-event' | 'ah-cert-expire'
  | 'ah-abuse';

export type EventSettings = Record<EventSettingsKey, boolean>;

export interface OpaParamsList {
  type: 'list';
  label: string;
  values: string[];
}

export interface OpaParamsServices {
  type: 'services';
  label: string;
  values: string[];
  options: string[];
}

export interface OpaParamsNumber {
  type: 'number';
  label: string;
  value: number;
  unit: string;
}

export type OpaParams = OpaParamsList | OpaParamsServices | OpaParamsNumber | null;

export interface OpaItem {
  key: string;
  label: string;
  on: boolean;
  severity: OpaSeverity;
  params: OpaParams;
  exceptions: string[];
}

export interface OpaCategory {
  category: string;
  items: OpaItem[];
}

export interface ReportSettings {
  summary: SummarySettings;
  schedules: Schedule[];
  eventSettings: EventSettings;
  opa: OpaCategory[];
}
