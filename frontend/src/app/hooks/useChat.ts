// app/hooks/useChat.ts
import { useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { AppDispatch, RootState } from '@/store';
import { 
  addUserMessage, 
  sendMessage as sendMessageThunk, // This likely needs to accept history
  startStreamingResponse // This likely needs to accept history
} from '@/store/slices/chatSlice';
import { Message } from '@/types/rag'; // Assuming Message type is here or accessible

export const useChat = () => {
  const dispatch = useDispatch<AppDispatch>();
  const [inputMessage, setInputMessage] = useState('');
  const [useStreaming, setUseStreaming] = useState(true); // Default to streaming

  // Get messages from Redux store, these will serve as history
  const { messages, isLoading, isStreaming, error } = useSelector((state: RootState) => state.chat);

  const sendMessage = async () => {
    if (!inputMessage.trim()) return;
    
    // Add user message to state
    dispatch(addUserMessage(inputMessage));
    
    // Save message to send to API
    const messageToSend = inputMessage;
    
    // Clear input field
    setInputMessage('');

    // Prepare history: Send all current messages.
    // You might want to limit the number of messages sent as history
    // to avoid overly large requests or token limits with the LLM.
    // For example: const conversationHistory = messages.slice(-10);
    const conversationHistory: Message[] = [...messages]; 
    // Add the new user message to the history being sent,
    // so the backend has the absolute latest state before its response.
    // Note: The addUserMessage dispatch above already adds it to the Redux state `messages`,
    // so `conversationHistory` will include it if `messages` selector updates immediately.
    // If there's a delay or you want to be explicit:
    // conversationHistory.push({ id: 'temp-user', content: messageToSend, sender: 'user', timestamp: new Date().toISOString() });
    // However, it's generally better to rely on the Redux state `messages` as the source of truth.

    // Choose streaming or non-streaming based on the setting
    if (useStreaming) {
      // Pass the current query and the conversation history
      // @ts-ignore // Assuming startStreamingResponse will be updated to accept history
      await dispatch(startStreamingResponse({ query: messageToSend, history: conversationHistory }));
    } else {
      // Pass the current query and the conversation history
      // @ts-ignore // Assuming sendMessageThunk will be updated to accept history
      await dispatch(sendMessageThunk({ query: messageToSend, history: conversationHistory }));
    }
  };

  // Toggle streaming on/off
  const toggleStreaming = () => {
    setUseStreaming(prev => !prev);
  };

  return {
    messages,
    isLoading,
    isStreaming, 
    error,
    inputMessage,
    setInputMessage,
    sendMessage,
    useStreaming,
    toggleStreaming
  };
};
