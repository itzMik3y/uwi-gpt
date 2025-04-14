// store/slices/chatSlice.ts

import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { Message } from '@/types/rag';
import { ragClient } from '@/lib/api/ragClient';
import { v4 as uuidv4 } from 'uuid'; // You'll need to install this package

// Define the state type
interface ChatState {
  messages: Message[];
  isLoading: boolean;
  isStreaming: boolean;
  error: string | null;
  streamCleanup: (() => void) | null;
}

// Initial state
const initialState: ChatState = {
  messages: [],
  isLoading: false,
  isStreaming: false,
  error: null,
  streamCleanup: null,
};

// Async thunk for sending a message to the API (non-streaming)
export const sendMessage = createAsyncThunk(
  'chat/sendMessage',
  async (message: string, { rejectWithValue }) => {
    try {
      const response = await ragClient.sendQuery(message);
      return response;
    } catch (error) {
      if (error instanceof Error) {
        return rejectWithValue(error.message);
      }
      return rejectWithValue('An unknown error occurred');
    }
  }
);

// Special action for adding a streaming bot message (initially empty)
export const startStreamingResponse = createAsyncThunk(
  'chat/startStreamingResponse',
  async (message: string, { dispatch, rejectWithValue }) => {
    const botMessageId = uuidv4();
    
    // First create an empty bot message in the state
    dispatch(addBotStreamingMessage({ id: botMessageId, content: '' }));
    
    try {
      // Start the streaming connection 
      const cleanupFn = ragClient.streamQuery(
        message,
        // On each chunk, update the bot message content
        (chunk) => {
          dispatch(updateStreamingMessage({
            id: botMessageId,
            contentToAdd: chunk,
          }));
        },
        // On error
        (error) => {
          dispatch(streamingError({
            id: botMessageId,
            error: error.message
          }));
        },
        // On complete
        () => {
          dispatch(completeStreaming(botMessageId));
        }
      );
      
      // Return the message ID and cleanup function
      return {
        messageId: botMessageId,
        cleanupFn
      };
    } catch (error) {
      if (error instanceof Error) {
        return rejectWithValue(error.message);
      }
      return rejectWithValue('An unknown error occurred');
    }
  }
);

// Create the slice
const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    // Add a user message
    addUserMessage: (state, action: PayloadAction<string>) => {
      const newMessage: Message = {
        id: uuidv4(),
        content: action.payload,
        sender: 'user',
        timestamp: new Date().toISOString(),
      };
      state.messages.push(newMessage);
    },
    
    // Add an empty bot message for streaming
    addBotStreamingMessage: (state, action: PayloadAction<{ id: string, content: string }>) => {
      const newMessage: Message = {
        id: action.payload.id,
        content: action.payload.content,
        sender: 'bot',
        timestamp: new Date().toISOString(),
      };
      state.messages.push(newMessage);
      state.isStreaming = true;
    },
    
    // Update a streaming message with new content
    updateStreamingMessage: (state, action: PayloadAction<{ id: string, contentToAdd: string }>) => {
      const { id, contentToAdd } = action.payload;
      const message = state.messages.find(msg => msg.id === id);
      if (message) {
        message.content += contentToAdd;
      }
    },
    
    // Handle streaming errors
    streamingError: (state, action: PayloadAction<{ id: string, error: string }>) => {
      const { id, error } = action.payload;
      state.error = error;
      state.isStreaming = false;
      
      // Optionally append error message to the bot message
      const message = state.messages.find(msg => msg.id === id);
      if (message) {
        message.content += `\n\nError: ${error}`;
      }
      
      // Clean up the streaming connection
      if (state.streamCleanup) {
        state.streamCleanup();
        state.streamCleanup = null;
      }
    },
    
    // Mark streaming as complete
    completeStreaming: (state, action: PayloadAction<string>) => {
      state.isStreaming = false;
      state.streamCleanup = null;
    },
    
    // Clear all messages
    clearMessages: (state) => {
      state.messages = [];
      state.error = null;
      
      // If there's an active stream, clean it up
      if (state.streamCleanup) {
        state.streamCleanup();
        state.streamCleanup = null;
      }
    },
    
    // Clear any error
    clearError: (state) => {
      state.error = null;
    },

    addBotMessage: (state, action: PayloadAction<string>) => {
      const newMessage: Message = {
        id: uuidv4(),
        content: action.payload,
        sender: 'bot',
        timestamp: new Date().toISOString(),
      };
      state.messages.push(newMessage);
    },
  },
  extraReducers: (builder) => {
    builder
      // Non-streaming message handler
      .addCase(sendMessage.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(sendMessage.fulfilled, (state, action) => {
        state.isLoading = false;
        // Add bot response as a new message
        state.messages.push({
          id: uuidv4(),
          content: action.payload.answer,
          sender: 'bot',
          timestamp: new Date().toISOString(),
        });
      })
      .addCase(sendMessage.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string || 'Failed to get a response';
      })
      
      // Streaming message handlers
      .addCase(startStreamingResponse.pending, (state) => {
        state.error = null;
      })
      .addCase(startStreamingResponse.fulfilled, (state, action) => {
        // Store the cleanup function
        state.streamCleanup = action.payload.cleanupFn;
      })
      .addCase(startStreamingResponse.rejected, (state, action) => {
        state.isStreaming = false;
        state.error = action.payload as string || 'Failed to start streaming';
      });
  },
});

// Export actions
export const {
  addUserMessage,
  addBotStreamingMessage,
  updateStreamingMessage,
  streamingError,
  completeStreaming,
  clearMessages,
  clearError,
  addBotMessage
} = chatSlice.actions;

// Export reducer
export default chatSlice.reducer;