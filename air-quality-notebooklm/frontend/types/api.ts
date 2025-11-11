/**
 * TypeScript types for Air Quality NotebookLM API
 * These types correspond to the backend Pydantic models
 */

// Tool call types
export interface ToolInput {
  [key: string]: string | number | boolean | null | undefined
}

export interface ToolResult {
  success: boolean
  result?: ResultData
  error?: string
}

export interface ToolCall {
  tool: string
  params: ToolInput
  result?: ToolResult
}

// Result data types for different tools
export interface MetricSummaryResult {
  metric: string
  aggregate: string
  value: number
  unit: string
  n_samples: number
  qa_flags?: number
}

export interface CorrelationResult {
  correlation: number
  p_value: number
  n_samples: number
  controlled_for?: string[]
}

export interface Exceedance {
  period: string
  avg_pm25: number
  max_pm25: number
  duration_hours: number
}

export interface ExceedancesResult {
  exceedances: Exceedance[]
  total: number
}

export interface Spike {
  ts: string
  pm25: number
  change_rate: number
}

export interface SpikesResult {
  spikes: Spike[]
  total: number
}

export interface Inversion {
  start_ts: string
  end_ts: string
  duration_hours: number
  confidence: string
  evidence: string[]
}

export interface InversionsResult {
  inversions: Inversion[]
  total: number
}

export type ResultData =
  | MetricSummaryResult
  | CorrelationResult
  | ExceedancesResult
  | SpikesResult
  | InversionsResult
  | Record<string, unknown>

// Message types
export interface Answer {
  text: string
  confidence?: number
  sources?: string[]
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  toolCalls?: ToolCall[]
  timestamp: Date
}

// API request/response types
export interface QueryRequest {
  question: string
  location: string
}

export interface QueryResponse {
  answer: Answer
  tool_calls: ToolCall[]
  rounds: number
  model: string
}

// Error response type
export interface ErrorResponse {
  error?: string
  detail?: string  // FastAPI uses 'detail' for HTTP exceptions
  details?: unknown
  type?: string
}

// Type guards for result data
export function isMetricSummaryResult(result: unknown): result is MetricSummaryResult {
  return (
    typeof result === 'object' &&
    result !== null &&
    'metric' in result &&
    'value' in result &&
    'unit' in result
  )
}

export function isExceedancesResult(result: unknown): result is ExceedancesResult {
  return (
    typeof result === 'object' &&
    result !== null &&
    'exceedances' in result &&
    Array.isArray((result as ExceedancesResult).exceedances)
  )
}

export function isSpikesResult(result: unknown): result is SpikesResult {
  return (
    typeof result === 'object' &&
    result !== null &&
    'spikes' in result &&
    Array.isArray((result as SpikesResult).spikes)
  )
}

export function isInversionsResult(result: unknown): result is InversionsResult {
  return (
    typeof result === 'object' &&
    result !== null &&
    'inversions' in result &&
    Array.isArray((result as InversionsResult).inversions)
  )
}

export function isCorrelationResult(result: unknown): result is CorrelationResult {
  return (
    typeof result === 'object' &&
    result !== null &&
    'correlation' in result &&
    'p_value' in result
  )
}
