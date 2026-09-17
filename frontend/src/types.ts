export type UserRole = 'admin' | 'operator'
export type MenuKey = 'workspace' | 'runs' | 'schedules' | 'feature_admin' | 'users' | 'customers' | 'audit' | 'settings'

export interface UserSummary {
  id: string
  username: string
  displayName: string
  role: UserRole
  isActive?: boolean
  mustChangePassword: boolean
  customerIds?: string[]
  menuKeys?: MenuKey[]
  createdAt?: number
  lastLoginAt?: number | null
}

export interface Customer {
  id: string
  name: string
  description: string
  isActive: boolean
  createdAt: number
  updatedAt: number
}

export interface SessionPayload {
  user: UserSummary
  customers: Customer[]
  csrfToken: string
}

export interface AuditLog {
  id: number
  occurredAt: number
  actorUserId: string | null
  actorDisplayName: string | null
  actorUsername: string | null
  actorRole: UserRole | null
  action: string
  outcome: string
  targetType: string | null
  targetId: string | null
  targetName: string | null
  customerId: string | null
  customerName: string | null
  clientIp: string
  requestMethod: string | null
  requestPath: string | null
  requestId: string | null
  userAgent: string | null
  details: Record<string, unknown>
}

export type FeatureStatus = 'PREPARING' | 'ACTIVE' | 'WAITING_DATA_SOURCE' | 'DEPENDENCY_FAILED' | 'DISABLED'

export interface DataSourceInfo {
  id: string
  revisionNumber: number
  sourceKind: 'DEFAULT' | 'UPLOAD'
  sourceVersionId: string | null
  filename: string
  size: number
  sha256: string
  createdAt: number
}

export interface CustomerFeature {
  id: string
  customerId: string
  customerName: string
  definitionId: string
  versionId: string
  versionNumber: number
  name: string
  description: string
  isEnabled: boolean
  status: FeatureStatus
  maxRuntimeSeconds: number | null
  configurationComplete: boolean
  dataSourceSchema: { filename: string; required: boolean; extensions: string[]; description: string } | null
  dataSource: DataSourceInfo | null
  updatedAt: number
}

export interface FeatureVersion {
  id: string
  definitionId: string
  versionNumber: number
  name: string
  description: string
  status: 'PREPARING' | 'READY' | 'DEPENDENCY_FAILED'
  prepareError: string | null
  packageFilename: string
  packageSize: number
  packageSha256: string
  sourceEncoding: string
  requirements: string[]
  warnings: string[]
  configSchema: Record<string, Record<string, unknown>>
  dataSourceSchema: Record<string, unknown> | null
  reportSchema: RunReportSchema | null
  defaultDataSource: { filename: string; size: number; sha256: string } | null
  environment: { id: string; status: string; requestFingerprint: string; resolvedFingerprint: string | null; failure: string | null } | null
  createdAt: number
}

export interface FeatureDefinition {
  id: string
  name: string
  createdAt: number
  versions: FeatureVersion[]
}

export type RunStatus = 'QUEUED' | 'STARTING' | 'RUNNING' | 'STOPPING' | 'SUCCEEDED' | 'FAILED' | 'STOPPED' | 'TIMED_OUT' | 'INTERRUPTED'
export type RunReportStatus = 'OPEN' | 'COMPLETE' | 'INCOMPLETE'
export type RunReportItemStatus = 'SUCCESS' | 'FAILED' | 'NO_DATA' | 'SKIPPED' | 'UNFINISHED'

export interface RunReportColumn {
  key: string
  label: string
  type: 'string' | 'integer' | 'number' | 'boolean'
}

export interface RunReportSchema {
  title: string
  item_label: string
  columns: RunReportColumn[]
}

export interface RunReportSummary {
  title: string
  itemLabel: string
  columns: RunReportColumn[]
  status: RunReportStatus
  expectedTotal: number | null
  reportedTotal: number
  total: number
  successCount: number
  failedCount: number
  noDataCount: number
  skippedCount: number
  unfinishedCount: number
  unreportedCount: number
  validationErrorCount: number
  startedAt: number
  completedAt: number | null
  detailsPurgedAt: number | null
}

export interface RunReportItem {
  sequence: number
  status: RunReportItemStatus
  reason: string
  values: Record<string, string | number | boolean | null>
  reportedAtMs: number
}

export interface RunSummary {
  requestId: string
  customerId: string
  customerName: string
  customerFeatureId: string
  featureVersionId: string
  featureName: string
  versionNumber: number
  dataSourceRevisionId: string | null
  dataSourceFilename: string | null
  triggerSource: 'MANUAL' | 'SCHEDULED'
  status: RunStatus
  queuedAt: number
  claimedAt: number | null
  startedAt: number | null
  stopRequestedAt: number | null
  finishedAt: number | null
  exitCode: number | null
  failureSummary: string | null
  stopReason: string | null
  maxRuntimeSeconds: number | null
  latestSequence: number
  finalSequence: number | null
  logsPurgedAt: number | null
  report: RunReportSummary | null
}

export interface RunEvent {
  requestId: string
  sequence: number
  occurredAtMs: number
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'
  source: 'PLATFORM' | 'SDK' | 'STDOUT' | 'STDERR'
  message: string
  context: Record<string, unknown>
}

export type ScheduleOutcome =
  | 'ENQUEUED'
  | 'MISSED'
  | 'SKIPPED_ACTIVE'
  | 'SKIPPED_UNAVAILABLE'
  | 'QUEUE_FULL'
  | 'DUPLICATE'

export interface Schedule {
  id: string
  customerId: string
  customerName: string
  customerFeatureId: string
  featureName: string
  featureStatus: FeatureStatus | 'MISSING'
  name: string
  cronExpression: string
  timezone: string
  isEnabled: boolean
  nextRunAt: number | null
  lastScheduledFor: number | null
  lastHandledAt: number | null
  lastRunRequestId: string | null
  lastOutcome: ScheduleOutcome | null
  lastMessage: string | null
  missedCount: number
  createdAt: number
  updatedAt: number
}

export interface Pagination {
  page: number
  pageSize: number
  total: number
  totalPages: number
}

export interface Paginated<T> {
  items: T[]
  pagination: Pagination
}
