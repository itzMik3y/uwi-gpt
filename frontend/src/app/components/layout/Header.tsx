// components/layout/Header.tsx
"use client"

import Image from "next/image"
import Link from "next/link"
import { Bell } from "lucide-react"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { useSelector } from "react-redux"
import { RootState } from "@/store"

export function Header() {
  // Get user from Redux store
  const user = useSelector((state: RootState) => state.auth.user);
  
  // Get full name for header
  const fullName = user?.name || "User";
  
  // Create initials for avatar fallback
  const getInitials = (name: string) => {
    const names = name.split(' ');
    if (names.length >= 2) {
      return `${names[0][0]}${names[1][0]}`.toUpperCase();
    }
    return name.substring(0, 2).toUpperCase();
  };
  
  const userInitials = getInitials(fullName);

  return (
    <header className="border-b">
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
            <span className="text-xl font-semibold text-blue-800">UWI-GPT</span>
          </Link>
        </div>
        
        <div className="flex items-center gap-4">
          <button aria-label="Notifications" className="rounded-full p-1 hover:bg-gray-100">
            <Bell className="h-5 w-5 text-gray-600" />
          </button>
          <div className="flex items-center gap-2">
            <Avatar>
              <AvatarImage src="/avatar.png" alt={fullName} />
              <AvatarFallback>{userInitials}</AvatarFallback>
            </Avatar>
            <span className="text-sm font-medium">{fullName}</span>
          </div>
        </div>
      </div>
    </header>
  )
}