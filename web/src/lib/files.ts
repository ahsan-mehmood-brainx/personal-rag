/**
 * Client-side upload pre-checks.
 *
 * These only give faster, friendlier feedback. The backend re-validates type, signature and
 * size (ingestion/validation.py) and its answer is the one that counts.
 */
import { ALLOWED_EXTENSIONS, config } from '../config'
import { extensionOf, formatBytes } from './format'

export const ACCEPT_ATTRIBUTE = ALLOWED_EXTENSIONS.join(',')

export function validateFile(
  file: Pick<File, 'name' | 'size'>,
  maxBytes: number = config.maxUploadBytes,
): string | null {
  const ext = extensionOf(file.name)
  if (ext === '.doc') {
    return 'Legacy .doc files are not supported. Save it as .docx and upload again.'
  }
  if (!(ALLOWED_EXTENSIONS as readonly string[]).includes(ext)) {
    return `Unsupported file type. Use ${ALLOWED_EXTENSIONS.join(', ')}.`
  }
  if (file.size === 0) return 'The file is empty.'
  if (file.size > maxBytes) {
    return `The file is ${formatBytes(file.size)}; the limit is ${formatBytes(maxBytes)}.`
  }
  return null
}
