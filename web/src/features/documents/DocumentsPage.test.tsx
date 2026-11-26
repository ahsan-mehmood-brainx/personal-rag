import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { installFakeBackend } from '../../test/fakeBackend'
import { renderApp } from '../../test/renderApp'

const docs = [
  { doc_id: 'd1', filename: 'cv.md', chunk_count: 3, ingested_at: '2026-11-20T10:00:00Z' },
  { doc_id: 'd2', filename: 'certs.docx', chunk_count: 1, ingested_at: '2026-11-25T10:00:00Z' },
]

afterEach(() => vi.unstubAllGlobals())

describe('DocumentsPage', () => {
  it('lists documents newest first with type and status', async () => {
    installFakeBackend({ documents: [...docs] })
    renderApp('/documents')
    const rows = await screen.findAllByTestId('document-row')
    expect(rows.map((r) => within(r).getAllByRole('cell')[0]?.textContent)).toEqual(['certs.docx', 'cv.md'])
    expect(within(rows[0]!).getByText('Word')).toBeInTheDocument()
    expect(within(rows[0]!).getByText('Indexed')).toBeInTheDocument()
    expect(screen.getByTestId('document-count')).toHaveTextContent('2 documents')
  })

  it('rejects unsupported files on the client without calling the backend', async () => {
    const backend = installFakeBackend()
    renderApp('/documents')
    await screen.findByText('No documents yet')
    // applyAccept:false simulates a drag-and-drop or an "All files" pick that bypasses `accept`.
    const user = userEvent.setup({ applyAccept: false })
    await user.upload(screen.getByTestId('file-input') as HTMLInputElement, new File(['x'], 'old.doc'))
    expect(await screen.findByText(/Legacy \.doc files are not supported/)).toBeInTheDocument()
    expect(backend.requests.some((r) => r.method === 'POST')).toBe(false)
  })

  it('deletes after confirmation and shows a toast', async () => {
    const backend = installFakeBackend({ documents: [...docs] })
    const { user } = renderApp('/documents')
    await screen.findAllByTestId('document-row')

    await user.click(screen.getByRole('button', { name: 'Delete cv.md' }))
    const dialog = screen.getByRole('alertdialog', { name: 'Delete this document?' })
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(screen.getAllByTestId('document-row')).toHaveLength(1))
    expect(await screen.findByText('Document deleted')).toBeInTheDocument()
    expect(backend.documents.map((d) => d.doc_id)).toEqual(['d2'])
  })

  it('Escape closes the delete dialog without deleting', async () => {
    const backend = installFakeBackend({ documents: [...docs] })
    const { user } = renderApp('/documents')
    await screen.findAllByTestId('document-row')
    await user.click(screen.getByRole('button', { name: 'Delete cv.md' }))
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(backend.documents).toHaveLength(2)
  })
})

