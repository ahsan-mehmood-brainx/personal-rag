import { describe, expect, it } from 'vitest'
import {
  addConversation,
  appendMessage,
  createConversation,
  loadConversations,
  MAX_CONVERSATIONS,
  removeConversation,
  saveConversations,
  STORAGE_KEY,
  titleFrom,
} from './conversationStore'
import { parseBlocks } from './parseAnswer'
import type { Conversation } from './types'

describe('parseBlocks', () => {
  it('splits paragraphs and keeps single line breaks inside a paragraph', () => {
    expect(parseBlocks('First line\nsecond line\n\nNext paragraph')).toEqual([
      { kind: 'paragraph', lines: ['First line', 'second line'] },
      { kind: 'paragraph', lines: ['Next paragraph'] },
    ])
  })

  it('recognises bullet and numbered lists, including a lead-in line', () => {
    expect(parseBlocks('Your roles:\n- Engineer\n* Lead\n\n1. Python\n2) Go')).toEqual([
      { kind: 'paragraph', lines: ['Your roles:'] },
      { kind: 'bullets', items: ['Engineer', 'Lead'] },
      { kind: 'numbered', items: ['Python', 'Go'] },
    ])
  })

  it('joins indented continuation lines onto the list item', () => {
    expect(parseBlocks('- Built a service\n  in Go')).toEqual([
      { kind: 'bullets', items: ['Built a service in Go'] },
    ])
  })
})

describe('conversation store', () => {
  const at = (minute: number) => `2026-11-25T10:${String(minute).padStart(2, '0')}:00.000Z`

  it('builds a trimmed single-line title', () => {
    expect(titleFrom('  Where   did\nI study?  ')).toBe('Where did I study?')
    const long = titleFrom('word '.repeat(40))
    expect(long.length).toBeLessThanOrEqual(60)
    expect(long.endsWith('…')).toBe(true)
  })

  it('keeps the most recently active conversation first', () => {
    let list: Conversation[] = []
    list = addConversation(list, createConversation('a', 'first', at(0)))
    list = addConversation(list, createConversation('b', 'second', at(1)))
    expect(list.map((c) => c.id)).toEqual(['b', 'a'])

    list = appendMessage(list, 'a', { id: 'm1', role: 'user', text: 'again', createdAt: at(2) })
    expect(list.map((c) => c.id)).toEqual(['a', 'b'])
    expect(list[0]?.messages).toHaveLength(1)
  })

  it('caps the number of stored conversations', () => {
    let list: Conversation[] = []
    for (let i = 0; i < MAX_CONVERSATIONS + 5; i++) {
      list = addConversation(list, createConversation(`c${i}`, 'q', new Date(Date.UTC(2026, 0, 1, 0, i)).toISOString()))
    }
    expect(list).toHaveLength(MAX_CONVERSATIONS)
    expect(list[0]?.id).toBe(`c${MAX_CONVERSATIONS + 4}`)
  })

  it('appending to a deleted conversation is a no-op', () => {
    const list = removeConversation([createConversation('a', 'q', at(0))], 'a')
    expect(appendMessage(list, 'a', { id: 'm', role: 'user', text: 'x', createdAt: at(1) })).toEqual([])
  })

  it('round-trips through localStorage and ignores malformed data', () => {
    const conversation = createConversation('a', 'q', at(0))
    conversation.messages.push({
      id: 'm',
      role: 'assistant',
      createdAt: at(1),
      externalSearch: false,
      response: { status: 'meta', answer: 'Hi', sources: [], web_sources: [], debug: null },
    })
    saveConversations([conversation])
    expect(loadConversations()).toEqual([conversation])

    // Answers saved before web search existed have no `web_sources`; they still load.
    const legacy = JSON.parse(JSON.stringify([conversation])) as Array<{
      messages: Array<{ response: Record<string, unknown> }>
    }>
    delete legacy[0]?.messages[0]?.response.web_sources
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(legacy))
    expect(loadConversations()).toEqual([conversation])

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([{ id: 'x', messages: 'nope' }]))
    expect(loadConversations()).toEqual([])
    window.localStorage.setItem(STORAGE_KEY, '{not json')
    expect(loadConversations()).toEqual([])
  })
})
