// app/hooks/useChat.ts
import { useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { AppDispatch, RootState } from '@/store';
import { addUserMessage, sendMessage as sendMessageThunk } from '@/store/slices/chatSlice';

export const useChat = () => {
  const dispatch = useDispatch<AppDispatch>();
  const [inputMessage, setInputMessage] = useState('');
  
  const { messages, isLoading, error } = useSelector((state: RootState) => state.chat);
  
  const sendMessage = async () => {
    if (!inputMessage.trim()) return;
    
    // Add user message to state
    dispatch(addUserMessage(inputMessage));
    
    // Save message to send to API
    const messageToSend = inputMessage;
    
    // Clear input field
    setInputMessage('');
    
    // Send message to API
    await dispatch(sendMessageThunk(messageToSend));
  };
  
  return {
    messages,
    isLoading,
    error,
    inputMessage,
    setInputMessage,
    sendMessage
  };
};