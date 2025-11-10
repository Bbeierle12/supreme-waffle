'use client'

import { useState } from 'react'
import { ChevronDown, ChevronRight, AlertTriangle, CheckCircle } from 'lucide-react'

interface DataInspectorProps {
  data: any
}

export default function DataInspector({ data }: DataInspectorProps) {
  const [expandedTools, setExpandedTools] = useState<Set<number>>(new Set([0]))

  const toggleTool = (index: number) => {
    const newExpanded = new Set(expandedTools)
    if (newExpanded.has(index)) {
      newExpanded.delete(index)
    } else {
      newExpanded.add(index)
    }
    setExpandedTools(newExpanded)
  }

  if (!data || data.length === 0) {
    return (
      <div className="h-full p-6">
        <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
          Data Inspector
        </h3>
        <p className="text-gray-600 dark:text-gray-400">
          Tool calls and data sources will appear here.
        </p>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
        Data Inspector
      </h3>

      <div className="space-y-3">
        {data.map((toolCall: any, index: number) => {
          const isExpanded = expandedTools.has(index)
          const success = toolCall.result?.success !== false
          const result = toolCall.result?.result || toolCall.result

          return (
            <div
              key={index}
              className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden"
            >
              {/* Tool header */}
              <button
                onClick={() => toggleTool(index)}
                className="w-full flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-750 transition-colors"
              >
                <div className="flex items-center gap-2">
                  {isExpanded ? (
                    <ChevronDown className="w-4 h-4" />
                  ) : (
                    <ChevronRight className="w-4 h-4" />
                  )}
                  <span className="font-mono text-sm font-medium">
                    {toolCall.tool}
                  </span>
                  {success ? (
                    <CheckCircle className="w-4 h-4 text-green-600" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 text-red-600" />
                  )}
                </div>
              </button>

              {/* Tool details */}
              {isExpanded && (
                <div className="p-3 space-y-3">
                  {/* Parameters */}
                  <div>
                    <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">
                      PARAMETERS
                    </div>
                    <div className="bg-gray-50 dark:bg-gray-900 rounded p-2 text-xs font-mono">
                      <pre className="whitespace-pre-wrap">
                        {JSON.stringify(toolCall.params, null, 2)}
                      </pre>
                    </div>
                  </div>

                  {/* Results */}
                  <div>
                    <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">
                      RESULT
                    </div>
                    {success ? (
                      <div className="space-y-2">
                        {renderResult(result)}
                      </div>
                    ) : (
                      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-2 text-sm text-red-800 dark:text-red-300">
                        {toolCall.result?.error || 'Unknown error'}
                      </div>
                    )}
                  </div>

                  {/* QA Flags */}
                  {result?.qa_flags && result.qa_flags > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">
                        QA FLAGS
                      </div>
                      <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded p-2">
                        <QAFlagsDisplay flags={result.qa_flags} />
                      </div>
                    </div>
                  )}

                  {/* Raw JSON */}
                  <details className="text-xs">
                    <summary className="cursor-pointer text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
                      View raw JSON
                    </summary>
                    <div className="mt-2 bg-gray-50 dark:bg-gray-900 rounded p-2 font-mono overflow-x-auto">
                      <pre className="whitespace-pre-wrap">
                        {JSON.stringify(result, null, 2)}
                      </pre>
                    </div>
                  </details>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function renderResult(result: any) {
  if (!result) return null

  // Handle different result types
  if (result.value !== undefined) {
    // Metric summary
    return (
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded p-3">
        <div className="text-2xl font-bold text-blue-900 dark:text-blue-100">
          {result.value?.toFixed(1)} {result.unit}
        </div>
        <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          {result.metric} ({result.aggregate})
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-500 mt-1">
          n = {result.n_samples} samples
        </div>
      </div>
    )
  }

  if (result.exceedances) {
    // Exceedances
    return (
      <div>
        <div className="font-medium mb-2">
          {result.total_count} exceedances found
        </div>
        <div className="space-y-2">
          {result.exceedances.slice(0, 5).map((exc: any, i: number) => (
            <div
              key={i}
              className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-2 text-sm"
            >
              <div className="font-medium">{exc.period}</div>
              <div className="text-gray-600 dark:text-gray-400">
                Avg: {exc.avg_pm25.toFixed(1)} µg/m³ (Max: {exc.max_pm25.toFixed(1)})
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (result.spikes) {
    // Spikes
    return (
      <div>
        <div className="font-medium mb-2">
          {result.total_count} spikes detected ({result.method})
        </div>
        <div className="space-y-2">
          {result.spikes.slice(0, 5).map((spike: any, i: number) => (
            <div
              key={i}
              className="bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 rounded p-2 text-sm"
            >
              <div className="font-medium">{spike.timestamp}</div>
              <div className="text-gray-600 dark:text-gray-400">
                Value: {spike.value.toFixed(1)} (z-score: {spike.z_score.toFixed(2)})
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (result.correlation !== undefined) {
    // Correlation
    return (
      <div className="bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800 rounded p-3">
        <div className="text-2xl font-bold text-purple-900 dark:text-purple-100">
          r = {result.correlation.toFixed(3)}
        </div>
        <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          p-value: {result.p_value?.toFixed(4) || 'N/A'}
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-500 mt-1">
          n = {result.n_samples} samples
        </div>
        {result.controlled_for && result.controlled_for.length > 0 && (
          <div className="text-xs text-gray-500 dark:text-gray-500 mt-1">
            Controlled for: {result.controlled_for.join(', ')}
          </div>
        )}
      </div>
    )
  }

  if (result.inversions) {
    // Inversions
    return (
      <div>
        <div className="font-medium mb-2">
          {result.total_count} inversion periods detected
        </div>
        <div className="text-xs text-yellow-700 dark:text-yellow-400 mb-2">
          ⚠️ {result.caveat}
        </div>
        <div className="space-y-2">
          {result.inversions.map((inv: any, i: number) => (
            <div
              key={i}
              className="bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800 rounded p-2 text-sm"
            >
              <div className="font-medium">{inv.date}</div>
              <div className="text-gray-600 dark:text-gray-400">
                Confidence: {(inv.confidence * 100).toFixed(0)}%
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  // Default: show raw data
  return (
    <div className="bg-gray-50 dark:bg-gray-900 rounded p-2 text-xs font-mono">
      <pre className="whitespace-pre-wrap">
        {JSON.stringify(result, null, 2)}
      </pre>
    </div>
  )
}

function QAFlagsDisplay({ flags }: { flags: number }) {
  const flagDescriptions = []

  if (flags & 0x01) flagDescriptions.push('A/B channel disagreement')
  if (flags & 0x02) flagDescriptions.push('High humidity (>85%)')
  if (flags & 0x04) flagDescriptions.push('Statistical outlier')
  if (flags & 0x08) flagDescriptions.push('Stale data (>2 hours)')
  if (flags & 0x10) flagDescriptions.push('Sensor offline')
  if (flags & 0x20) flagDescriptions.push('Maintenance period')

  if (flagDescriptions.length === 0) {
    return <div className="text-sm text-green-700 dark:text-green-400">No issues</div>
  }

  return (
    <ul className="text-sm text-yellow-700 dark:text-yellow-400 space-y-1">
      {flagDescriptions.map((desc, i) => (
        <li key={i}>⚠️ {desc}</li>
      ))}
    </ul>
  )
}
