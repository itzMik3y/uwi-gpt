// app/admin/page.tsx
"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAppSelector } from "@/store/hooks"

export default function AdminRedirectPage() {
  const router = useRouter()
  const { isAuthenticated, isAuthInitialized } = useAppSelector(state => state.adminAuth)
  
  useEffect(() => {
    if (isAuthInitialized) {
      if (isAuthenticated) {
        router.push('/admin/dashboard')
      } else {
        router.push('/admin/login')
      }
    }
  }, [isAuthenticated, isAuthInitialized, router])
  
  return (
    <div className="flex h-screen items-center justify-center">
      <div className="text-center">
        <h1 className="text-xl font-semibold">Redirecting...</h1>
        <p className="text-gray-500">Please wait while we check your credentials</p>
      </div>
    </div>
  )
}