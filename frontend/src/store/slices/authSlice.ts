// src/store/slices/authSlice.ts
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { moodleApi } from '@/lib/api/moodleClient'; // TOKEN_STORAGE_KEY etc. are not directly used by thunks but by moodleApi
import {
  MoodleLoginRequest,
  CombinedLoginResponse,
  AuthResponse,
  MoodleUser,
  MoodleCourse,
  MoodleAuthTokens,
  MoodleCalendarEvent,
  GradesDataPayload,
  GradesStatus
} from '@/types/moodle';

interface AuthState {
  isAuthenticated: boolean;
  isAuthInitialized: boolean;
  user: MoodleUser | null;
  courses: MoodleCourse[] | null;
  calendarEvents: {
    events: MoodleCalendarEvent[];
    firstid: number | null;
    lastid: number | null;
  } | null;
  authTokens: MoodleAuthTokens | null;
  gradesData: GradesDataPayload | null;
  gradesStatus: GradesStatus | null;
  isLoading: boolean;
  error: string | null;
}

const initialState: AuthState = {
  isAuthenticated: false,
  isAuthInitialized: false,
  user: null,
  courses: null,
  calendarEvents: null,
  authTokens: null,
  gradesData: null,
  gradesStatus: null,
  isLoading: false,
  error: null
};

// Login thunk
export const loginUser = createAsyncThunk<
  AuthResponse,
  MoodleLoginRequest,
  { rejectValue: string }
>('auth/login', async (credentials, { rejectWithValue }) => {
  try {
    return await moodleApi.login(credentials);
  } catch (err: any) {
    return rejectWithValue(err?.message || 'Login failed');
  }
});

// Fetch user data thunk
export const fetchUserData = createAsyncThunk<
  CombinedLoginResponse,
  void,
  { rejectValue: string }
>('auth/fetchUserData', async (_, { rejectWithValue }) => {
  try {
    return await moodleApi.getUserData();
  } catch (err: any) {
    return rejectWithValue(err?.message || 'Failed to fetch user data');
  }
});

// Check auth status thunk
export const checkAuthStatus = createAsyncThunk<
  boolean,
  void,
  { dispatch: any; rejectValue: string } // Added dispatch type for internal dispatch
>('auth/checkStatus', async (_, { dispatch, rejectWithValue }) => {
  try {
    if (!moodleApi.isAuthenticated()) {
      return false;
    }
    await dispatch(fetchUserData()).unwrap(); // Use unwrap to ensure error propagates if fetchUserData fails
    return true;
  } catch (err: any) {
    return false; // If any error during validation, consider not authenticated
  }
});

// New Thunk for Account Deletion
export const deleteUserAccount = createAsyncThunk<
  void, // Resolves with void on success
  void, // No arguments needed
  { dispatch: any; rejectValue: string } // Added dispatch type
>(
  'auth/deleteAccount',
  async (_, { dispatch, rejectWithValue }) => {
    try {
      await moodleApi.deleteAccount();
      // After moodleApi.deleteAccount() succeeds, tokens are cleared from localStorage.
      // Now, dispatch logout() to clear the Redux state.
      dispatch(logout());
      // No explicit return value needed for void promise
    } catch (err: any) {
      return rejectWithValue(err?.message || 'Failed to delete account.');
    }
  }
);


const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    logout(state) {
      state.isAuthenticated = false;
      state.user = null;
      state.courses = null;
      state.calendarEvents = null;
      state.authTokens = null;
      state.gradesData = null;
      state.gradesStatus = null;
      state.isLoading = false; // Ensure loading is reset on logout
      state.error = null;
      
      moodleApi.clearTokens(); // This is already called by moodleApi.deleteAccount on success, but good to have for explicit logout action
    },
    setAuthInitialized(state, action: PayloadAction<boolean>) {
      state.isAuthInitialized = action.payload;
    }
  },
  extraReducers: (builder) => {
    builder
      // Login
      .addCase(loginUser.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(loginUser.fulfilled, (state, action) => {
        state.isLoading = false;
        state.isAuthenticated = true;
        state.error = null;
        state.isAuthInitialized = true;
      })
      .addCase(loginUser.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload || 'Login failed';
        state.isAuthenticated = false;
        state.isAuthInitialized = true;
      })
      
      // Fetch User Data
      .addCase(fetchUserData.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchUserData.fulfilled, (state, action) => {
        state.isLoading = false;
        state.error = null;
        state.isAuthInitialized = true;
        
        const { moodle_data, grades_data, grades_status } = action.payload;
        
        state.user = moodle_data.user_info;
        state.courses = moodle_data.courses.courses;
        state.calendarEvents = moodle_data.calendar_events;
        // state.authTokens = moodle_data.auth_tokens; // Not typically stored directly in Redux if API client handles them
        state.gradesData = grades_data;
        state.gradesStatus = grades_status;
        state.isAuthenticated = true; 
      })
      .addCase(fetchUserData.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload || 'Failed to fetch user data';
        // Do not change isAuthenticated here; only login/logout/explicit status check should.
        // If token is invalid, checkAuthStatus or next API call will fail.
      })
      
      // Check Auth Status
      .addCase(checkAuthStatus.pending, (state) => {
        state.isLoading = true;
      })
      .addCase(checkAuthStatus.fulfilled, (state, action) => {
        state.isLoading = false;
        state.isAuthInitialized = true;
        if (!action.payload) { // If checkAuthStatus resolved to false
          state.isAuthenticated = false;
          state.user = null; // Clear user data if not authenticated
          // Clear other sensitive data as well
          state.courses = null;
          state.calendarEvents = null;
          state.gradesData = null;
          state.gradesStatus = null;
        } else {
            state.isAuthenticated = true; // If fetchUserData succeeded within checkAuthStatus
        }
      })
      .addCase(checkAuthStatus.rejected, (state) => { // Should ideally not happen if catch block returns false
        state.isLoading = false;
        state.isAuthenticated = false;
        state.isAuthInitialized = true;
        state.user = null;
         state.courses = null;
        state.calendarEvents = null;
        state.gradesData = null;
        state.gradesStatus = null;
      })

      // Delete User Account
      .addCase(deleteUserAccount.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(deleteUserAccount.fulfilled, (state) => {
        // The logout action dispatched within the thunk already resets state.
        // state.isLoading will be false due to logout reducer.
        // state.isAuthenticated will be false.
        // state.user will be null.
        // No need to duplicate state changes here.
        state.error = null; // Ensure error is cleared on success
      })
      .addCase(deleteUserAccount.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload || 'Failed to delete account.';
        // User remains authenticated if deletion failed; error is shown.
      });
  }
});

export const { logout, setAuthInitialized } = authSlice.actions;
export default authSlice.reducer;