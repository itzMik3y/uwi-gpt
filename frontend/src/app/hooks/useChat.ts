// app/hooks/useChat.ts

import { useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { AppDispatch, RootState } from '@/store';
import { 
  addUserMessage, 
  sendMessage as sendMessageThunk,
  startStreamingResponse
} from '@/store/slices/chatSlice';

export const useChat = () => {
  const dispatch = useDispatch<AppDispatch>();
  const [inputMessage, setInputMessage] = useState('');
  const [useStreaming, setUseStreaming] = useState(true); // Default to streaming

  const { messages, isLoading, isStreaming, error } = useSelector((state: RootState) => state.chat);

  const sendMessage = async () => {
    if (!inputMessage.trim()) return;
   
    // Add user message to state
    dispatch(addUserMessage(inputMessage));
   
    // Save message to send to API
    const messageToSend = inputMessage;
   
    // Clear input field
    setInputMessage('');
   
    // Choose streaming or non-streaming based on the setting
    if (useStreaming) {
      // Use streaming response
      await dispatch(startStreamingResponse(messageToSend));
    } else {
      // Use traditional non-streaming response
      await dispatch(sendMessageThunk(messageToSend));
    }
  };

  // Toggle streaming on/off
  const toggleStreaming = () => {
    setUseStreaming(prev => !prev);
  };

  return {
    messages,
    isLoading,
    isStreaming, // Add this to expose streaming state to UI
    error,
    inputMessage,
    setInputMessage,
    sendMessage,
    useStreaming,
    toggleStreaming
  };
};