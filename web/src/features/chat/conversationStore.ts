/**
 * Pure functions over the conversation list, plus its localStorage persistence.
 *
 * The backend is stateless (each `/ask` is independent and nothing is stored server-side), so
 * history lives only in this browser. Kept pure so the reducer logic is unit-tested without
 * React.
 */
import { isAskResponse, normalizeAskResponse } from '../../api/guards'
import { readJson, writeJson } from '../../lib/storage'
import type { ChatMessage, Conversation } from './types'

export const STORAGE_KEY = 'prag.conversations.v1'
export const MAX_CONVERSATIONS = 50
export const MAX_MESSAGES = 200
const TITLE_LENGTH = 60

export function titleFrom(question: string): string {
  const flat = question.replace(/\s+/g, ' ').trim()
  return flat.length > TITLE_LENGTH ? `${flat.slice(0, TITLE_LENGTH - 1).trimEnd()}…` : flat
}

function isMessage(v: unknown): v is ChatMessage {
  if (typeof v !== 'object' || v === null) return false
  const m = v as Record<string, unknown>
  if (typeof m.id !== 'string' || typeof m.createdAt !== 'string') return false
  if (m.role === 'user') return typeof m.text === 'string'
  if (m.role === 'assistant') return isAskResponse(m.response) && typeof m.externalSearch === 'boolean'
  if (m.role === 'failure') return typeof m.text === 'string' && typeof m.question === 'string'
  return false
}

function isConversation(v: unknown): v is Conversation {
  if (typeof v !== 'object' || v === null) return false
  const c = v as Record<string, unknown>
  return (
    typeof c.id === 'string' &&
    typeof c.title === 'string' &&
    typeof c.createdAt === 'string' &&
    typeof c.updatedAt === 'string' &&
    Array.isArray(c.messages) &&
    c.messages.every(isMessage)
  )
}

function isConversationList(v: unknown): v is Conversation[] {
  return Array.isArray(v) && v.every(isConversation)
}

/** Fill fields older saved answers lack (for example `web_sources`). */
function normalizeMessage(m: ChatMessage): ChatMessage {
  return m.role === 'assistant' ? { ...m, response: normalizeAskResponse(m.response) } : m
}

/** Load saved conversations; anything malformed (old format, hand-edited) is ignored. */
export function loadConversations(): Conversation[] {
  const list = readJson(STORAGE_KEY, isConversationList) ?? []
  return list.map((c) => ({ ...c, messages: c.messages.map(normalizeMessage) }))
}

export function saveConversations(list: Conversation[]): boolean {
  return writeJson(STORAGE_KEY, list)
}

export function sortByRecent(list: Conversation[]): Conversation[] {
  return [...list].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
}

export function createConversation(id: string, firstQuestion: string, now: string): Conversation {
  return { id, title: titleFrom(firstQuestion), createdAt: now, updatedAt: now, messages: [] }
}

/** Insert a new conversation at the front, dropping the oldest beyond the cap. */
export function addConversation(list: Conversation[], conversation: Conversation): Conversation[] {
  return sortByRecent([conversation, ...list]).slice(0, MAX_CONVERSATIONS)
}

export function appendMessage(
  list: Conversation[],
  conversationId: string,
  message: ChatMessage,
): Conversation[] {
  return sortByRecent(
    list.map((c) =>
      c.id === conversationId
        ? { ...c, updatedAt: message.createdAt, messages: [...c.messages, message].slice(-MAX_MESSAGES) }
        : c,
    ),
  )
}

export function removeMessage(list: Conversation[], conversationId: string, messageId: string) {
  return list.map((c) =>
    c.id === conversationId ? { ...c, messages: c.messages.filter((m) => m.id !== messageId) } : c,
  )
}

export function removeConversation(list: Conversation[], conversationId: string): Conversation[] {
  return list.filter((c) => c.id !== conversationId)
}
