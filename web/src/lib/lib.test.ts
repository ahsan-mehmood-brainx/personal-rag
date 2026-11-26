import { describe, expect, it } from 'vitest'
import { validateFile } from './files'
import { extensionOf, fileTypeLabel, formatBytes, formatRelative, pluralize } from './format'

const MB = 1024 * 1024

describe('validateFile', () => {
  it.each(['cv.pdf', 'CV.DOCX', 'notes.txt', 'readme.md'])('accepts %s', (name) => {
    expect(validateFile({ name, size: 100 }, 10 * MB)).toBeNull()
  })

  it('explains that legacy .doc must be converted', () => {
    expect(validateFile({ name: 'resume.doc', size: 100 }, 10 * MB)).toMatch(/Save it as \.docx/)
  })

  it('rejects other types, empty files and files over the limit', () => {
    expect(validateFile({ name: 'photo.png', size: 100 }, 10 * MB)).toMatch(/Unsupported file type/)
    expect(validateFile({ name: 'noext', size: 100 }, 10 * MB)).toMatch(/Unsupported file type/)
    expect(validateFile({ name: 'cv.pdf', size: 0 }, 10 * MB)).toBe('The file is empty.')
    expect(validateFile({ name: 'cv.pdf', size: 11 * MB }, 10 * MB)).toBe(
      'The file is 11 MB; the limit is 10 MB.',
    )
  })
})

describe('format helpers', () => {
  it('extracts extensions and type labels', () => {
    expect(extensionOf('My.CV.PDF')).toBe('.pdf')
    expect(extensionOf('.hidden')).toBe('')
    expect(fileTypeLabel('a.docx')).toBe('Word')
    expect(fileTypeLabel('a.md')).toBe('Markdown')
    expect(fileTypeLabel('a.xyz')).toBe('XYZ')
  })

  it('formats sizes and plurals', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2 KB')
    expect(formatBytes(1.5 * MB)).toBe('1.5 MB')
    expect(pluralize(1, 'chunk')).toBe('1 chunk')
    expect(pluralize(3, 'chunk')).toBe('3 chunks')
  })

  it('formats relative times', () => {
    const now = new Date('2026-11-25T12:00:00Z')
    expect(formatRelative('2026-11-25T11:59:30Z', now)).toBe('Just now')
    expect(formatRelative('2026-11-25T11:45:00Z', now)).toBe('15 min ago')
    expect(formatRelative('2026-11-25T09:00:00Z', now)).toBe('3 h ago')
    expect(formatRelative('2026-11-24T10:00:00Z', now)).toBe('Yesterday')
    expect(formatRelative('not a date', now)).toBe('')
  })
})
