// components/layout/Header.tsx
"use client"

import Image from "next/image"
import Link from "next/link"
import { Bell, LogOut } from "lucide-react" // Added LogOut icon
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { useSelector, useDispatch } from "react-redux" // Added useDispatch
import { RootState } from "@/store"
import { logout } from "@/store/slices/authSlice" // Import the logout action
import { useState, useRef, useEffect } from "react" // Added useState, useRef, useEffect
import { motion, AnimatePresence } from "framer-motion" // Added motion and AnimatePresence
import { useRouter } from "next/navigation" // For redirecting after logout

export function Header() {
  // Get user from Redux store
  const user = useSelector((state: RootState) => state.auth.user);
  const dispatch = useDispatch();
  const router = useRouter();

  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null); // Ref for the dropdown container

  // Get full name for header
  const fullName = user?.name || "User";

  // Create initials for avatar fallback
  const getInitials = (name: string) => {
    const names = name.split(' ');
    if (names.length === 0 || !names[0]) return "U"; // Handle empty or undefined name
    if (names.length >= 2 && names[1]) { // Check if second name exists
      return `${names[0][0]}${names[1][0]}`.toUpperCase();
    }
    return name.substring(0, 2).toUpperCase();
  };

  const userInitials = getInitials(fullName);

  const toggleDropdown = () => {
    setIsDropdownOpen(!isDropdownOpen);
  };

  const handleLogout = () => {
    dispatch(logout());
    setIsDropdownOpen(false);
    router.push('/login'); // Redirect to login page after logout
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [dropdownRef]);

  return (
    <header className="border-b bg-white sticky top-0 z-50">
      <div className="flex h-16 items-center justify-between px-6">
        <div className="flex items-center gap-2">
          <Image
            src="/uwi-logo.png"
            alt="UWI Logo"
            width={40}
            height={40}
            className="h-8 w-auto"
          />
          <Link href="/dashboard">
            <span className="text-xl font-semibold text-blue-800 hover:text-blue-600 transition-colors">UWI-GPT</span>
          </Link>
        </div>

        <div className="flex items-center gap-4">
          <button 
            aria-label="Notifications" 
            className="rounded-full p-2 hover:bg-gray-100 transition-colors"
          >
            <Bell className="h-5 w-5 text-gray-600" />
          </button>

          {/* User Avatar and Dropdown */}
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={toggleDropdown}
              aria-label="User menu"
              className="flex items-center gap-2 cursor-pointer rounded-full p-1 hover:bg-gray-100 transition-colors"
            >
              <Avatar className="h-9 w-9">
                <AvatarImage src={user?.profileimageurl || "/avatar.png"} alt={fullName} />
                <AvatarFallback className="bg-blue-600 text-white font-semibold">
                  {userInitials}
                </AvatarFallback>
              </Avatar>
              <span className="text-sm font-medium text-gray-700 hidden sm:block">{fullName}</span>
            </button>

            <AnimatePresence>
              {isDropdownOpen && (
                <motion.div
                  initial={{ opacity: 0, y: -10, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -10, scale: 0.95 }}
                  transition={{
                    type: "spring",
                    stiffness: 300,
                    damping: 25,
                    duration: 0.2
                  }}
                  className="absolute right-0 mt-2 w-48 origin-top-right rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none py-1"
                  role="menu"
                  aria-orientation="vertical"
                  aria-labelledby="user-menu-button"
                >
                  <div className="px-4 py-3">
                    <p className="text-sm font-medium text-gray-900 truncate">{fullName}</p>
                    {user?.email && <p className="text-xs text-gray-500 truncate">{user.email}</p>}
                  </div>
                  <div className="border-t border-gray-100"></div>
                  <button
                    onClick={handleLogout}
                    className="flex items-center w-full px-4 py-2 text-sm text-left text-gray-700 hover:bg-gray-100 hover:text-gray-900 transition-colors"
                    role="menuitem"
                  >
                    <LogOut className="mr-2 h-4 w-4" />
                    <span>Log out</span>
                  </button>
                  {/* Add more options here if needed */}
                  {/* Example:
                  <Link href="/profile" passHref>
                    <a
                      onClick={() => setIsDropdownOpen(false)}
                      className="flex items-center w-full px-4 py-2 text-sm text-left text-gray-700 hover:bg-gray-100 hover:text-gray-900 transition-colors"
                      role="menuitem"
                    >
                      <User className="mr-2 h-4 w-4" />
                      <span>Profile</span>
                    </a>
                  </Link>
                  */}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </header>
  )
}