import autoSizer from '@/hooks/autoSizer';
import sendIcon from '@/assets/images/send.svg';

function Userinput({ newMessage, isLoading, setNewMessage, submitNewMessage }) {
  const textareaRef = autoSizer(newMessage);

  function handleKeyDown(e) {
    if (e.keyCode === 13 && !e.shiftKey && !isLoading) {
      e.preventDefault();
      submitNewMessage();
    }
  }

  return (
    <div className="sticky bottom-0 py-4 bg-gray-900">
      <div className="p-1.5 bg-primary-blue/35 rounded-md z-50 font-mono origin-bottom animate-chat duration-400">
        <div className="pr-0.5 relative shrink-0 rounded-md overflow-hidden ring-primary-blue ring-1 focus-within:ring-2 transition-all">
          <textarea
            className="block w-full max-h-[140px] py-2 px-4 pr-11 bg-gray-900 text-primary-blue placeholder:text-primary-blue/70 rounded-md resize-none placeholder:leading-4 placeholder:-translate-y-1 sm:placeholder:leading-normal sm:placeholder:translate-y-0 focus:outline-none"
            ref={textareaRef}
            rows="1"
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter your message..."
          />
          <button
            className="rounded-md absolute top-1/2 -translate-y-1/2 right-3 p-1  hover:bg-primary-blue/20"
            onClick={submitNewMessage}
          >
            <img src={sendIcon} alt="send" />
          </button>
        </div>
      </div>
    </div>
  );
}

export default Userinput;
