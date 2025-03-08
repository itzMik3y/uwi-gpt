import Markdown from 'react-markdown';
import autoScroller from '@/hooks/autoScroller';
import Spinner from '@/components/Blinker';
import userIcon from '@/assets/images/user.png';
import assistantIcon from '@/assets/images/uwi.png'; 
import errorIcon from '@/assets/images/wrong.svg';

function Messages({ messages, isLoading }) {
  const scrollContentRef = autoScroller(isLoading);
  
  return (
    <div ref={scrollContentRef} className='grow space-y-4'>
      {messages.map(({ role, content, loading, error }, idx) => (
        <div key={idx} className={`flex items-start gap-4 py-4 px-3 rounded-xl ${role === 'user' ? 'bg-primary-blue/10' : ''}`}>
          {role === 'user' && (
            <img
              className='h-[26px] w-[26px] shrink-0'
              src={userIcon}
              alt='user'
            />
          )}

          {role === 'assistant' && (
            <img
              className='h-[35px] w-[35px] shrink-0'
              src={assistantIcon}  
              alt='assistant'
            />
          )}
          
          <div>
            <div className='markdown-container'>
              {(loading && !content) ? <Spinner />
                : (role === 'assistant')
                  ? <Markdown>{content}</Markdown>
                  : <div className='whitespace-pre-line'>{content}</div>
              }
            </div>
            {error && (
              <div className={`flex items-center gap-1 text-sm text-error-red ${content && 'mt-2'}`}>
                <img className='h-5 w-5' src={errorIcon} alt='error' />
                <span>An error occured check if you have docker running qdrant, if you have torch enabled and if you have llama installed on your machine.</span>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export default Messages;