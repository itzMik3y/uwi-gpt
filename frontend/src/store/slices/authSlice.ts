// src/store/slices/authSlice.ts
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { moodleApi, TOKEN_STORAGE_KEY, REFRESH_TOKEN_STORAGE_KEY, TOKEN_EXPIRY_KEY } from '@/lib/api/moodleClient';
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

// Login thunk - handles the initial login process
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

// Fetch user data thunk - gets user data after login
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

// Check auth status thunk - verifies if the current token is valid
export const checkAuthStatus = createAsyncThunk<
  boolean,
  void,
  { rejectValue: string }
>('auth/checkStatus', async (_, { dispatch, rejectWithValue }) => {
  try {
    // Check if access token exists and is valid
    if (!moodleApi.isAuthenticated()) {
      return false;
    }
    
    // Try to fetch user data to validate the token
    await dispatch(fetchUserData());
    return true;
  } catch (err: any) {
    // If error occurs, token might be invalid
    return false;
  }
});

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
      state.isLoading = false;
      state.error = null;
      
      // Clear tokens from API client and localStorage
      moodleApi.clearTokens();
    },
    
    // Mark authentication as initialized (whether successful or not)
    setAuthInitialized(state, action: PayloadAction<boolean>) {
      state.isAuthInitialized = action.payload;
    }
  },
  extraReducers: (builder) => {
    // Login
    builder
      .addCase(loginUser.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(loginUser.fulfilled, (state, action) => {
        state.isLoading = false;
        state.isAuthenticated = true;
        state.error = null;
        state.isAuthInitialized = true;
        
        // Note: We don't set user data here yet - that happens in fetchUserData
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
        state.authTokens = moodle_data.auth_tokens;
        state.gradesData = grades_data;
        state.gradesStatus = grades_status;
        state.isAuthenticated = true;
      })
      .addCase(fetchUserData.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload || 'Failed to fetch user data';
        
        // Keep isAuthenticated unchanged here - only loginUser and logout should change this
      })
      
      // Check Auth Status
      .addCase(checkAuthStatus.pending, (state) => {
        state.isLoading = true;
      })
      .addCase(checkAuthStatus.fulfilled, (state, action) => {
        state.isLoading = false;
        state.isAuthInitialized = true;
        
        // If status check returns false, we explicitly set isAuthenticated to false
        if (!action.payload) {
          state.isAuthenticated = false;
          state.user = null;
          state.courses = null;
          state.calendarEvents = null;
          state.authTokens = null;
          state.gradesData = null;
          state.gradesStatus = null;
        }
      })
      .addCase(checkAuthStatus.rejected, (state) => {
        state.isLoading = false;
        state.isAuthenticated = false;
        state.isAuthInitialized = true;
        state.user = null;
        state.courses = null;
        state.calendarEvents = null;
        state.authTokens = null;
        state.gradesData = null;
        state.gradesStatus = null;
      });
  }
});

export const { logout, setAuthInitialized } = authSlice.actions;
export default authSlice.reducer;