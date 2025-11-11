'use client'

import { useState, useRef, useEffect } from 'react'
import { Send, AlertCircle } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import axios, { AxiosError } from 'axios'
import { Message, ToolCall, QueryResponse, ErrorResponse } from '@/types/api'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface ChatInterfaceProps {
  onToolCall: (data: ToolCall[]) => void
}

export default function ChatInterface({ onToolCall }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!input.trim() || isLoading) return

    const userMessage: Message = {
      role: 'user',
      content: input.trim(),
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsLoading(true)
    setError(null)

    try {
      const response = await axios.post<QueryResponse>(`${API_URL}/query`, {
        question: userMessage.content,
        location: 'bakersfield'
      })

      const { answer, tool_calls } = response.data

      // Show tool calls in inspector
      if (tool_calls && tool_calls.length > 0) {
        onToolCall(tool_calls)
      }

      const assistantMessage: Message = {
        role: 'assistant',
        content: answer.text || 'No response generated',
        toolCalls: tool_calls,
        timestamp: new Date()
      }

      setMessages(prev => [...prev, assistantMessage])

    } catch (err) {
      const axiosError = err as AxiosError<ErrorResponse>
      const errorMessage =
        axiosError.response?.data?.error ||
        axiosError.response?.data?.detail ||
        axiosError.message ||
        'Failed to get response'
      setError(errorMessage)
      console.error('Query error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-12">
            <h2 className="text-2xl font-semibold text-gray-900 dark:text-white mb-4">
              Welcome to Air Quality NotebookLM
            </h2>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              Ask questions about air quality data, weather patterns, and research insights.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-2xl mx-auto">
              <button
                onClick={() => setInput("What was the max PM2.5 yesterday?")}
                className="p-4 text-left bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-blue-500 transition-colors"
              >
                <div className="font-medium text-gray-900 dark:text-white">
                  Recent measurements
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  What was the max PM2.5 yesterday?
                </div>
              </button>
              <button
                onClick={() => setInput("Is there a correlation between wind speed and PM2.5?")}
                className="p-4 text-left bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-blue-500 transition-colors"
              >
                <div className="font-medium text-gray-900 dark:text-white">
                  Find correlations
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  Is there a correlation between wind speed and PM2.5?
                </div>
              </button>
              <button
                onClick={() => setInput("Detect any inversions in the past week")}
                className="p-4 text-left bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-blue-500 transition-colors"
              >
                <div className="font-medium text-gray-900 dark:text-white">
                  Inversion detection
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  Detect any inversions in the past week
                </div>
              </button>
              <button
                onClick={() => setInput("How many EPA exceedances this month?")}
                className="p-4 text-left bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-blue-500 transition-colors"
              >
                <div className="font-medium text-gray-900 dark:text-white">
                  EPA standards
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  How many EPA exceedances this month?
                </div>
              </button>
            </div>
          </div>
        )}

        {messages.map((message, index) => (
          <div
            key={index}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-3xl px-4 py-3 rounded-lg ${
                message.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700'
              }`}
            >
              {message.role === 'assistant' ? (
                <div className="prose dark:prose-invert">
                  <ReactMarkdown>{message.content}</ReactMarkdown>
                </div>
              ) : (
                <div>{message.content}</div>
              )}

              <div className="text-xs opacity-70 mt-2">
                {message.timestamp.toLocaleTimeString()}
              </div>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 px-4 py-3 rounded-lg">
              <div className="flex items-center gap-2">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                <span className="text-gray-600 dark:text-gray-400">Analyzing data...</span>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="flex justify-center">
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 rounded-lg flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400" />
              <span className="text-red-800 dark:text-red-300">{error}</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-gray-200 dark:border-gray-700 p-4 bg-white dark:bg-gray-800">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about air quality data..."
            className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-lg transition-colors flex items-center gap-2"
          >
            <Send className="w-4 h-4" />
            Send
          </button>
        </form>
      </div>
    </div>
  )
}
