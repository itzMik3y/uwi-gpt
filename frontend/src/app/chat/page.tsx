"use client"

import { useState, useRef, useEffect } from "react"
import Link from "next/link"
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
  ChevronRight as ArrowRight
} from "lucide-react"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Header } from "@/app/components/layout/Header"
import { HorizontalNav } from "@/app/components/layout/HorizonatalNav"
import { motion, AnimatePresence } from "framer-motion"
import { useChat } from "@/app/hooks/useChat"
import { Provider } from "react-redux"
import { store } from "@/store/index"
import ReactMarkdown from "react-markdown"

// Define interface for nav items
interface NavItem {
  label: string;
  icon: React.ReactNode;
  path: string;
  active?: boolean;
  hasArrow?: boolean;
}

// Animation variants
const pageVariants = {
  hidden: { opacity: 0 },
  visible: { 
    opacity: 1,
    transition: {
      duration: 0.3
    }
  },
  exit: { 
    opacity: 0,
    transition: {
      duration: 0.2
    }
  }
};

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
const MessageContent = ({ content, sender }: { content: string, sender: 'user' | 'bot' }) => {
  if (sender === 'user') {
    return <p>{content}</p>;
  }
  
  return (
    <div className="prose prose-invert max-w-none">
      <ReactMarkdown>
        {content}
      </ReactMarkdown>
    </div>
  );
};

// Wrap the page content with Redux Provider
const ChatPageContent = () => {
  const [leftSidebarCollapsed, setLeftSidebarCollapsed] = useState(false)
  const [rightSidebarCollapsed, setRightSidebarCollapsed] = useState(false)
  const pathname = usePathname()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  
  // Use our custom hook for chat functionality
  const { messages, isLoading, inputMessage, setInputMessage, sendMessage } = useChat();
  
  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);
  
  // Handle pressing Enter key
  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };
  
  // Quick Actions sidebar items
  const quickActions: NavItem[] = [
    { 
      label: "Course Selection", 
      icon: <GraduationCap className="h-5 w-5" />, 
      path: "/course-selection",
      active: true,
      hasArrow: false
    },
    { 
      label: "Graduation Planning", 
      icon: <Calendar className="h-5 w-5" />, 
      path: "/graduation-planning",
      hasArrow: false
    },
    { 
      label: "Mental Wellness", 
      icon: <Heart className="h-5 w-5" />, 
      path: "/mental-wellness",
      hasArrow: false
    },
    { 
      label: "FAQs", 
      icon: <HelpCircle className="h-5 w-5" />, 
      path: "/faqs",
      hasArrow: false
    },
  ]
  
  // Resources sidebar items with arrows
  const resources: NavItem[] = [
    { 
      label: "Academic Calendar", 
      icon: <Calendar className="h-5 w-5" />, 
      path: "/academic-calendar",
      hasArrow: true
    },
    { 
      label: "Course Catalog", 
      icon: <BookOpen className="h-5 w-5" />, 
      path: "/course-catalog",
      hasArrow: true 
    },
    { 
      label: "Degree Requirements", 
      icon: <FileText className="h-5 w-5" />, 
      path: "/degree-requirements",
      hasArrow: true 
    },
    { 
      label: "Student Resources", 
      icon: <School className="h-5 w-5" />, 
      path: "/student-resources",
      hasArrow: true 
    },
  ]

  const toggleLeftSidebar = () => {
    setLeftSidebarCollapsed(!leftSidebarCollapsed)
  }

  const toggleRightSidebar = () => {
    setRightSidebarCollapsed(!rightSidebarCollapsed)
  }

  return (
    <motion.div 
      className="flex h-screen flex-col bg-white overflow-hidden"
      variants={pageVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
    >
      {/* Header */}
      <div className="flex-shrink-0">
        <Header />
      </div>
      
      {/* Horizontal Navbar */}
      <motion.div 
        className="flex-shrink-0 bg-gradient-to-b from-blue-600 to-blue-500 px-4 py-2"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3 }}
      >
        <HorizontalNav />
      </motion.div>
      
      {/* Main content area with fixed height */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar - Quick Actions */}
        <aside 
          className={`
            relative flex-shrink-0 border-r bg-white transition-all duration-300 ease-in-out overflow-hidden
            ${leftSidebarCollapsed ? 'w-0' : 'w-80'}
          `}
        >
          <div 
            className="absolute -right-6 top-4 z-10"
          >
            <Button 
              variant="ghost" 
              size="icon" 
              className="flex h-6 w-6 items-center justify-center rounded-full border border-gray-200 bg-white shadow-sm hover:bg-gray-100"
              onClick={toggleLeftSidebar}
              aria-label={leftSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              <motion.div
                animate={{ rotate: leftSidebarCollapsed ? 0 : 180 }}
                transition={{ duration: 0.3 }}
              >
                {leftSidebarCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
              </motion.div>
            </Button>
          </div>
          
          <AnimatePresence>
            {!leftSidebarCollapsed && (
              <motion.div 
                className="h-full overflow-y-auto p-4"
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                transition={{ duration: 0.2 }}
              >
                <h2 className="mb-4 font-semibold">Quick Actions</h2>
                <nav className="space-y-2">
                  {quickActions.map((item, index) => (
                    <motion.div
                      key={item.path}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.05, duration: 0.2 }}
                    >
                      <Link
                        href={item.path}
                        className={`
                          flex items-center gap-3 rounded-lg p-3 transition-colors
                          ${item.active 
                            ? "bg-yellow-400 text-black font-medium" 
                            : "bg-gray-100 text-gray-700 hover:bg-gray-200"}
                        `}
                      >
                        {item.icon}
                        <span className="flex-1">{item.label}</span>
                        {item.hasArrow && <ArrowRight className="h-4 w-4" />}
                      </Link>
                    </motion.div>
                  ))}
                </nav>
              </motion.div>
            )}
          </AnimatePresence>
        </aside>
        
        {/* Space between left sidebar and main content */}
        <div className="flex-shrink-0 w-8"></div>
        
        {/* Main Chat Area - Fixed height with internal scrolling */}
        <motion.main 
          className={`flex-1 flex flex-col bg-white ${leftSidebarCollapsed && rightSidebarCollapsed ? 'px-6' : 'px-2'} overflow-hidden`}
          layout
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
        >
          <div className="flex flex-col h-full">
            {/* Chat messages - This div scrolls */}
            <div className="flex-1 overflow-y-auto p-4">
              <div className="space-y-6">
                {messages.map((msg, index) => (
                  <motion.div 
                    key={msg.id}
                    className={`flex ${msg.sender === 'user' ? 'justify-end' : ''}`}
                    custom={index}
                    initial="hidden"
                    animate="visible"
                    variants={chatItemVariants}
                  >
                    {msg.sender === 'bot' && (
                      <div className="mr-3 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-blue-900 text-white">
                        <User className="h-6 w-6" />
                      </div>
                    )}
                    
                    <div className={`max-w-3xl rounded-lg ${msg.sender === 'user' 
                      ? 'bg-gray-100 p-4 text-gray-800' 
                      : 'bg-blue-900 p-4 text-white'} 
                      ${leftSidebarCollapsed && rightSidebarCollapsed ? 'max-w-2xl' : ''}`}
                    >
                      <MessageContent content={msg.content} sender={msg.sender} />
                    </div>
                    
                    {msg.sender === 'user' && (
                      <div className="ml-3">
                        <Avatar>
                          <AvatarImage src="/avatar.png" alt="Sarah Johnson" />
                          <AvatarFallback>SJ</AvatarFallback>
                        </Avatar>
                      </div>
                    )}
                  </motion.div>
                ))}
                
                {/* Typing indicator when loading */}
                {isLoading && (
                  <motion.div 
                    className="flex"
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3 }}
                  >
                    <div className="mr-3 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-blue-900 text-white">
                      <User className="h-6 w-6" />
                    </div>
                    <div className="flex space-x-1 rounded-lg bg-gray-200 px-4 py-2">
                      <div className="h-2 w-2 animate-bounce rounded-full bg-gray-500" style={{ animationDelay: '0ms' }}></div>
                      <div className="h-2 w-2 animate-bounce rounded-full bg-gray-500" style={{ animationDelay: '200ms' }}></div>
                      <div className="h-2 w-2 animate-bounce rounded-full bg-gray-500" style={{ animationDelay: '400ms' }}></div>
                    </div>
                  </motion.div>
                )}
                
                {/* Invisible element to scroll to */}
                <div ref={messagesEndRef} />
              </div>
            </div>
            
            {/* Message input - Fixed at bottom */}
            <div className="flex-shrink-0 border-t p-4 bg-white">
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-gray-500 hover:bg-gray-100"
                >
                  <Paperclip className="h-5 w-5" />
                </Button>
                
                <Input
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyDown={handleKeyPress}
                  placeholder="Type your message here..."
                  className="flex-1 rounded-full border-gray-300"
                  disabled={isLoading}
                />
                
                <Button
                  className="rounded-full bg-red-600 hover:bg-red-700"
                  onClick={sendMessage}
                  disabled={isLoading || !inputMessage.trim()}
                >
                  <Send className="mr-1 h-4 w-4" />
                  Send
                </Button>
              </div>
            </div>
          </div>
        </motion.main>
        
        {/* Space between main content and right sidebar */}
        <div className="flex-shrink-0 w-8"></div>
        
        {/* Right Sidebar - Resources */}
        <aside 
          className={`
            relative flex-shrink-0 border-l bg-white transition-all duration-300 ease-in-out overflow-hidden
            ${rightSidebarCollapsed ? 'w-0' : 'w-80'}
          `}
        >
          <div 
            className="absolute -left-6 top-4 z-10"
          >
            <Button 
              variant="ghost" 
              size="icon" 
              className="flex h-6 w-6 items-center justify-center rounded-full border border-gray-200 bg-white shadow-sm hover:bg-gray-100"
              onClick={toggleRightSidebar}
              aria-label={rightSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              <motion.div
                animate={{ rotate: rightSidebarCollapsed ? 0 : 180 }}
                transition={{ duration: 0.3 }}
              >
                {rightSidebarCollapsed ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </motion.div>
            </Button>
          </div>
          
          <AnimatePresence>
            {!rightSidebarCollapsed && (
              <motion.div 
                className="h-full overflow-y-auto p-4"
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 10 }}
                transition={{ duration: 0.2 }}
              >
                <h2 className="mb-4 font-semibold">Resources</h2>
                <nav className="space-y-2">
                  {resources.map((item, index) => (
                    <motion.div
                      key={item.path}
                      initial={{ opacity: 0, x: 10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.05, duration: 0.2 }}
                    >
                      <Link
                        href={item.path}
                        className="flex items-center gap-3 rounded-lg p-3 text-gray-700 transition-colors hover:bg-gray-100"
                      >
                        {item.icon}
                        <span className="flex-1">{item.label}</span>
                        {item.hasArrow && <ArrowRight className="h-4 w-4" />}
                      </Link>
                    </motion.div>
                  ))}
                </nav>
              </motion.div>
            )}
          </AnimatePresence>
        </aside>
      </div>
    </motion.div>
  );
};

// Wrap with Redux Provider for state management
export default function ChatPage() {
  return (
    <Provider store={store}>
      <ChatPageContent />
    </Provider>
  );
}