import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { installFakeBackend } from '../../test/fakeBackend'
import { renderApp } from '../../test/renderApp'

const DOC = { doc_id: 'd1', filename: 'cv.md', chunk_count: 3, ingested_at: '2026-11-25T10:00:00Z' }

afterEach(() => vi.unstubAllGlobals())

describe('ChatPage', () => {
  it('has a single toggle, external search, which starts OFF and is sent with each question', async () => {
    const backend = installFakeBackend({ documents: [DOC] })
    const { user } = renderApp()

    expect(screen.getAllByRole('switch')).toHaveLength(1)
    expect(screen.queryByRole('switch', { name: 'Show internals' })).not.toBeInTheDocument()
    const toggle = screen.getByRole('switch', { name: 'Allow External Search' })
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(toggle).toBeEnabled()

    await user.type(screen.getByLabelText('Your question'), 'Where did I study?{Enter}')
    await screen.findByText('An answer.')

    // Turned on after the first question, in the same conversation.
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-checked', 'true')
    await user.type(screen.getByLabelText('Your question'), 'What is Kubernetes?{Enter}')
    await screen.findAllByText('An answer.')

    // And off again.
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    await user.type(screen.getByLabelText('Your question'), 'What is Docker?{Enter}')
    await screen.findAllByText('An answer.')

    const asks = backend.requests.filter((r) => r.path === '/ask').map((r) => r.body)
    expect(asks).toEqual([
      { question: 'Where did I study?', debug: false, allow_external_search: false },
      { question: 'What is Kubernetes?', debug: false, allow_external_search: true },
      { question: 'What is Docker?', debug: false, allow_external_search: false },
    ])
  })

  it('renders a web answer with a badge and safe web source links', async () => {
    installFakeBackend({
      documents: [DOC],
      askResponse: {
        status: 'web_answered',
        answer: 'Kubernetes orchestrates containers.',
        sources: [],
        web_sources: [
          { title: 'Kubernetes docs', url: 'https://kubernetes.io/docs/' },
          { title: 'Kubernetes docs again', url: 'https://KUBERNETES.io/docs/' },
          { title: 'Bad', url: 'javascript:alert(1)' },
        ],
        debug: null,
      },
    })
    const { user } = renderApp()
    await user.click(screen.getByRole('switch', { name: 'Allow External Search' }))
    await user.type(screen.getByLabelText('Your question'), 'What is Kubernetes?{Enter}')

    const answer = await screen.findByRole('article', { name: 'Assistant: From the web' })
    expect(within(answer).getByText('Web sources (1)')).toBeInTheDocument()
    const link = within(answer).getByRole('link', { name: 'Kubernetes docs', hidden: true })
    expect(link).toHaveAttribute('href', 'https://kubernetes.io/docs/')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(within(answer).queryByText('Bad')).not.toBeInTheDocument()
    expect(within(answer).queryByTestId('external-search-notice')).not.toBeInTheDocument()
  })

  it('explains that external search is off when a question is out of scope', async () => {
    installFakeBackend({
      documents: [DOC],
      askResponse: { status: 'out_of_scope', answer: 'I can only help with…', sources: [], web_sources: [], debug: null },
    })
    const { user } = renderApp()
    await user.type(screen.getByLabelText('Your question'), 'What is Kubernetes?{Enter}')

    const answer = await screen.findByRole('article', { name: 'Assistant: Out of scope' })
    expect(within(answer).getByTestId('external-search-notice')).toHaveTextContent(
      'External search is off',
    )
  })

  it('does not show the notice for other statuses', async () => {
    installFakeBackend({
      documents: [DOC],
      askResponse: { status: 'not_found', answer: "I couldn't find that…", sources: [], web_sources: [], debug: null },
    })
    const { user } = renderApp()
    await user.type(screen.getByLabelText('Your question'), 'What is my salary?{Enter}')
    await screen.findByRole('article', { name: 'Assistant: Not in your documents' })
    expect(screen.queryByTestId('external-search-notice')).not.toBeInTheDocument()
  })

  it('Shift+Enter adds a line instead of sending; empty input cannot be sent', async () => {
    const backend = installFakeBackend({ documents: [DOC] })
    const { user } = renderApp()
    const box = screen.getByLabelText('Your question')
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()

    await user.type(box, 'line one{Shift>}{Enter}{/Shift}line two')
    expect(box).toHaveValue('line one\nline two')
    expect(backend.requests.some((r) => r.path === '/ask')).toBe(false)
  })

  it('prompts to upload documents when the knowledge base is empty', async () => {
    installFakeBackend({ documents: [] })
    renderApp()
    expect(await screen.findByText('No documents yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Upload documents' })).toHaveAttribute('href', '/documents')
  })
})
