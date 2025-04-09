// src/store/slices/authSlice.ts
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { moodleApi } from '@/lib/api/moodleClient';
import { MoodleLoginRequest, MoodleLoginResponse } from '@/types/moodle';
import { MoodleCourse,MoodleUser,MoodleAuthTokens } from '@/types/moodle';

interface AuthState {
  isAuthenticated: boolean;
  user: MoodleUser | null;       // Store the complete user info object
  courses: MoodleCourse[] | null; // Store courses data (if needed)
  calendarEvents: any | null;     // Type as needed (or create an interface)
  authTokens: MoodleAuthTokens | null;
  isLoading: boolean;
  error: string | null;
}

const initialState: AuthState = {
  isAuthenticated: false,
  user: null,
  courses: null,
  calendarEvents: null,
  authTokens: null,
  isLoading: false,
  error: null
};

// Define localStorage keys
const USERNAME_KEY = 'moodle_username';
const PASSWORD_KEY = 'moodle_password'; // !!! INSECURE - FOR DEMONSTRATION ONLY !!!
const TOKEN_KEY = 'moodle_auth_token'; // If you use tokens

export const loginUser = createAsyncThunk(
  'auth/login',
  async (credentials: MoodleLoginRequest, { rejectWithValue }) => {
    try {
      const response = await moodleApi.login(credentials);
      // Return the complete response data so you can later store it in Redux state.
      return {
        user: response.user_info,          // Contains name, email, student_id, etc.
        courses: response.courses,           // Contains list of courses
        calendarEvents: response.calendar_events, // Contains calendar events
        authTokens: response.auth_tokens     // Contains login_token, sesskey, and moodle_session
      };
    } catch (error: any) {
      const errorMessage = error?.response?.data?.error || error?.message || 'Login failed';
      return rejectWithValue(errorMessage);
    }
  }
);


const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    logout: (state) => {
      state.isAuthenticated = false;
      state.user = null;
      state.courses = null;
      state.calendarEvents = null;
      state.authTokens = null;
      // Also clear tokens from API client and localStorage:
      moodleApi.clearToken();
      localStorage.removeItem('moodle_auth_token');
      localStorage.removeItem('moodle_username');
      localStorage.removeItem('moodle_password');
    },
    initializeAuth: (state) => {
      // Read token and username from localStorage if available.
      const token = localStorage.getItem('moodle_auth_token');
      const username = localStorage.getItem('moodle_username');
      if (token && username) {
        state.authTokens = { login_token: token } as MoodleAuthTokens;
        // Optionally you could also retrieve more detailed user data from a stored JSON.
        state.user = { name: '', email: username, student_id: '' };
        state.isAuthenticated = true;
        moodleApi.setToken(token);
      } else {
        state.isAuthenticated = false;
        state.user = null;
        state.authTokens = null;
      }
    }
  },
  extraReducers: (builder) => {
    builder
      .addCase(loginUser.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(loginUser.fulfilled, (state, action) => {
        state.isLoading = false;
        state.isAuthenticated = true;
        state.user = action.payload.user;
        state.courses = action.payload.courses.courses; // adjust if your nested structure differs
        state.calendarEvents = action.payload.calendarEvents;
        state.authTokens = action.payload.authTokens;
        
        // Optionally store credentials in localStorage for auto population
        localStorage.setItem('moodle_username', action.payload.user.student_id);
        localStorage.setItem('moodle_password', action.meta.arg.password);
        // If you use a real token:
        // localStorage.setItem('moodle_auth_token', action.payload.authTokens.login_token);

        // Update API client with token if applicable:
        // moodleApi.setToken(action.payload.authTokens.login_token);
      })
      .addCase(loginUser.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
        state.isAuthenticated = false;
        state.user = null;
        state.authTokens = null;
      });
  }
});

export const { logout, initializeAuth } = authSlice.actions;
export default authSlice.reducer;
