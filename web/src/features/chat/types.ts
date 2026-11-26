import type { AskResponse } from '../../api/types'

export interface UserMessage {
  id: string
  role: 'user'
  text: string
  createdAt: string
}

export interface AssistantMessage {
  id: string
  role: 'assistant'
  createdAt: string
  response: AskResponse
  /** Toggle value sent with the question, so the notice under a refusal stays accurate. */
  externalSearch: boolean
}

/** The request itself failed (network, timeout, 4xx). Kept in history so it can be retried. */
export interface FailedMessage {
  id: string
  role: 'failure'
  createdAt: string
  text: string
  question: string
}

export type ChatMessage = UserMessage | AssistantMessage | FailedMessage

export interface Conversation {
  id: string
  title: string
  createdAt: string
  updatedAt: string
  messages: ChatMessage[]
}
