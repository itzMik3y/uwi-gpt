// src/store/index.ts
import { configureStore, combineReducers } from '@reduxjs/toolkit';
import {
  persistStore,
  persistReducer,
  FLUSH,
  REHYDRATE,
  PAUSE,
  PERSIST,
  PURGE,
  REGISTER
} from 'redux-persist';
import storage from 'redux-persist/lib/storage';
import authReducer from './slices/authSlice';
import chatReducer from './slices/chatSlice'; 
import adminAuthReducer from './slices/adminAuthSlice';

const persistConfig = {
  key: 'root',
  storage,
  whitelist: ['auth', 'adminAuth'] // Persist both auth and adminAuth states
};

const rootReducer = combineReducers({
  auth: authReducer,
  chat: chatReducer,
  adminAuth: adminAuthReducer,
  // Add other reducers here
});

const persistedReducer = persistReducer(persistConfig, rootReducer);

export const store = configureStore({
  reducer: persistedReducer,
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        // Ignore specific action types & state paths for non-serializable values
        ignoredActions: [
          FLUSH,
          REHYDRATE,
          PAUSE,
          PERSIST,
          PURGE,
          REGISTER,
          'chat/startStreamingResponse/fulfilled' // Ignore fulfilled action for streaming thunk
        ],
        ignoredPaths: ['chat.streamCleanup'], // Ignore the streamCleanup function in state
      }
    }),
  // Add support for Redux DevTools
  devTools: process.env.NODE_ENV !== 'production',
});

export const persistor = persistStore(store);
export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;