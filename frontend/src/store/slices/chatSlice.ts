import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { Message, RagQueryRequest, RagQueryResponse } from '@/types/rag'; // Ensure RagQueryResponse is imported if used in sendMessage
import { ragClient } from '@/lib/api/ragClient'; // Ensure this path is correct
import { v4 as uuidv4 } from 'uuid';

// Define the state type
interface ChatState {
  messages: Message[];
  isLoading: boolean;
  isStreaming: boolean;
  error: string | null;
  streamCleanup: (() => void) | null; // To store the cleanup function from streamQuery
}

// Initial state
const initialState: ChatState = {
  messages: [],
  isLoading: false,
  isStreaming: false,
  error: null,
  streamCleanup: null,
};

// Define the payload type for thunks that send query and history
interface SendMessagePayload {
  query: string;
  history: Message[];
  filters?: RagQueryRequest['filters']; // Optional filters
}


// Async thunk for sending a message to the API (non-streaming)
export const sendMessage = createAsyncThunk<
  RagQueryResponse, // Return type from ragClient.sendQuery
  SendMessagePayload, // Updated payload type
  { rejectValue: string }
>(
  'chat/sendMessage',
  async ({ query, history, filters }, { rejectWithValue }) => { // Destructure payload
    try {
      // Pass query, history, and filters to ragClient
      const response = await ragClient.sendQuery(query, history, filters);
      return response;
    } catch (error) {
      if (error instanceof Error) {
        return rejectWithValue(error.message);
      }
      return rejectWithValue('An unknown error occurred while sending message');
    }
  }
);

// Async thunk for starting a streaming response
export const startStreamingResponse = createAsyncThunk<
  { messageId: string; cleanupFn: () => void }, // Fulfilled action payload type
  SendMessagePayload, // Updated payload type
  { dispatch: any; rejectValue: string } // Added AppDispatch type if available
>(
  'chat/startStreamingResponse',
  async ({ query, history, filters }, { dispatch, rejectWithValue }) => { // Destructure payload
    const botMessageId = uuidv4();
    
    // Dispatch an action to add an initial empty bot message to the UI
    dispatch(addBotStreamingMessage({ id: botMessageId, content: '' }));
    
    try {
      // Call ragClient.streamQuery with destructured query, history, and filters
      const cleanupFn = ragClient.streamQuery(
        query,
        history, // Pass the history
        (chunk) => { // onChunk
          dispatch(updateStreamingMessage({
            id: botMessageId,
            contentToAdd: chunk,
          }));
        },
        (error) => { // onError
          dispatch(streamingError({
            id: botMessageId,
            error: error.message,
          }));
          // No need to rejectWithValue here as onError handles state update
        },
        (processingTime, userContext) => { // onComplete
          dispatch(completeStreaming({
            id: botMessageId, // Pass ID to identify which message is complete
            processingTime,
            userContext
          }));
        },
        filters // Pass the filters
      );
      
      // Return the messageId and the cleanup function to be stored in state
      return { messageId: botMessageId, cleanupFn };
    } catch (error) {
      // This catch block might be for errors setting up the stream itself,
      // not for errors during streaming (which are handled by onError callback).
      if (error instanceof Error) {
        // Dispatch an error for the specific bot message if applicable
        dispatch(streamingError({ id: botMessageId, error: error.message }));
        return rejectWithValue(error.message);
      }
      dispatch(streamingError({ id: botMessageId, error: 'An unknown error occurred starting stream' }));
      return rejectWithValue('An unknown error occurred starting stream');
    }
  }
);

// Create the slice
const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    addUserMessage: (state, action: PayloadAction<string>) => {
      if (state.isStreaming && state.streamCleanup) {
        // If a stream is active, cancel it before adding a new user message
        // to prevent multiple bot responses or UI confusion.
        state.streamCleanup();
        state.streamCleanup = null;
        state.isStreaming = false;
        // Optionally, mark the last bot message as 'interrupted' or handle its state.
        const lastMessage = state.messages[state.messages.length -1];
        if(lastMessage && lastMessage.sender === 'bot' && !lastMessage.content.includes("Error:")) {
            // lastMessage.content += " (Interrupted)"; // Example
        }

      }
      const newMessage: Message = {
        id: uuidv4(),
        content: action.payload,
        sender: 'user',
        timestamp: new Date().toISOString(),
      };
      state.messages.push(newMessage);
      state.isLoading = true; // Set loading true when user sends a message
      state.error = null; // Clear previous errors
    },
    addBotMessage: (state, action: PayloadAction<string>) => { // For non-streaming welcome message
        const newMessage: Message = {
          id: uuidv4(),
          content: action.payload,
          sender: 'bot',
          timestamp: new Date().toISOString(),
        };
        state.messages.push(newMessage);
    },
    addBotStreamingMessage: (state, action: PayloadAction<{ id: string, content: string }>) => {
      const newMessage: Message = {
        id: action.payload.id,
        content: action.payload.content,
        sender: 'bot',
        timestamp: new Date().toISOString(),
      };
      state.messages.push(newMessage);
      state.isLoading = true; // Also set isLoading during streaming
      state.isStreaming = true;
      state.error = null;
    },
    updateStreamingMessage: (state, action: PayloadAction<{ id: string, contentToAdd: string }>) => {
      const { id, contentToAdd } = action.payload;
      const message = state.messages.find(msg => msg.id === id && msg.sender === 'bot');
      if (message) {
        message.content += contentToAdd;
      }
    },
    streamingError: (state, action: PayloadAction<{ id: string, error: string }>) => {
      const { id, error } = action.payload;
      state.error = error; // General error state
      state.isLoading = false;
      state.isStreaming = false;
      
      const message = state.messages.find(msg => msg.id === id && msg.sender === 'bot');
      if (message) {
        message.content = message.content ? message.content + `\n\nError: ${error}` : `Error: ${error}`;
      } else {
        // If the streaming message wasn't even added, create an error message
        state.messages.push({
            id: id, // Use the passed id or a new one
            content: `Error during streaming: ${error}`,
            sender: 'bot',
            timestamp: new Date().toISOString(),
        });
      }
      if (state.streamCleanup) {
        state.streamCleanup();
        state.streamCleanup = null;
      }
    },
    completeStreaming: (state, action: PayloadAction<{id: string, processingTime?: number, userContext?: any}>) => {
      // const { id, processingTime, userContext } = action.payload;
      // Find the message by id and mark it as complete if you have a flag for it.
      // const message = state.messages.find(msg => msg.id === id);
      // if (message) { /* update message if needed, e.g., message.isComplete = true */ }
      state.isLoading = false;
      state.isStreaming = false;
      state.streamCleanup = null;
      // You could store processingTime or userContext in the state if needed globally,
      // or attach it to the specific message.
    },
    clearMessages: (state) => {
      if (state.streamCleanup) {
        state.streamCleanup();
        state.streamCleanup = null;
      }
      state.messages = [];
      state.isLoading = false;
      state.isStreaming = false;
      state.error = null;
    },
    clearError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // Non-streaming sendMessage thunk
      .addCase(sendMessage.pending, (state) => {
        state.isLoading = true;
        state.isStreaming = false; // Ensure streaming is false
        state.error = null;
      })
      .addCase(sendMessage.fulfilled, (state, action: PayloadAction<RagQueryResponse>) => {
        state.isLoading = false;
        state.messages.push({
          id: uuidv4(),
          content: action.payload.answer,
          sender: 'bot',
          timestamp: new Date().toISOString(),
        });
        // You can also handle action.payload.context or action.payload.user_context here if needed
      })
      .addCase(sendMessage.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string || 'Failed to get a response';
        // Optionally add a bot message indicating the error
        state.messages.push({
            id: uuidv4(),
            content: `Error: ${state.error}`,
            sender: 'bot',
            timestamp: new Date().toISOString(),
        });
      })
      // Streaming startStreamingResponse thunk
      .addCase(startStreamingResponse.pending, (state) => {
        // isLoading and isStreaming are set by addBotStreamingMessage reducer
        // state.isLoading = true; 
        // state.isStreaming = true;
        state.error = null;
      })
      .addCase(startStreamingResponse.fulfilled, (state, action) => {
        // isLoading and isStreaming will be false once completeStreaming is called.
        // The primary role here is to store the cleanup function.
        state.streamCleanup = action.payload.cleanupFn;
      })
      .addCase(startStreamingResponse.rejected, (state, action) => {
        // Error handling is mostly done within the streamingError reducer,
        // but this catches errors from the thunk's rejectWithValue.
        state.isLoading = false;
        state.isStreaming = false;
        if (!state.error) { // If streamingError reducer didn't already set it
            state.error = action.payload as string || 'Failed to start streaming';
        }
         // Ensure a bot message reflects the error if not already handled
        const lastMessage = state.messages[state.messages.length - 1];
        if (!lastMessage || lastMessage.sender !== 'bot' || !lastMessage.content.includes("Error:")) {
            state.messages.push({
                id: uuidv4(),
                content: `Error: ${state.error}`,
                sender: 'bot',
                timestamp: new Date().toISOString(),
            });
        }
      });
  },
});

export const {
  addUserMessage,
  addBotMessage,
  addBotStreamingMessage,
  updateStreamingMessage,
  streamingError,
  completeStreaming,
  clearMessages,
  clearError,
} = chatSlice.actions;

export default chatSlice.reducer;
