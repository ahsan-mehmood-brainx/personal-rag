/** Route paths in one place, so links, redirects and navigation cannot drift apart. */
export const ROUTES = {
  chat: '/chat',
  documents: '/documents',
  conversation: (id: string) => `/chat/${id}`,
} as const
