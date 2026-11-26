import { expect, test, type Page } from '@playwright/test'
import { resetBackend, seedDocument } from './helpers'

const isAsk = (url: URL) => url.pathname === '/api/ask'

async function askQuestion(page: Page, question: string) {
  const box = page.getByLabel('Your question')
  await box.fill(question)
  await box.press('Enter')
}

/** On narrow screens history is a drawer (hidden until opened); on desktop it is always shown. */
async function openHistory(page: Page) {
  if (await page.getByTestId('chat-sidebar').isVisible()) return
  await page.getByRole('button', { name: 'Open history' }).click()
  await expect(page.getByTestId('chat-sidebar')).toBeVisible()
}

const lastAssistant = (page: Page) => page.locator('article[aria-label^="Assistant"]').last()

test.beforeEach(async ({ request }) => {
  await resetBackend(request)
})

test('answers from uploaded documents with a status badge and sources', async ({ page, request }) => {
  await seedDocument(request, 'cv.md')
  await page.goto('/chat')
  await expect(page.getByRole('heading', { name: 'Ask about your background' })).toBeVisible()

  await askQuestion(page, 'Where did I study?')
  await expect(page.getByRole('article', { name: 'You' })).toHaveText('Where did I study?')
  const answer = lastAssistant(page)
  await expect(answer.getByText('Answered')).toBeVisible()
  await expect(answer).toContainText('From your documents (cv.md)')
  // The fake answer contains "- " lines, which render as a real list.
  await expect(answer.locator('ul li').first()).toBeVisible()

  await answer.getByText('Sources (1)').click()
  await expect(answer.getByText('S1', { exact: true })).toBeVisible()
  await expect(answer.locator('blockquote')).not.toBeEmpty()

  await expect(page).toHaveURL(/\/chat\/[\w-]+$/)
  await expect(page.getByLabel('Your question')).toHaveValue('')
})

test('external search is the only toggle, OFF by default and enabled', async ({ page }) => {
  await page.goto('/chat')
  await expect(page.getByRole('switch')).toHaveCount(1)
  const toggle = page.getByRole('switch', { name: 'Allow External Search' })
  await expect(toggle).toBeVisible()
  await expect(toggle).toHaveAttribute('aria-checked', 'false')
  await expect(toggle).toBeEnabled()
  await expect(page.getByText('Answers come only from your uploaded documents.')).toBeVisible()
})

test('external search can be turned on and off during a conversation', async ({ page, request }) => {
  await seedDocument(request, 'cv.md')
  await page.goto('/chat')
  const toggle = page.getByRole('switch', { name: 'Allow External Search' })

  // First question with the toggle OFF: refused, with the notice.
  await askQuestion(page, 'What is Kubernetes?')
  await expect(lastAssistant(page).getByText('Out of scope')).toBeVisible()
  await expect(lastAssistant(page).getByTestId('external-search-notice')).toBeVisible()

  // Turn it ON after the first chat: the same kind of question is answered from the web.
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-checked', 'true')
  const sentOn = page.waitForRequest((r) => isAsk(new URL(r.url())))
  await askQuestion(page, 'What is Docker?')
  expect((await sentOn).postDataJSON()).toMatchObject({ allow_external_search: true })
  const web = lastAssistant(page)
  await expect(web.getByText('From the web', { exact: true })).toBeVisible()
  await expect(web).toContainText('From the web: a general answer')
  await web.getByText('Web sources (1)').click()
  await expect(web.getByRole('link', { name: 'Example source' })).toHaveAttribute('href', 'https://example.com/')
  await expect(web.getByTestId('external-search-notice')).toHaveCount(0)

  // Personal questions still come from the documents with the toggle ON.
  await askQuestion(page, 'Where did I study?')
  await expect(lastAssistant(page).getByText('Answered')).toBeVisible()

  // Turn it OFF again: back to the refusal. All of this stays in one conversation.
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-checked', 'false')
  await askQuestion(page, 'What is Python?')
  await expect(lastAssistant(page).getByText('Out of scope')).toBeVisible()
  await expect(page.getByRole('article', { name: 'You' })).toHaveCount(4)
})

test('out-of-scope questions explain that external search is off', async ({ page, request }) => {
  await seedDocument(request, 'cv.md')
  await page.goto('/chat')
  await askQuestion(page, 'What is Kubernetes?')
  const answer = lastAssistant(page)
  await expect(answer.getByText('Out of scope')).toBeVisible()
  // Backend's fixed refusal text, shown verbatim.
  await expect(answer).toContainText('I can only help with questions about your own background')
  await expect(answer.getByTestId('external-search-notice')).toContainText('External search is off')

  // A normal answer carries no such notice.
  await askQuestion(page, 'Where did I study?')
  await expect(lastAssistant(page).getByText('Answered')).toBeVisible()
  await expect(page.getByTestId('external-search-notice')).toHaveCount(1)
})

test('meta, no-documents and upstream-error statuses render their fixed messages', async ({ page, request }) => {
  await page.goto('/chat')
  await expect(page.getByText('No documents yet')).toBeVisible()

  await askQuestion(page, 'Where did I work?')
  await expect(lastAssistant(page).getByText('No documents', { exact: true })).toBeVisible()
  await expect(lastAssistant(page)).toContainText('No documents have been uploaded yet.')

  await seedDocument(request, 'cv.md')
  await askQuestion(page, 'hello there')
  await expect(lastAssistant(page).getByText('Info', { exact: true })).toBeVisible()
  await expect(lastAssistant(page)).toContainText("I'm your personal knowledge assistant")

  // HTTP 502 with an AskResponse body: shown as a normal "Error" answer, not a crash.
  await askQuestion(page, 'please trigger upstream error')
  await expect(lastAssistant(page).getByText('Error', { exact: true })).toBeVisible()
  await expect(lastAssistant(page)).toContainText('Something went wrong while processing your question')
})

test('a failed request can be retried', async ({ page, request }) => {
  await seedDocument(request, 'cv.md')
  await page.goto('/chat')
  await page.route(isAsk, (route) => route.abort('connectionrefused'))
  await askQuestion(page, 'Where did I study?')
  const failure = page.getByRole('article', { name: 'Request failed' })
  await expect(failure).toContainText('Cannot reach the backend API')

  await page.unroute(isAsk)
  await failure.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByRole('article', { name: 'Request failed' })).toHaveCount(0)
  await expect(lastAssistant(page).getByText('Answered')).toBeVisible()
  // The question is not duplicated by the retry.
  await expect(page.getByRole('article', { name: 'You' })).toHaveCount(1)
})

test('shows a loading indicator and can stop a slow request', async ({ page, request }) => {
  await seedDocument(request, 'cv.md')
  await page.goto('/chat')
  await page.route(isAsk, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 4000))
    await route.continue().catch(() => undefined) // the page may have aborted already
  })
  await askQuestion(page, 'Where did I study?')
  const pending = page.getByTestId('pending-message')
  await expect(pending).toContainText('Searching your documents')
  await expect(page.getByRole('button', { name: 'Send' })).toBeDisabled()

  await pending.getByRole('button', { name: 'Stop' }).click()
  await expect(page.getByRole('article', { name: 'Request failed' })).toContainText('You stopped this request')
  await expect(pending).toHaveCount(0)
})

test('sends the external search flag and no debug request by default', async ({ page, request }) => {
  await seedDocument(request, 'cv.md')
  await page.goto('/chat')
  const requestPromise = page.waitForRequest((r) => isAsk(new URL(r.url())))
  await askQuestion(page, 'Where did I study?')
  const sent = (await requestPromise).postDataJSON() as Record<string, unknown>
  expect(sent).toEqual({ question: 'Where did I study?', debug: false, allow_external_search: false })
  await expect(lastAssistant(page).getByText('Internals')).toHaveCount(0)
})

test('enforces the question length limit before sending', async ({ page }) => {
  await page.goto('/chat')
  await page.getByLabel('Your question').fill('x'.repeat(1001))
  await expect(page.getByText('1 characters over the 1000 limit')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Send' })).toBeDisabled()
})

test('conversation history persists, switches and deletes', async ({ page, request }) => {
  await seedDocument(request, 'cv.md')
  await page.goto('/chat')
  await askQuestion(page, 'Where did I study?')
  await expect(lastAssistant(page).getByText('Answered')).toBeVisible()

  await page.getByRole('button', { name: 'New chat' }).first().click()
  await expect(page).toHaveURL(/\/chat$/)
  await askQuestion(page, 'What is Kubernetes?')
  await expect(lastAssistant(page).getByText('Out of scope')).toBeVisible()

  await page.reload()
  await openHistory(page)
  const history = page.getByRole('navigation', { name: 'Conversation history' })
  await expect(history.getByRole('link')).toHaveCount(2)

  await history.getByRole('link', { name: /Where did I study\?/ }).click()
  await expect(page.getByRole('article', { name: 'You' })).toHaveText('Where did I study?')

  await openHistory(page)
  await history.getByRole('button', { name: 'Delete conversation: Where did I study?' }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Delete' }).click()
  await expect(page).toHaveURL(/\/chat$/)
  await openHistory(page)
  await expect(history.getByRole('link')).toHaveCount(1)
})

test('chat is text-only: no file, image, audio or voice inputs', async ({ page }) => {
  await page.goto('/chat')
  await expect(page.locator('input[type="file"]')).toHaveCount(0)
  await expect(page.locator('audio, video, [accept]')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /attach|voice|microphone|record|image/i })).toHaveCount(0)
  await expect(page.locator('textarea')).toHaveCount(1)
})

test('no horizontal overflow on the chat page', async ({ page, request }) => {
  await seedDocument(request, 'cv.md')
  await page.goto('/chat')
  await askQuestion(page, 'Where did I study?')
  await expect(lastAssistant(page).getByText('Answered')).toBeVisible()
  await lastAssistant(page).getByText('Sources (1)').click()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
  await expect(lastAssistant(page)).toBeInViewport({ ratio: 0.1 })
})
