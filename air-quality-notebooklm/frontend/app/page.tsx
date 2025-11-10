'use client'

import { useState } from 'react'
import ChatInterface from '@/components/ChatInterface'
import DataInspector from '@/components/DataInspector'
import { FileText, Database } from 'lucide-react'

export default function Home() {
  const [showInspector, setShowInspector] = useState(false)
  const [inspectorData, setInspectorData] = useState<any>(null)

  return (
    <main className="flex min-h-screen flex-col bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Database className="w-6 h-6 text-blue-600" />
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              Air Quality NotebookLM
            </h1>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              Bakersfield, CA
            </span>
          </div>

          <button
            onClick={() => setShowInspector(!showInspector)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
          >
            <FileText className="w-4 h-4" />
            {showInspector ? 'Hide' : 'Show'} Inspector
          </button>
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 max-w-7xl w-full mx-auto">
        {/* Chat interface */}
        <div className={`flex-1 ${showInspector ? 'border-r border-gray-200 dark:border-gray-700' : ''}`}>
          <ChatInterface
            onToolCall={(data) => {
              setInspectorData(data)
              setShowInspector(true)
            }}
          />
        </div>

        {/* Data inspector (collapsible) */}
        {showInspector && (
          <div className="w-96 bg-white dark:bg-gray-800">
            <DataInspector data={inspectorData} />
          </div>
        )}
      </div>
    </main>
  )
}
