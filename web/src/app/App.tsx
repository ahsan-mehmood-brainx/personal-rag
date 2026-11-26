import { Navigate, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '../components/Toast'
import { ChatProvider } from '../features/chat/ChatContext'
import { ChatPage } from '../features/chat/ChatPage'
import { DocumentsPage } from '../features/documents/DocumentsPage'
import { HealthProvider } from '../features/health/HealthContext'
import { AppShell } from './AppShell'
import { ROUTES } from './routes'

/** Providers and routes. Kept router-agnostic so tests can wrap it in a MemoryRouter. */
export function App() {
  return (
    <ToastProvider>
      <HealthProvider>
        <ChatProvider>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<Navigate to={ROUTES.chat} replace />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="chat/:conversationId" element={<ChatPage />} />
              <Route path="documents" element={<DocumentsPage />} />
              <Route path="*" element={<Navigate to={ROUTES.chat} replace />} />
            </Route>
          </Routes>
        </ChatProvider>
      </HealthProvider>
    </ToastProvider>
  )
}
