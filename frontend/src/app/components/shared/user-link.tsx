// app/components/shared/user-link.tsx
"use client"

import Link from "next/link"
import { useAppSelector } from "@/store/hooks"

interface UserLinkProps {
  children: React.ReactNode
  className?: string
}

export function UserLink({ children, className }: UserLinkProps) {
  const { isAuthenticated: isUserAuthenticated } = useAppSelector(state => state.auth)
  
  return (
    <Link 
      href={isUserAuthenticated ? "/dashboard" : "/login"} 
      className={className}
    >
      {children}
    </Link>
  )
}