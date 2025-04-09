// app/client-providers.tsx
'use client';

import { useEffect } from 'react';
import { Provider } from 'react-redux';
import { PersistGate } from 'redux-persist/integration/react';
import { store, persistor } from '@/store';
import { initializeAuth } from '@/store/slices/authSlice';

export function ClientProviders({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    // Initialize auth state from localStorage
    store.dispatch(initializeAuth());
  }, []);

  return (
    <Provider store={store}>
      <PersistGate loading={null} persistor={persistor}>
        {children}
      </PersistGate>
    </Provider>
  );
}