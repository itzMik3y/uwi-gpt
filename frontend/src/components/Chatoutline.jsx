import { useState } from 'react';
import { useImmer } from 'use-immer';
import api from '@/api';
import Messages from '@/components/Messages';
import Userinput from '@/components/Userinput';

function Chatoutline() {
  const [messages, setMessages] = useImmer([]);
  const [newMessage, setNewMessage] = useState('');

  const isLoading = messages.length && messages[messages.length - 1].loading;

  async function submitNewMessage() {
    const trimmedMessage = newMessage.trim();
    if (!trimmedMessage || isLoading) return;

    setMessages(draft => [...draft,
      { role: 'user', content: trimmedMessage },
      { role: 'assistant', content: '', sources: [], loading: true }
    ]);
    setNewMessage('');


    try {
      const data = await api.fetchMessage(trimmedMessage);  
      
      setMessages(draft => {
        draft[draft.length - 1].content = data.answer || "No answer provided";
        draft[draft.length - 1].loading = false;
      });
    } catch (err) {
      console.log(err);
      setMessages(draft => {
        draft[draft.length - 1].loading = false;
        draft[draft.length - 1].error = true;
      });
    }
  }

  return (
    <div className='relative grow flex flex-col gap-6 pt-6'>
      {messages.length === 0 && (
        <div className='mt-3 font-urbanist text-primary-blue text-xl font-light space-y-2'>
          <p>How can I help you with your UWI needs?</p>
        </div>
      )}
      <Messages
        messages={messages}
        isLoading={isLoading}
      />
      <Userinput
        newMessage={newMessage}
        isLoading={isLoading}
        setNewMessage={setNewMessage}
        submitNewMessage={submitNewMessage}
      />
    </div>
  );
}

export default Chatoutline;