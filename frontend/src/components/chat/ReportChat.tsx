/**
 * ReportChat - Interactive chat interface for discussing evaluation results.
 * 
 * "Ask Judex" - The AI assistant for understanding video safety evaluations.
 * 
 * Features:
 * - Initial report as first message
 * - Follow-up questions about the evaluation
 * - Suggested question chips
 * - Tool trace visibility (debug mode)
 */
import { FC, useState, useEffect, useRef, useCallback } from 'react'
import { Send, Loader2, Sparkles, RefreshCw, User, Diamond, ChevronRight } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { chat, ChatMessage, ChatResponse } from '@/api/client'

interface ReportChatProps {
  evaluationId: string
  onClose?: () => void
}

export const ReportChat: FC<ReportChatProps> = ({ evaluationId, onClose }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [threadId, setThreadId] = useState<string | null>(null)
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isInitializing, setIsInitializing] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showToolTrace, setShowToolTrace] = useState(false)
  const [lastToolTrace, setLastToolTrace] = useState<any>(null)
  
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Initialize chat thread
  useEffect(() => {
    const initChat = async () => {
      try {
        setIsInitializing(true)
        setError(null)
        
        const response = await chat.startThread(evaluationId)
        
        setThreadId(response.thread_id)
        setMessages(response.messages)
        setSuggestedQuestions(response.suggested_questions || [])
        
      } catch (err: any) {
        console.error('Failed to initialize chat:', err)
        setError(err.response?.data?.detail || 'Failed to start chat')
      } finally {
        setIsInitializing(false)
      }
    }
    
    initChat()
  }, [evaluationId])

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Send message
  const sendMessage = useCallback(async (message: string) => {
    if (!message.trim() || !threadId || isLoading) return
    
    // Add user message optimistically
    const userMessage: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMessage])
    setInputValue('')
    setIsLoading(true)
    setError(null)
    
    try {
      const response = await chat.sendMessage(evaluationId, threadId, message)
      
      // Replace temp message and add response
      setMessages(prev => {
        const filtered = prev.filter(m => !m.id.startsWith('temp-'))
        return [...filtered, ...response.messages]
      })
      
      if (response.tool_trace) {
        setLastToolTrace(response.tool_trace)
      }
      
    } catch (err: any) {
      console.error('Failed to send message:', err)
      setError(err.response?.data?.detail || 'Failed to send message')
      // Remove optimistic message on error
      setMessages(prev => prev.filter(m => !m.id.startsWith('temp-')))
    } finally {
      setIsLoading(false)
      inputRef.current?.focus()
    }
  }, [evaluationId, threadId, isLoading])

  // Handle suggested question click
  const handleSuggestedQuestion = (question: string) => {
    sendMessage(question)
  }

  // Handle form submit
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    sendMessage(inputValue)
  }

  // Refresh thread
  const handleRefresh = async () => {
    if (!threadId) return
    
    try {
      const response = await chat.getThread(evaluationId, threadId)
      setMessages(response.messages)
    } catch (err: any) {
      console.error('Failed to refresh thread:', err)
    }
  }

  return (
    <div className="flex flex-col h-full bg-black text-white">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800/50 flex-shrink-0 bg-black/50">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 flex items-center justify-center">
            <Diamond size={14} className="text-white" />
          </div>
          <span className="text-[11px] font-medium tracking-wide">ASK JUDEX</span>
          {threadId && (
            <span className="text-[9px] text-gray-600 font-mono">
              #{threadId}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={handleRefresh}
            className="p-1 hover:bg-gray-800/50 rounded text-gray-500 hover:text-white transition-colors"
            title="Refresh"
          >
            <RefreshCw size={12} />
          </button>
          <button
            onClick={() => setShowToolTrace(!showToolTrace)}
            className={`text-[9px] px-1.5 py-0.5 rounded transition-colors ${
              showToolTrace ? 'bg-white/10 text-white' : 'text-gray-600 hover:text-gray-400'
            }`}
          >
            DBG
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
        {isInitializing ? (
          <div className="flex flex-col items-center justify-center py-12">
            <Diamond size={24} className="text-white/20 mb-3 animate-pulse" />
            <span className="text-[11px] text-gray-500">Preparing analysis...</span>
          </div>
        ) : error && messages.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-red-400/80 text-[11px] mb-2">{error}</div>
            <button
              onClick={() => window.location.reload()}
              className="text-[10px] text-gray-500 hover:text-white underline"
            >
              Retry
            </button>
          </div>
        ) : (
          <>
            {messages.map((message, idx) => (
              <MessageBubble 
                key={message.id || idx} 
                message={message}
                showToolTrace={showToolTrace}
              />
            ))}
            
            {isLoading && (
              <div className="flex items-center gap-2 pl-8">
                <div className="flex items-center gap-1.5 text-gray-500">
                  <div className="w-1.5 h-1.5 bg-gray-600 rounded-full animate-pulse" />
                  <div className="w-1.5 h-1.5 bg-gray-600 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }} />
                  <div className="w-1.5 h-1.5 bg-gray-600 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }} />
                </div>
              </div>
            )}
            
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Suggested Questions */}
      {suggestedQuestions.length > 0 && messages.length <= 2 && !isLoading && (
        <div className="px-3 pb-2 flex-shrink-0">
          <div className="text-[9px] text-gray-600 uppercase tracking-widest mb-1.5 flex items-center gap-1">
            <Sparkles size={9} />
            Suggestions
          </div>
          <div className="flex flex-wrap gap-1.5">
            {suggestedQuestions.slice(0, 3).map((question, idx) => (
              <button
                key={idx}
                onClick={() => handleSuggestedQuestion(question)}
                disabled={isLoading}
                className="text-[10px] px-2 py-1 bg-gray-900 hover:bg-gray-800 border border-gray-800 hover:border-gray-700 text-gray-400 hover:text-white transition-all disabled:opacity-50 flex items-center gap-1"
              >
                <ChevronRight size={10} className="text-gray-600" />
                {question}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Tool Trace (Debug) */}
      {showToolTrace && lastToolTrace && (
        <div className="px-3 pb-2 flex-shrink-0">
          <div className="bg-gray-900/50 border border-gray-800/50 p-2 text-[9px] font-mono text-gray-600 max-h-20 overflow-y-auto">
            <div>Tools: {lastToolTrace.tools_called}</div>
            {lastToolTrace.steps?.map((step: any, idx: number) => (
              <div key={idx} className="text-gray-700 mt-0.5">
                → {step.node}: {step.intent || step.response_length || ''}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-3 border-t border-gray-800/50 flex-shrink-0 bg-black/50">
        {error && messages.length > 0 && (
          <div className="text-[10px] text-red-400/70 mb-2">{error}</div>
        )}
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Ask about this evaluation..."
            disabled={isLoading || isInitializing}
            className="flex-1 bg-gray-900/50 border border-gray-800 focus:border-gray-600 px-3 py-2 text-[11px] text-white placeholder-gray-600 focus:outline-none transition-colors disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!inputValue.trim() || isLoading || isInitializing}
            className="px-3 py-2 bg-white text-black hover:bg-gray-200 disabled:bg-gray-800 disabled:text-gray-600 transition-colors disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
          </button>
        </div>
      </form>
    </div>
  )
}

// Message Bubble Component
interface MessageBubbleProps {
  message: ChatMessage
  showToolTrace?: boolean
}

const MessageBubble: FC<MessageBubbleProps> = ({ message, showToolTrace }) => {
  const isUser = message.role === 'user'
  
  return (
    <div className={`flex gap-2.5 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div className={`w-6 h-6 flex items-center justify-center flex-shrink-0 ${
        isUser ? 'bg-white' : 'bg-transparent border border-gray-800'
      }`}>
        {isUser ? (
          <User size={12} className="text-black" />
        ) : (
          <Diamond size={10} className="text-gray-500" />
        )}
      </div>
      
      {/* Content */}
      <div className={`flex-1 max-w-[90%] ${isUser ? 'text-right' : ''}`}>
        <div className={`inline-block text-left ${
          isUser 
            ? 'bg-white text-black px-3 py-2' 
            : 'bg-transparent'
        }`}>
          {isUser ? (
            <p className="text-[11px]">{message.content}</p>
          ) : (
            <div className="prose prose-sm prose-invert max-w-none">
              <ReactMarkdown
                components={{
                  h1: ({children}) => <h1 className="text-sm font-semibold text-white mb-2 mt-0 pb-1 border-b border-gray-800/50">{children}</h1>,
                  h2: ({children}) => <h2 className="text-xs font-medium text-white mb-1.5 mt-3">{children}</h2>,
                  h3: ({children}) => <h3 className="text-[11px] font-medium text-gray-300 mb-1 mt-2">{children}</h3>,
                  p: ({children}) => <p className="text-[11px] text-gray-400 mb-2 leading-relaxed">{children}</p>,
                  ul: ({children}) => <ul className="text-[11px] text-gray-400 list-none ml-0 mb-2 space-y-0.5">{children}</ul>,
                  ol: ({children}) => <ol className="text-[11px] text-gray-400 list-decimal list-outside ml-4 mb-2 space-y-0.5">{children}</ol>,
                  li: ({children}) => <li className="text-gray-400 flex items-start gap-1.5"><span className="text-gray-600 mt-0.5">→</span><span>{children}</span></li>,
                  strong: ({children}) => <strong className="text-white font-medium">{children}</strong>,
                  em: ({children}) => <em className="text-gray-300 not-italic">{children}</em>,
                  code: ({children}) => <code className="text-[10px] bg-gray-900 px-1 py-0.5 text-gray-300 font-mono">{children}</code>,
                  blockquote: ({children}) => <blockquote className="border-l border-gray-700 pl-2 my-2 text-gray-500 text-[11px]">{children}</blockquote>,
                  hr: () => <hr className="border-gray-800/50 my-3" />,
                  table: ({children}) => <table className="w-full text-[10px] border-collapse my-2">{children}</table>,
                  thead: ({children}) => <thead className="border-b border-gray-800">{children}</thead>,
                  tbody: ({children}) => <tbody className="divide-y divide-gray-800/50">{children}</tbody>,
                  tr: ({children}) => <tr>{children}</tr>,
                  th: ({children}) => <th className="px-2 py-1 text-left text-gray-400 font-medium">{children}</th>,
                  td: ({children}) => <td className="px-2 py-1 text-gray-500">{children}</td>,
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          )}
        </div>
        
        {/* Timestamp */}
        <div className={`text-[9px] text-gray-700 mt-0.5 ${isUser ? 'text-right' : ''}`}>
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
        
        {/* Tool calls (debug) */}
        {showToolTrace && message.tool_calls && message.tool_calls.length > 0 && (
          <div className="mt-0.5 text-[9px] text-gray-700 font-mono">
            [{message.tool_calls.map(tc => tc.tool_name).join(', ')}]
          </div>
        )}
      </div>
    </div>
  )
}

export default ReportChat
