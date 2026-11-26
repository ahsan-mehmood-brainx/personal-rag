import { expect, test } from '@playwright/test'
import { persona, resetBackend, seedDocument, uploadViaUi } from './helpers'

test.beforeEach(async ({ request }) => {
  await resetBackend(request)
})

test('empty state, multi-file upload, and listing with type, date and status', async ({ page }) => {
  await page.goto('/documents')
  await expect(page.getByRole('heading', { name: 'No documents yet' })).toBeVisible()

  await uploadViaUi(page, [persona('cv.md'), persona('certifications.docx'), persona('cv_onepage.pdf')])

  const rows = page.getByTestId('document-row')
  await expect(rows).toHaveCount(3)
  await expect(page.getByTestId('document-count')).toHaveText('3 documents')

  const pdfRow = rows.filter({ hasText: 'cv_onepage.pdf' })
  await expect(pdfRow.getByText('PDF', { exact: true })).toBeVisible()
  await expect(pdfRow.getByText('Indexed')).toBeVisible()
  await expect(pdfRow.locator('time')).toHaveAttribute('datetime', /\d{4}-\d{2}-\d{2}T/)
  await expect(rows.filter({ hasText: 'certifications.docx' }).getByText('Word', { exact: true })).toBeVisible()

  const uploads = page.getByRole('list', { name: 'Upload progress' })
  await expect(uploads.getByText(/^Indexed · \d+ chunks?$/)).toHaveCount(3)
  await expect(page.getByTestId('health-indicator')).toContainText('Connected')
})

test('duplicate upload is reported, not re-indexed', async ({ page, request }) => {
  await seedDocument(request, 'projects.txt')
  await page.goto('/documents')
  await expect(page.getByTestId('document-row')).toHaveCount(1)

  await uploadViaUi(page, [persona('projects.txt')])
  await expect(page.getByText('Already in your knowledge base. Nothing changed.')).toBeVisible()
  await expect(page.getByTestId('document-row')).toHaveCount(1)
})

test('rejects legacy .doc on the client and shows backend validation errors', async ({ page }) => {
  await page.goto('/documents')
  await uploadViaUi(page, [
    { name: 'old-resume.doc', mimeType: 'application/msword', buffer: Buffer.from('legacy') },
    { name: 'fake.pdf', mimeType: 'application/pdf', buffer: Buffer.from('not really a pdf') },
  ])
  const uploads = page.getByRole('list', { name: 'Upload progress' })
  await expect(uploads.getByText(/Legacy \.doc files are not supported/)).toBeVisible()
  // 422 from the backend's signature check, shown verbatim.
  await expect(uploads.getByText('File is not a valid PDF.')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'No documents yet' })).toBeVisible()
})

test('delete asks for confirmation; cancel keeps the document, confirm removes it', async ({ page, request }) => {
  await seedDocument(request, 'cv.md')
  await seedDocument(request, 'projects.txt')
  await page.goto('/documents')
  await expect(page.getByTestId('document-row')).toHaveCount(2)

  await page.getByRole('button', { name: 'Delete cv.md' }).click()
  const dialog = page.getByRole('alertdialog', { name: 'Delete this document?' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByTestId('document-row')).toHaveCount(2)

  await page.getByRole('button', { name: 'Delete cv.md' }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Delete' }).click()
  await expect(page.getByTestId('document-row')).toHaveCount(1)
  await expect(page.getByTestId('document-row')).toContainText('projects.txt')

  // The server agrees.
  await page.reload()
  await expect(page.getByTestId('document-row')).toHaveCount(1)
})

// Match API calls only: a glob like **/api/** would also catch Vite's /src/api/*.ts modules.
const isApiCall = (url: URL) => url.pathname.startsWith('/api/')

test('shows an error state with retry when the backend is unreachable', async ({ page }) => {
  await page.route(isApiCall, (route) => route.abort('connectionrefused'))
  await page.goto('/documents')
  await expect(page.getByRole('heading', { name: "Couldn't load your documents" })).toBeVisible()
  await expect(page.getByTestId('health-indicator')).toContainText('Offline')

  await page.unroute(isApiCall)
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('heading', { name: 'No documents yet' })).toBeVisible()
})

test('no horizontal overflow on the documents page', async ({ page, request }) => {
  await seedDocument(request, 'certifications.docx')
  await page.goto('/documents')
  await expect(page.getByTestId('document-row')).toHaveCount(1)
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
})
