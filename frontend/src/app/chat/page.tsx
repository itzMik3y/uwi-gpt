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
import { useChat } from "@/app/hooks/useChat"
import { useSelector, useDispatch } from "react-redux"
import { RootState } from "@/store"
import ReactMarkdown from "react-markdown"
import { addBotMessage } from "@/store/slices/chatSlice"
import { Layout } from "../components/layout/Layout"

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
  visible: (i) => ({
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
    <div className="prose max-w-none text-gray-800">
      {isHtmlContent(content) ? (
        <div dangerouslySetInnerHTML={{ __html: content }} />
      ) : (
        <ReactMarkdown>
          {content}
        </ReactMarkdown>
      )}
      {isStreaming && (
        <div className="inline-flex space-x-1 mt-1">
          <div className="h-2 w-2 animate-bounce rounded-full bg-gray-500" style={{ animationDelay: '0ms' }}></div>
          <div className="h-2 w-2 animate-bounce rounded-full bg-gray-500" style={{ animationDelay: '200ms' }}></div>
          <div className="h-2 w-2 animate-bounce rounded-full bg-gray-500" style={{ animationDelay: '400ms' }}></div>
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
    sendMessage,
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
  // But only scroll the chat container, not the whole page
  useEffect(() => {
    if (messagesEndRef.current && chatContainerRef.current) {
      // Use scrollIntoView only within the container, not the whole page
      chatContainerRef.current.scrollTo({
        top: chatContainerRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [messages, isStreaming]);
  
  // Ensure the chat container is properly sized based on viewport
  useEffect(() => {
    const resizeChat = () => {
      if (chatContainerRef.current) {
        const viewportHeight = window.innerHeight;
        const infoSectionHeight = infoSectionCollapsed ? 0 : 180; // Approximate height of info section
        const inputSectionHeight = 80; // Approximate height of input section
        const headerHeight = 120; // Estimated header height (adjust as needed)
        
        // Calculate available height for chat container
        const availableHeight = viewportHeight - headerHeight - inputSectionHeight - infoSectionHeight;
        
        // Set min-height to ensure it doesn't get too small
        chatContainerRef.current.style.height = `${Math.max(300, availableHeight)}px`;
      }
    };
    
    // Initial sizing
    resizeChat();
    
    // Resize on window resize
    window.addEventListener('resize', resizeChat);
    
    // Resize when info section collapses/expands
    const resizeTimeout = setTimeout(resizeChat, 350); // After animation completes
    
    return () => {
      window.removeEventListener('resize', resizeChat);
      clearTimeout(resizeTimeout);
    };
  }, [infoSectionCollapsed]);
  
  // Handle pressing Enter key
  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      // Prevent scrolling by stopping event propagation
      e.stopPropagation();
      sendMessage();
    }
  };
  
  // Quick Actions sidebar items
  const quickActions = [
    { 
      label: "Courses", 
      icon: <BookOpen className="h-4 w-4" />, 
      bgColor: "bg-blue-100",
      textColor: "text-blue-700",
      hoverColor: "hover:bg-blue-200"
    },
    { 
      label: "Grades", 
      icon: <GraduationCap className="h-4 w-4" />, 
      bgColor: "bg-purple-100",
      textColor: "text-purple-700",
      hoverColor: "hover:bg-purple-200"
    },
    { 
      label: "Schedule", 
      icon: <Calendar className="h-4 w-4" />, 
      bgColor: "bg-green-100",
      textColor: "text-green-700",
      hoverColor: "hover:bg-green-200"
    },
    { 
      label: "Help", 
      icon: <HelpCircle className="h-4 w-4" />, 
      bgColor: "bg-amber-100",
      textColor: "text-amber-700",
      hoverColor: "hover:bg-amber-200"
    },
  ]
  
  // Recent Chats items
  const recentChats = [
    { 
      title: "Course Registration Help", 
      time: "2h ago",
      active: true
    },
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

  // Add global CSS to hide scrollbars
  useEffect(() => {
    // Add CSS to hide scrollbars globally
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
    
    // Cleanup function
    return () => {
      document.head.removeChild(style);
    };
  }, []);
  
  return (
    <Layout>
    <div className="container mx-auto py-4 px-2">
      {/* Main Chat Area with Border and Shadow */}
      <div className="bg-white rounded-lg shadow-sm flex flex-col h-[calc(100vh-120px)] max-h-[calc(100vh-120px)] overflow-hidden">
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
              // Determine if this is the last bot message and is currently streaming
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
                          className="w-8 h-8"
                        />
                      </div>
                      <div className="bg-blue-50 text-gray-800 rounded-2xl rounded-tl-none p-4 max-w-[70%]">
                        <MessageContent 
                          content={msg.content} 
                          sender={msg.sender} 
                          isStreaming={isCurrentlyStreaming}
                        />
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="bg-gray-100 text-gray-800 rounded-2xl rounded-tr-none p-4 max-w-[70%]">
                        <MessageContent 
                          content={msg.content} 
                          sender={msg.sender}
                        />
                      </div>
                      <div className="flex-shrink-0 ml-2">
                        <Avatar className="w-8 h-8">
                          <AvatarImage src="/avatar.png" alt={fullName} />
                          <AvatarFallback>{userInitials}</AvatarFallback>
                        </Avatar>
                      </div>
                    </>
                  )}
                </motion.div>
              );
            })}
                  
            {/* Only show the typing indicator for non-streaming loading */}
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
                    className="w-8 h-8"
                  />
                </div>
                <div className="bg-gray-100 rounded-full px-4 py-2">
                  <div className="flex space-x-1">
                    <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400" style={{ animationDelay: '0ms' }}></div>
                    <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400" style={{ animationDelay: '200ms' }}></div>
                    <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400" style={{ animationDelay: '400ms' }}></div>
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
                    <User className="h-4 w-4 text-white" />
                  </div>
                </div>
                <div className="bg-red-50 text-red-700 rounded-2xl rounded-tl-none p-4">
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
        <div className="border-t bg-gray-50 relative flex-shrink-0">
          {/* Collapse/Expand button */}
          <div className="absolute left-1/2 -top-3 transform -translate-x-1/2 z-10">
            <Button 
              variant="ghost" 
              size="icon" 
              className="flex h-6 w-6 items-center justify-center rounded-full border border-gray-200 bg-white shadow-sm hover:bg-gray-100"
              onClick={toggleInfoSection}
              aria-label={infoSectionCollapsed ? "Expand info section" : "Collapse info section"}
            >
              <motion.div
                animate={{ rotate: infoSectionCollapsed ? 90 : 270 }}
                transition={{ 
                  duration: 0.4, 
                  ease: [0.4, 0.0, 0.2, 1] // Custom easing curve for smoother motion
                }}
              >
                <ChevronRight className="h-4 w-4" />
              </motion.div>
            </Button>
          </div>

          {/* Info Section (collapsible) */}
          <AnimatePresence>
            {!infoSectionCollapsed && (
              <motion.div 
                className="grid grid-cols-3 gap-4 p-4 border-b w-full"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ 
                  duration: 0.4, 
                  ease: [0.4, 0.0, 0.2, 1]
                }}
              >
                {/* Recent Chats */}
                <div className="bg-white p-4 rounded-lg shadow-sm overflow-hidden">
                  <h3 className="text-sm font-semibold mb-3 flex items-center">
                    <Clock className="mr-2 h-4 w-4 text-blue-600" />
                    Recent Chats
                  </h3>
                  <div className="space-y-2 max-h-24 overflow-y-auto" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
                    {recentChats.map((chat, index) => (
                      <div 
                        key={index}
                        className={`text-sm ${chat.active ? 'bg-blue-50' : 'bg-gray-100'} p-2 rounded cursor-pointer ${chat.active ? 'hover:bg-blue-100' : 'hover:bg-gray-200'}`}
                      >
                        {chat.title} - {chat.time}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Quick Actions */}
                <div className="bg-white p-4 rounded-lg shadow-sm">
                  <h3 className="text-sm font-semibold mb-3 flex items-center">
                    <Zap className="mr-2 h-4 w-4 text-amber-500" />
                    Quick Actions
                  </h3>
                  <div className="grid grid-cols-2 gap-2">
                    {quickActions.map((action, index) => (
                      <button 
                        key={index}
                        className={`text-sm px-3 py-2 ${action.bgColor} ${action.textColor} rounded-lg ${action.hoverColor} flex items-center justify-center`}
                      >
                        {action.icon}
                        <span className="ml-1">{action.label}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Suggested Topics */}
                <div className="bg-white p-4 rounded-lg shadow-sm overflow-hidden">
                  <h3 className="text-sm font-semibold mb-3 flex items-center">
                    <LightbulbIcon className="mr-2 h-4 w-4 text-yellow-500" />
                    Suggested Topics
                  </h3>
                  <div className="space-y-2 max-h-24 overflow-y-auto" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
                    {suggestedTopics.map((topic, index) => (
                      <button 
                        key={index}
                        className="w-full text-left text-sm px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
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
            <div className="flex items-center space-x-4">
              <div className="flex-1 relative">
                <Input
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyDown={handleKeyPress}
                  placeholder="Type your question here..."
                  className="w-full px-4 py-3 rounded-lg border focus:ring-2 focus:ring-blue-500"
                  disabled={isLoading || isStreaming}
                />
                <div className="absolute right-2 top-1/2 transform -translate-y-1/2 flex items-center space-x-2">
                  {/* Streaming toggle button */}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-gray-400 hover:text-gray-600 h-8 w-8 flex items-center justify-center"
                    onClick={toggleStreaming}
                    title={useStreaming ? "Turn off streaming" : "Turn on streaming"}
                  >
                    <Sparkles className={`h-5 w-5 ${useStreaming ? 'text-yellow-500' : 'text-gray-400'}`} />
                  </Button>
                  
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-gray-400 hover:text-gray-600 h-8 w-8 flex items-center justify-center"
                  >
                    <Paperclip className="h-5 w-5" />
                  </Button>
                </div>
              </div>
              
              <Button
                className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg flex items-center"
                onClick={sendMessage}
                disabled={isLoading || isStreaming || !inputMessage.trim()}
              >
                <Send className="mr-2 h-4 w-4" />
                Send
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
    </Layout>
  );
}