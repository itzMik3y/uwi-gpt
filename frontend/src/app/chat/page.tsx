"use client"

import { useState, useRef, useEffect } from "react"
import Link from "next/link"
import Image from "next/image"
import { usePathname } from "next/navigation"
import { 
  GraduationCap, 
  Calendar, 
  Heart, 
  HelpCircle, 
  ChevronLeft,
  ChevronRight,
  Paperclip,
  Send,
  BookOpen,
  FileText,
  School,
  User,
  Clock,
  Zap,
  LightbulbIcon,
  Sparkles
} from "lucide-react"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { motion, AnimatePresence } from "framer-motion"
import { useChat } from "@/app/hooks/useChat" // This hook is updated
import { useSelector, useDispatch } from "react-redux"
import { RootState } from "@/store"
import ReactMarkdown from "react-markdown"
import { addBotMessage } from "@/store/slices/chatSlice"
import { Layout } from "../components/layout/Layout"
import { Message } from "@/types/rag"; // Ensure Message type is imported if used directly

// Define interface for nav items and quick action items
interface NavItem {
  label: string;
  icon: React.ReactNode;
  path: string;
  active?: boolean;
  hasArrow?: boolean;
}

// Chat message animation variants
const chatItemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({ // Added type for i
    opacity: 1,
    y: 0,
    transition: {
      delay: i * 0.1,
      duration: 0.3,
    }
  })
};

// Message component that handles markdown rendering for bot messages
const MessageContent = ({ 
  content, 
  sender, 
  isStreaming 
}: { 
  content: string, 
  sender: 'user' | 'bot',
  isStreaming?: boolean 
}) => {
  if (sender === 'user') {
    return <p>{content}</p>;
  }
  
  // Function to check if content is likely HTML
  const isHtmlContent = (str: string) => {
    return /<\/?[a-z][\s\S]*>/i.test(str);
  };
  
  return (
    <div className="prose max-w-none text-gray-800 dark:text-gray-200">
      {isHtmlContent(content) ? (
        <div dangerouslySetInnerHTML={{ __html: content }} />
      ) : (
        <ReactMarkdown>
          {content}
        </ReactMarkdown>
      )}
      {isStreaming && (
        <div className="inline-flex space-x-1 mt-1">
          <div className="h-2 w-2 animate-bounce rounded-full bg-gray-500 dark:bg-gray-400" style={{ animationDelay: '0ms' }}></div>
          <div className="h-2 w-2 animate-bounce rounded-full bg-gray-500 dark:bg-gray-400" style={{ animationDelay: '200ms' }}></div>
          <div className="h-2 w-2 animate-bounce rounded-full bg-gray-500 dark:bg-gray-400" style={{ animationDelay: '400ms' }}></div>
        </div>
      )}
    </div>
  );
};

export default function ChatPage() {
  const [infoSectionCollapsed, setInfoSectionCollapsed] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const chatContainerRef = useRef<HTMLDivElement>(null)
  const dispatch = useDispatch();
  
  // Get user from Redux store
  const user = useSelector((state: RootState) => state.auth.user);
  
  // Get full name and create initials
  const fullName = user?.name || "Sarah Johnson";
  
  // Create initials for avatar fallback
  const getInitials = (name: string) => {
    const names = name.split(' ');
    if (names.length >= 2) {
      return `${names[0][0]}${names[1][0]}`.toUpperCase();
    }
    return name.substring(0, 2).toUpperCase();
  };
  
  const userInitials = getInitials(fullName);
  
  // Use our custom hook for chat functionality with streaming
  const { 
    messages, 
    isLoading, 
    isStreaming, 
    error, 
    inputMessage, 
    setInputMessage, 
    sendMessage, // This now sends history implicitly via useChat
    useStreaming,
    toggleStreaming
  } = useChat();
  
  const hasDispatchedWelcomeRef = useRef(false);

  useEffect(() => {
    // Bail out if there's already messages or we don't have a user yet
    if (!user || messages.length > 0 || hasDispatchedWelcomeRef.current) return;

    // Extract first name
    const firstName = user.name?.split(" ")[0] ?? "User";

    // Define multiple greeting templates
    const greetingTemplates = [
      (name: string) => `Hello ${name}! I'm your UWI academic advisor. How can I assist you today?`,
      (name: string) => `Welcome ${name}, how can I help you with your academic needs?`,
      (name: string) => `Hi ${name}! How may I help you with your studies today?`,
    ];

    // Pick a random greeting
    const randomIndex = Math.floor(Math.random() * greetingTemplates.length);
    const greetingMessage = greetingTemplates[randomIndex](firstName);

    // Dispatch once
    dispatch(addBotMessage(greetingMessage));
    hasDispatchedWelcomeRef.current = true;
  }, [user, messages, dispatch]);

  
  // Auto-scroll to bottom when new messages arrive or during streaming
  useEffect(() => {
    if (messagesEndRef.current && chatContainerRef.current) {
      chatContainerRef.current.scrollTo({
        top: chatContainerRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [messages, isStreaming]); // isStreaming will trigger scroll on new chunks
  
  // Ensure the chat container is properly sized based on viewport
  useEffect(() => {
    const resizeChat = () => {
      if (chatContainerRef.current) {
        const viewportHeight = window.innerHeight;
        // Approximate heights - adjust these values based on your actual layout
        const headerHeight = document.querySelector('header')?.offsetHeight || 70; // Dynamically get header height or fallback
        const inputSection = document.getElementById('chat-input-section');
        const inputSectionHeight = inputSection?.offsetHeight || 80; 
        const infoSection = document.getElementById('info-section-collapsible');
        const infoSectionHeight = !infoSectionCollapsed && infoSection ? infoSection.offsetHeight : 0;
        
        // Calculate available height for chat container
        // Subtract a small buffer for padding/margins if needed
        const buffer = 20; 
        const availableHeight = viewportHeight - headerHeight - inputSectionHeight - infoSectionHeight - buffer;
        
        // Set min-height to ensure it doesn't get too small, and max-height for overall layout
        chatContainerRef.current.style.height = `${Math.max(300, availableHeight)}px`;
      }
    };
    
    resizeChat(); // Initial call
    window.addEventListener('resize', resizeChat);
    
    // Resize when info section collapses/expands, wait for animation
    const resizeTimeout = setTimeout(resizeChat, 350); 
    
    return () => {
      window.removeEventListener('resize', resizeChat);
      clearTimeout(resizeTimeout);
    };
  }, [infoSectionCollapsed]);
  
  // Handle pressing Enter key
  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      e.stopPropagation(); // Important to prevent other handlers if any
      sendMessage();
    }
  };
  
  // Quick Actions sidebar items
  const quickActions = [
    { 
      label: "Courses", 
      icon: <BookOpen className="h-4 w-4" />, 
      bgColor: "bg-blue-100 dark:bg-blue-800",
      textColor: "text-blue-700 dark:text-blue-200",
      hoverColor: "hover:bg-blue-200 dark:hover:bg-blue-700"
    },
    // ... other actions with dark mode classes
     { 
      label: "Grades", 
      icon: <GraduationCap className="h-4 w-4" />, 
      bgColor: "bg-purple-100 dark:bg-purple-800",
      textColor: "text-purple-700 dark:text-purple-200",
      hoverColor: "hover:bg-purple-200 dark:hover:bg-purple-700"
    },
    { 
      label: "Schedule", 
      icon: <Calendar className="h-4 w-4" />, 
      bgColor: "bg-green-100 dark:bg-green-800",
      textColor: "text-green-700 dark:text-green-200",
      hoverColor: "hover:bg-green-200 dark:hover:bg-green-700"
    },
    { 
      label: "Help", 
      icon: <HelpCircle className="h-4 w-4" />, 
      bgColor: "bg-amber-100 dark:bg-amber-800",
      textColor: "text-amber-700 dark:text-amber-200",
      hoverColor: "hover:bg-amber-200 dark:hover:bg-amber-700"
    },
  ]
  
  // Recent Chats items
  const recentChats = [
    { 
      title: "Course Registration Help", 
      time: "2h ago",
      active: true
    },
    // ... other chats
    { 
      title: "GPA Calculator", 
      time: "Yesterday",
      active: false
    },
    { 
      title: "Exam Schedule", 
      time: "2d ago",
      active: false
    },
  ]
  
  // Suggested Topics
  const suggestedTopics = [
    "Course Prerequisites",
    "Registration Deadlines",
    "GPA Calculator"
  ]

  const toggleInfoSection = () => {
    setInfoSectionCollapsed(!infoSectionCollapsed)
  }

  // Global CSS to hide scrollbars (optional, consider accessibility)
  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = `
      /* Hide scrollbar for Chrome, Safari and Opera */
      ::-webkit-scrollbar {
        display: none;
      }
      /* Hide scrollbar for IE, Edge and Firefox */
      * {
        -ms-overflow-style: none;  /* IE and Edge */
        scrollbar-width: none;  /* Firefox */
      }
    `;
    document.head.appendChild(style);
    return () => {
      document.head.removeChild(style);
    };
  }, []);
  
  return (
    <Layout> {/* Assuming Layout handles overall page structure including header */}
    <div className="container mx-auto py-4 px-2 h-[calc(100vh-var(--header-height,70px))] flex flex-col">
      {/* Main Chat Area with Border and Shadow */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm flex flex-col flex-grow overflow-hidden">
        {/* Chat messages - This div scrolls */}
        <div 
          ref={chatContainerRef}
          className="flex-1 overflow-y-auto px-6 py-4 scroll-smooth" 
          style={{ 
            scrollbarWidth: 'none', 
            overscrollBehavior: 'contain',
            msOverflowStyle: 'none'
          }}
        >
          <div className="space-y-4 min-h-full">
            {messages.map((msg, index) => {
              const isLastBotMessage = msg.sender === 'bot' && index === messages.length - 1;
              const isCurrentlyStreaming = isLastBotMessage && isStreaming;
              
              return (
                <motion.div 
                  key={msg.id}
                  className={`flex items-start ${msg.sender === 'user' ? 'justify-end' : 'justify-start'} w-full`}
                  custom={index}
                  initial="hidden"
                  animate="visible"
                  variants={chatItemVariants}
                >
                  {msg.sender === 'bot' ? (
                    <>
                      <div className="flex-shrink-0 mr-2">
                        <Image 
                          src="/uwi-logo.png" 
                          alt="UWI-GPT" 
                          width={32} 
                          height={32} 
                          className="w-8 h-8 rounded-full" // Added rounded-full
                        />
                      </div>
                      <div className="bg-blue-50 dark:bg-blue-900 text-gray-800 dark:text-gray-100 rounded-2xl rounded-tl-none p-4 max-w-[70%] shadow">
                        <MessageContent 
                          content={msg.content} 
                          sender={msg.sender} 
                          isStreaming={isCurrentlyStreaming}
                        />
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-2xl rounded-tr-none p-4 max-w-[70%] shadow">
                        <MessageContent 
                          content={msg.content} 
                          sender={msg.sender}
                        />
                      </div>
                      <div className="flex-shrink-0 ml-2">
                        <Avatar className="w-8 h-8">
                          <AvatarImage src={user?.profileimageurl || "/avatar.png"} alt={fullName} />
                          <AvatarFallback>{userInitials}</AvatarFallback>
                        </Avatar>
                      </div>
                    </>
                  )}
                </motion.div>
              );
            })}
                
            {/* Typing indicator for non-streaming loading */}
            {isLoading && !isStreaming && (
              <motion.div 
                className="flex items-start space-x-2"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
              >
                <div className="flex-shrink-0">
                  <Image 
                    src="/uwi-logo.png" 
                    alt="UWI-GPT" 
                    width={32} 
                    height={32} 
                    className="w-8 h-8 rounded-full"
                  />
                </div>
                <div className="bg-gray-100 dark:bg-gray-700 rounded-full px-4 py-2 shadow">
                  <div className="flex space-x-1">
                    <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400 dark:bg-gray-500" style={{ animationDelay: '0ms' }}></div>
                    <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400 dark:bg-gray-500" style={{ animationDelay: '200ms' }}></div>
                    <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400 dark:bg-gray-500" style={{ animationDelay: '400ms' }}></div>
                  </div>
                </div>
              </motion.div>
            )}
                
            {/* Show error message if any */}
            {error && (
              <motion.div 
                className="flex items-start space-x-2"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
              >
                <div className="flex-shrink-0">
                  <div className="w-8 h-8 bg-red-600 rounded-full flex items-center justify-center">
                    <User className="h-4 w-4 text-white" /> {/* Changed to User, or use an Error icon */}
                  </div>
                </div>
                <div className="bg-red-50 dark:bg-red-900 border border-red-200 dark:border-red-700 text-red-700 dark:text-red-200 rounded-2xl rounded-tl-none p-4 shadow">
                  <p className="font-medium">Error</p>
                  <p>{error}</p>
                </div>
              </motion.div>
            )}
                
            {/* Invisible element to scroll to */}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Bottom Panel with collapsible Info Section */}
        {/* Assign an ID for height calculation */}
        <div id="chat-input-section" className="border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 relative flex-shrink-0">
          {/* Collapse/Expand button */}
          <div className="absolute left-1/2 -top-3 transform -translate-x-1/2 z-10">
            <Button 
              variant="ghost" 
              size="icon" 
              className="flex h-6 w-6 items-center justify-center rounded-full border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 shadow-sm hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-500 dark:text-gray-400"
              onClick={toggleInfoSection}
              aria-label={infoSectionCollapsed ? "Expand info section" : "Collapse info section"}
            >
              <motion.div
                animate={{ rotate: infoSectionCollapsed ? 0 : 180 }} // Adjusted rotation for up/down arrow illusion
                transition={{ 
                  duration: 0.3, 
                  ease: "easeInOut"
                }}
              >
                <ChevronRight className={`h-4 w-4 transform ${infoSectionCollapsed ? 'rotate-90' : '-rotate-90'}`} />
              </motion.div>
            </Button>
          </div>

          {/* Info Section (collapsible) - Assign an ID for height calculation */}
          <AnimatePresence>
            {!infoSectionCollapsed && (
              <motion.div 
                id="info-section-collapsible"
                className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 border-b border-gray-200 dark:border-gray-700 w-full bg-gray-100 dark:bg-gray-750" // Slightly different bg
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ 
                  duration: 0.3, 
                  ease: "easeInOut"
                }}
              >
                {/* Recent Chats */}
                <div className="bg-white dark:bg-gray-800 p-3 rounded-lg shadow-sm overflow-hidden">
                  <h3 className="text-sm font-semibold mb-2 flex items-center text-gray-700 dark:text-gray-300">
                    <Clock className="mr-2 h-4 w-4 text-blue-600 dark:text-blue-400" />
                    Recent Chats
                  </h3>
                  <div className="space-y-1.5 max-h-24 overflow-y-auto" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
                    {recentChats.map((chat, index) => (
                      <div 
                        key={index}
                        className={`text-xs p-2 rounded cursor-pointer ${chat.active ? 'bg-blue-50 dark:bg-blue-900 text-blue-700 dark:text-blue-200' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'} ${chat.active ? 'hover:bg-blue-100 dark:hover:bg-blue-800' : 'hover:bg-gray-200 dark:hover:bg-gray-600'}`}
                      >
                        {chat.title} - <span className="text-gray-500 dark:text-gray-400 text-xs">{chat.time}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Quick Actions */}
                <div className="bg-white dark:bg-gray-800 p-3 rounded-lg shadow-sm">
                  <h3 className="text-sm font-semibold mb-2 flex items-center text-gray-700 dark:text-gray-300">
                    <Zap className="mr-2 h-4 w-4 text-amber-500 dark:text-amber-400" />
                    Quick Actions
                  </h3>
                  <div className="grid grid-cols-2 gap-2">
                    {quickActions.map((action, index) => (
                      <button 
                        key={index}
                        className={`text-xs px-2 py-1.5 ${action.bgColor} ${action.textColor} rounded-md ${action.hoverColor} flex items-center justify-center transition-colors duration-150`}
                      >
                        {action.icon}
                        <span className="ml-1.5">{action.label}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Suggested Topics */}
                <div className="bg-white dark:bg-gray-800 p-3 rounded-lg shadow-sm overflow-hidden">
                  <h3 className="text-sm font-semibold mb-2 flex items-center text-gray-700 dark:text-gray-300">
                    <LightbulbIcon className="mr-2 h-4 w-4 text-yellow-500 dark:text-yellow-400" />
                    Suggested Topics
                  </h3>
                  <div className="space-y-1.5 max-h-24 overflow-y-auto" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
                    {suggestedTopics.map((topic, index) => (
                      <button 
                        key={index}
                        className="w-full text-left text-xs px-2 py-1.5 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors duration-150"
                        onClick={() => {
                            setInputMessage(topic);
                            // Optionally send message immediately: sendMessage(); 
                            // but usually user confirms by pressing send.
                        }}
                      >
                        {topic}
                      </button>
                    ))}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          
          {/* Message input - Fixed at bottom */}
          <div className="p-4 flex-shrink-0">
            <div className="flex items-center space-x-2 md:space-x-4">
              <div className="flex-1 relative">
                <Input
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyDown={handleKeyPress}
                  placeholder="Type your question here..."
                  className="w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400"
                  disabled={isLoading || isStreaming}
                />
                <div className="absolute right-2 top-1/2 transform -translate-y-1/2 flex items-center space-x-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 h-8 w-8 flex items-center justify-center"
                    onClick={toggleStreaming}
                    title={useStreaming ? "Turn off streaming" : "Turn on streaming"}
                  >
                    <Sparkles className={`h-5 w-5 ${useStreaming ? 'text-yellow-500 dark:text-yellow-400' : 'text-gray-400 dark:text-gray-500'}`} />
                  </Button>
                  
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 h-8 w-8 flex items-center justify-center"
                    // Add onClick handler for paperclip if you implement file uploads
                  >
                    <Paperclip className="h-5 w-5" />
                  </Button>
                </div>
              </div>
              
              <Button
                className="px-4 py-3 md:px-6 bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 text-white rounded-lg flex items-center font-medium"
                onClick={sendMessage}
                disabled={isLoading || isStreaming || !inputMessage.trim()}
              >
                <Send className="mr-0 md:mr-2 h-4 w-4" />
                <span className="hidden md:inline">Send</span>
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
    </Layout>
  );
}
