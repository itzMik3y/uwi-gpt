// app/store/slices/chatSlice.ts
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { ragClient } from '@/lib/api/ragClient';

export interface Message {
  id: string;
  content: string;
  sender: 'user' | 'bot';
  timestamp: string;
}

interface ChatState {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
}

const initialState: ChatState = {
  messages: [
    {
      id: '1',
      content: 'Hello! I\'m your UWI-GPT advisor. How can I assist you today with your academic journey?',
      sender: 'bot',
      timestamp: new Date().toISOString()
    }
  ],
  isLoading: false,
  error: null
};

// Async thunk for sending a message and getting a response
export const sendMessage = createAsyncThunk(
  'chat/sendMessage',
  async (content: string, { rejectWithValue }) => {
    try {
      const response = await ragClient.sendQuery(content);
      return response;
    } catch (error) {
      if (error instanceof Error) {
        return rejectWithValue(error.message);
      }
      return rejectWithValue('An unknown error occurred');
    }
  }
);

const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    // Add user message to state
    addUserMessage: (state, action: PayloadAction<string>) => {
      const newMessage: Message = {
        id: Date.now().toString(),
        content: action.payload,
        sender: 'user',
        timestamp: new Date().toISOString()
      };
      state.messages.push(newMessage);
    },
    
    // Clear all messages (reset chat)
    clearMessages: (state) => {
      state.messages = [state.messages[0]]; // Keep the welcome message
      state.error = null;
    }
  },
  extraReducers: (builder) => {
    builder
      .addCase(sendMessage.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(sendMessage.fulfilled, (state, action) => {
        state.isLoading = false;
        // Add bot response to messages
        const botMessage: Message = {
          id: (Date.now() + 1).toString(),
          content: action.payload.answer,
          sender: 'bot',
          timestamp: new Date().toISOString()
        };
        state.messages.push(botMessage);
      })
      .addCase(sendMessage.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
        // Add error message
        const errorMessage: Message = {
          id: (Date.now() + 1).toString(),
          content: `Sorry, I encountered an error: ${action.payload}`,
          sender: 'bot',
          timestamp: new Date().toISOString()
        };
        state.messages.push(errorMessage);
      });
  }
});

export const { addUserMessage, clearMessages } = chatSlice.actions;
export default chatSlice.reducer;