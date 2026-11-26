/**
 * Chat state, app-wide: conversations, the in-flight question, and the chat toggles.
 *
 * Lives above the router so an answer that is still loading is not lost when the user
 * switches to the Documents page and back. One question is in flight at a time, matching the
 * backend, which answers each question independently.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { ApiError, ask } from '../../api/client'
import { capabilities } from '../../config'
import { isStorageWritable, newId } from '../../lib/storage'
import {
  addConversation,
  appendMessage,
  createConversation,
  loadConversations,
  removeConversation,
  removeMessage,
  saveConversations,
} from './conversationStore'
import type { ChatMessage, Conversation } from './types'

interface Pending {
  conversationId: string
  question: string
}

interface ChatState {
  conversations: Conversation[]
  pending: Pending | null
  /** False when the browser refused to save history (private mode, storage full). */
  persisted: boolean
  externalSearch: boolean
  setExternalSearch: (value: boolean) => void
  showInternals: boolean
  setShowInternals: (value: boolean) => void
  /** Ask a question. Creates a conversation when `conversationId` is null. Returns its id. */
  send: (conversationId: string | null, question: string) => string | null
  retry: (conversationId: string, failedMessageId: string) => void
  stop: () => void
  deleteConversation: (conversationId: string) => void
  clearAll: () => void
}

const ChatContext = createContext<ChatState | null>(null)

const STOPPED_MESSAGE = 'You stopped this request, so no answer was generated.'

export function ChatProvider({ children }: { children: ReactNode }) {
  const [conversations, setConversations] = useState<Conversation[]>(loadConversations)
  const [pending, setPending] = useState<Pending | null>(null)
  const [persisted] = useState(isStorageWritable)
  // Defaults to OFF, as required; it can only be turned on when the backend supports it.
  const [externalSearch, setExternalSearchState] = useState(false)
  const [showInternals, setShowInternals] = useState(false)
  const controller = useRef<AbortController | null>(null)
  const pendingRef = useRef<Pending | null>(null)

  useEffect(() => {
    if (persisted && !saveConversations(conversations)) {
      console.warn('Could not save chat history (browser storage full or blocked).')
    }
  }, [conversations, persisted])

  useEffect(() => () => controller.current?.abort(), [])

  const setExternalSearch = useCallback((value: boolean) => {
    setExternalSearchState(capabilities.externalSearch ? value : false)
  }, [])

  const push = useCallback((conversationId: string, message: ChatMessage) => {
    setConversations((list) => appendMessage(list, conversationId, message))
  }, [])

  const run = useCallback(
    async (conversationId: string, question: string) => {
      const current = new AbortController()
      controller.current = current
      const job = { conversationId, question }
      pendingRef.current = job
      setPending(job)
      const external = capabilities.externalSearch && externalSearch
      try {
        const response = await ask({ question, debug: showInternals }, current.signal)
        push(conversationId, {
          id: newId(),
          role: 'assistant',
          createdAt: new Date().toISOString(),
          response,
          externalSearch: external,
        })
      } catch (err) {
        const text =
          err instanceof ApiError
            ? err.kind === 'aborted'
              ? STOPPED_MESSAGE
              : err.message
            : 'Something went wrong. Please try again.'
        push(conversationId, {
          id: newId(),
          role: 'failure',
          createdAt: new Date().toISOString(),
          text,
          question,
        })
      } finally {
        if (controller.current === current) controller.current = null
        pendingRef.current = null
        setPending(null)
      }
    },
    [externalSearch, showInternals, push],
  )

  const send = useCallback(
    (conversationId: string | null, question: string): string | null => {
      const text = question.trim()
      if (!text || pendingRef.current) return null
      const now = new Date().toISOString()
      let id = conversationId
      if (!id || !conversations.some((c) => c.id === id)) {
        const created = createConversation(newId(), text, now)
        id = created.id
        setConversations((list) => addConversation(list, created))
      }
      push(id, { id: newId(), role: 'user', text, createdAt: now })
      void run(id, text)
      return id
    },
    [conversations, push, run],
  )

  const retry = useCallback(
    (conversationId: string, failedMessageId: string) => {
      if (pendingRef.current) return
      const conversation = conversations.find((c) => c.id === conversationId)
      const failed = conversation?.messages.find((m) => m.id === failedMessageId)
      if (!failed || failed.role !== 'failure') return
      setConversations((list) => removeMessage(list, conversationId, failedMessageId))
      void run(conversationId, failed.question)
    },
    [conversations, run],
  )

  const stop = useCallback(() => controller.current?.abort(), [])

  const deleteConversation = useCallback((conversationId: string) => {
    if (pendingRef.current?.conversationId === conversationId) controller.current?.abort()
    setConversations((list) => removeConversation(list, conversationId))
  }, [])

  const clearAll = useCallback(() => {
    controller.current?.abort()
    setConversations([])
  }, [])

  const value = useMemo(
    () => ({
      conversations,
      pending,
      persisted,
      externalSearch,
      setExternalSearch,
      showInternals,
      setShowInternals,
      send,
      retry,
      stop,
      deleteConversation,
      clearAll,
    }),
    [
      conversations,
      pending,
      persisted,
      externalSearch,
      setExternalSearch,
      showInternals,
      send,
      retry,
      stop,
      deleteConversation,
      clearAll,
    ],
  )

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

// The hook belongs with its provider; fast refresh still works for the provider.
// eslint-disable-next-line react-refresh/only-export-components
export function useChat(): ChatState {
  const value = useContext(ChatContext)
  if (!value) throw new Error('useChat must be used inside <ChatProvider>')
  return value
}
