import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { installFakeBackend } from '../../test/fakeBackend'
import { renderApp } from '../../test/renderApp'

const DOC = { doc_id: 'd1', filename: 'cv.md', chunk_count: 3, ingested_at: '2026-11-25T10:00:00Z' }

afterEach(() => vi.unstubAllGlobals())

describe('ChatPage', () => {
  it('shows the external search toggle OFF and locked, and never sends it to the backend', async () => {
    const backend = installFakeBackend({ documents: [DOC] })
    const { user } = renderApp()

    const toggle = screen.getByRole('switch', { name: 'Allow External Search' })
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(toggle).toBeDisabled()
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-checked', 'false')

    await user.type(screen.getByLabelText('Your question'), 'Where did I study?{Enter}')
    await screen.findByText('An answer.')
    const askCall = backend.requests.find((r) => r.path === '/ask')
    expect(askCall?.body).toEqual({ question: 'Where did I study?', debug: false })
  })

  it('explains that external search is off when a question is out of scope', async () => {
    installFakeBackend({
      documents: [DOC],
      askResponse: { status: 'out_of_scope', answer: 'I can only help with…', sources: [], debug: null },
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
      askResponse: { status: 'not_found', answer: "I couldn't find that…", sources: [], debug: null },
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
