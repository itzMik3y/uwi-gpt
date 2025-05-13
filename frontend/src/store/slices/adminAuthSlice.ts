// src/store/slices/adminAuthSlice.ts
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { adminApi } from '@/lib/api/adminClient'; // Assuming ADMIN_TOKEN_STORAGE_KEY etc. are not directly used here
import {
  AdminLoginRequest,
  AdminAuthResponse,
  AdminUser,
  AdminDataResponse,
  AdminSlotWithBooking
} from '@/types/admin';

interface AdminAuthState {
  isAuthenticated: boolean;
  isAuthInitialized: boolean;
  admin: AdminUser | null;
  slots: AdminSlotWithBooking[] | null;
  isLoading: boolean;
  error: string | null;
}

const initialState: AdminAuthState = {
  isAuthenticated: false,
  isAuthInitialized: false,
  admin: null,
  slots: null,
  isLoading: false,
  error: null
};

// Login thunk - handles the initial login process
export const loginAdmin = createAsyncThunk<
  AdminAuthResponse,
  AdminLoginRequest,
  { rejectValue: string, state: { adminAuth: AdminAuthState } }
>('adminAuth/login', async (credentials, { rejectWithValue }) => { // Removed dispatch from params
  try {
    adminApi.clearTokens();
    console.log('Login thunk started, proceeding to API call for login.');
    const response = await adminApi.login(credentials);
    console.log('Admin API login call successful, tokens received:', response);

    // MODIFICATION: Removed the automatic dispatch of fetchAdminData from here.
    // The dashboard will be responsible for fetching data after authentication.
    return response;
  } catch (err: any) {
    console.error('Admin login failed in thunk:', err);
    return rejectWithValue(err?.response?.data?.detail || err?.message || 'Login failed');
  }
});

// Fetch admin data thunk - gets admin data after login or on dashboard load
export const fetchAdminData = createAsyncThunk<
  AdminDataResponse,
  void,
  { rejectValue: string, state: { adminAuth: AdminAuthState } }
>('adminAuth/fetchAdminData', async (_, { rejectWithValue }) => { // Removed dispatch, getState from params
  try {
    // MODIFICATION: Removed the internal isLoading check.
    // The .pending action will set isLoading. The component calling this thunk
    // should manage whether to dispatch it based on its own logic (e.g., !isLoading from selector).
    console.log('fetchAdminData thunk: proceeding to adminApi.getAdminData()');
    return await adminApi.getAdminData();
  } catch (err: any) {
    console.error('Error fetching admin data in thunk:', err);
    // The .rejected reducer case will set isLoading = false.
    return rejectWithValue(err?.response?.data?.detail || err?.message || 'Failed to fetch admin data');
  }
});

// Create slots thunk
export const createSlots = createAsyncThunk<
  AdminSlotWithBooking[],
  { slots: { start_time: string; end_time: string }[] },
  { rejectValue: string }
>('adminAuth/createSlots', async (slotsData, { rejectWithValue }) => {
  try {
    return await adminApi.createSlots(slotsData);
  } catch (err: any) {
    return rejectWithValue(err?.response?.data?.detail || err?.message || 'Failed to create slots');
  }
});

// Check auth status thunk - verifies if the current token is valid
export const checkAdminAuthStatus = createAsyncThunk<
  boolean,
  void,
  { rejectValue: string, state: { adminAuth: AdminAuthState } }
>('adminAuth/checkStatus', async (_, { dispatch, rejectWithValue, getState }) => {
  try {
    if (!adminApi.isAuthenticated()) {
      console.log('checkAdminAuthStatus: No token, returning false.');
      return false;
    }
    
    const { admin, isLoading } = getState().adminAuth;
    if (admin) {
      console.log('checkAdminAuthStatus: Admin data already in store, returning true.');
      return true;
    }

    // If no admin data, but token exists, try to fetch.
    // Avoid dispatching if a fetch is already in progress.
    if (isLoading) {
        console.log('checkAdminAuthStatus: isLoading is true, assuming auth check will resolve, returning true temporarily.');
        // This case is tricky. If a fetch is ongoing due to login, we might want to assume true.
        // However, if it's stuck, this could be problematic.
        // For now, let's assume an ongoing fetch (likely from login/dashboard mount) will clarify auth.
        return true; 
    }
    
    console.log('checkAdminAuthStatus: Token exists, no admin data, not loading. Attempting to fetch admin data.');
    try {
      await dispatch(fetchAdminData()).unwrap();
      console.log('checkAdminAuthStatus: fetchAdminData successful.');
      return true; // If unwrap doesn't throw, fetch was successful
    } catch (error: any) {
      console.error('checkAdminAuthStatus: Error fetching admin data to validate token:', error);
      return false; // Fetch failed, so token might be invalid or other issue
    }
  } catch (err: any) {
    console.error('checkAdminAuthStatus: General error:', err);
    return false;
  }
});

const adminAuthSlice = createSlice({
  name: 'adminAuth',
  initialState,
  reducers: {
    logoutAdmin(state) {
      adminApi.clearTokens();
      // Reset to initial state but keep isAuthInitialized true
      Object.assign(state, initialState, { isAuthInitialized: true, isAuthenticated: false });
    },
    setAdminAuthInitialized(state, action: PayloadAction<boolean>) {
      state.isAuthInitialized = action.payload;
    },
    clearAdminError(state) {
      state.error = null;
    },
    resetLoadingState(state) {
      state.isLoading = false;
    }
  },
  extraReducers: (builder) => {
    builder
      // loginAdmin
      .addCase(loginAdmin.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(loginAdmin.fulfilled, (state, action) => {
        state.isLoading = false;
        state.isAuthenticated = true; // Token received
        state.error = null;
        state.isAuthInitialized = true;
        // Admin data (user profile) is NOT set here; dashboard will fetch it.
      })
      .addCase(loginAdmin.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload || 'Login failed';
        state.isAuthenticated = false;
        state.isAuthInitialized = true; 
      })
      
      // fetchAdminData
      .addCase(fetchAdminData.pending, (state) => {
        // Only set isLoading if admin data isn't already present (i.e., initial fetch)
        // or if explicitly refreshing. For now, simple isLoading set is fine.
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchAdminData.fulfilled, (state, action) => {
        state.isLoading = false;
        state.error = null;
        state.isAuthInitialized = true; 
        
        if (action.payload && action.payload.admin) {
          state.admin = action.payload.admin;
          state.slots = action.payload.slots || [];
          state.isAuthenticated = true; // Re-affirm auth if data is successfully fetched
        } else {
          // Fetched successfully but no admin data, or payload was unexpected
          state.admin = null; // Ensure admin is null if not in payload
          state.slots = null;
          // Potentially set an error or log out if isAuthenticated was true
          // For now, if fetchAdminData is called, it implies an attempt to get admin profile.
          // If it's empty, then admin is null.
          if(state.isAuthenticated) { // if we thought we were authenticated
            state.error = "Admin data not found after fetch.";
            // Consider setting isAuthenticated to false if admin data is mandatory for an authenticated admin session
            // state.isAuthenticated = false; 
          }
        }
      })
      .addCase(fetchAdminData.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload || 'Failed to fetch admin data';
        state.admin = null; // Ensure admin is null on failure
        state.slots = null;
        // If fetching data fails, especially due to auth, ensure isAuthenticated is false.
        const errPayload = action.payload?.toLowerCase() || "";
        if (errPayload.includes('unauthorized') || errPayload.includes('authentication') || errPayload.includes('401')) {
          state.isAuthenticated = false;
        }
        state.isAuthInitialized = true;
      })
      
      // createSlots
      .addCase(createSlots.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(createSlots.fulfilled, (state, action) => {
        state.isLoading = false;
        state.error = null;
        if (state.slots) {
          state.slots = [...state.slots, ...action.payload];
        } else {
          state.slots = action.payload;
        }
      })
      .addCase(createSlots.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload || 'Failed to create slots';
      })
      
      // checkAdminAuthStatus
      .addCase(checkAdminAuthStatus.pending, (state) => {
        // state.isLoading = true; // Can cause issues if fetchAdminData also sets it
      })
      .addCase(checkAdminAuthStatus.fulfilled, (state, action) => {
        state.isLoading = false; 
        state.isAuthInitialized = true;
        // If checkAdminAuthStatus directly fetches data and confirms, isAuthenticated might be set here.
        // But since it calls fetchAdminData, fetchAdminData.fulfilled will primarily handle state.admin and isAuthenticated.
        if (!action.payload) { 
          state.isAuthenticated = false;
          state.admin = null;
          state.slots = null;
        } else {
            // If action.payload is true, it means token is valid and data fetch was (or will be) attempted.
            // isAuthenticated will be set by fetchAdminData.fulfilled.
            // If admin is already set, ensure isAuthenticated is true.
            if(state.admin) state.isAuthenticated = true;
        }
      })
      .addCase(checkAdminAuthStatus.rejected, (state) => {
        state.isLoading = false;
        state.isAuthenticated = false;
        state.isAuthInitialized = true;
        state.admin = null;
        state.slots = null;
      });
  }
});

export const { logoutAdmin, setAdminAuthInitialized, clearAdminError, resetLoadingState } = adminAuthSlice.actions;
export default adminAuthSlice.reducer;