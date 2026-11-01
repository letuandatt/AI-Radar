import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { App } from './App';

import '@fontsource/inter/400.css';
import '@fontsource/inter/600.css';
import '@fontsource/jetbrains-mono/400.css';
import './styles.css';

async function start() {
  if (import.meta.env.DEV && import.meta.env.MODE === 'mock') {
    const { worker } = await import('./mocks/browser');
    await worker.start({ onUnhandledFrame: 'bypass' });
  }

  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 30000,
        refetchOnWindowFocus: false,
      },
    },
  });

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <QueryClientProvider client={client}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </React.StrictMode>,
  );
}

start().catch(() => {
  document.getElementById('root')!.textContent =
    'Unable to start the application. Reload to retry.';
});