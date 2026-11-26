import { expect, type APIRequestContext, type Page } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))

/** Synthetic persona documents shipped with the backend tests. Never real personal data. */
export const PERSONA_DIR = path.resolve(here, '../../tests/fixtures/persona')
export const persona = (name: string) => path.join(PERSONA_DIR, name)

const API = 'http://127.0.0.1:8765'

/** Delete every document so each test starts from an empty knowledge base. */
export async function resetBackend(request: APIRequestContext): Promise<void> {
  const response = await request.get(`${API}/documents`)
  expect(response.ok()).toBeTruthy()
  const docs = (await response.json()) as Array<{ doc_id: string }>
  for (const doc of docs) {
    await request.delete(`${API}/documents/${doc.doc_id}`)
  }
}

export async function seedDocument(request: APIRequestContext, name: string): Promise<void> {
  const fs = await import('node:fs/promises')
  const buffer = await fs.readFile(persona(name))
  const response = await request.post(`${API}/documents`, {
    multipart: { file: { name, mimeType: 'application/octet-stream', buffer } },
  })
  expect(response.ok()).toBeTruthy()
}

export async function uploadViaUi(page: Page, files: string[] | { name: string; mimeType: string; buffer: Buffer }[]) {
  await page.getByTestId('file-input').setInputFiles(files)
}
