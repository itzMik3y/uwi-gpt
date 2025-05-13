// app/components/shared/admin-link.tsx
"use client"

import Link from "next/link"
import { useAppSelector } from "@/store/hooks"

interface AdminLinkProps {
  children: React.ReactNode
  className?: string
}

export function AdminLink({ children, className }: AdminLinkProps) {
  const { isAuthenticated: isAdminAuthenticated } = useAppSelector(state => state.adminAuth)
  const { isAuthenticated: isUserAuthenticated } = useAppSelector(state => state.auth)
  
  return (
    <Link 
      href={isAdminAuthenticated ? "/admin/dashboard" : "/admin/login"} 
      className={className}
    >
      {children}
    </Link>
  )
}