// app/login/page.tsx
"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import Image from "next/image"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { Card, CardContent } from "@/components/ui/card"
import { Shield, GraduationCap, User } from "lucide-react"
import { useAppDispatch, useAppSelector } from "@/store/hooks"
import { loginUser, fetchUserData } from "@/store/slices/authSlice"
import { Alert, AlertDescription } from "@/components/ui/alert"

export default function LoginPage() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [rememberMe, setRememberMe] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)
  
  const dispatch = useAppDispatch()
  const { isLoading, error, isAuthenticated } = useAppSelector(state => state.auth)
  const router = useRouter()
  
  // Check if already authenticated and redirect if needed
  useEffect(() => {
    if (isAuthenticated) {
      router.push('/dashboard')
    }
  }, [isAuthenticated, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLocalError(null)
    
    if (!username || !password) {
      setLocalError("Please enter both username and password")
      return
    }
    
    try {
      // First login to get tokens
      const loginResult = await dispatch(loginUser({
        username, 
        password
      })).unwrap()
      
      // Then fetch user data
      await dispatch(fetchUserData()).unwrap()
      
      // Navigate after successful login and data fetch
      router.push('/dashboard')
    } catch (error: any) {
      setLocalError(error || 'Login failed. Please check your credentials.')
      console.error('Login error:', error)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-blue-100 p-4">
      <Card className="w-full max-w-3xl overflow-hidden p-0 shadow-xl">
        <div className="flex flex-col md:flex-row">
          {/* Left side - Dark blue section */}
          <div className="relative flex flex-col justify-center bg-blue-950 p-8 text-white md:w-1/2">
            <div className="mb-6">
              <Image 
                src="/uwi-logo.png" 
                alt="UWI Logo" 
                width={100} 
                height={40}
                className="h-auto"
              />
            </div>
            
            <h1 className="mb-6 text-2xl font-bold">Welcome to UWI-GPT</h1>
            
            <p className="mb-10 text-lg">
              Your AI-powered academic companion for success at The University of the West Indies.
            </p>
            
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <User className="h-6 w-6 text-blue-300" />
                <span>24/7 AI Academic Support</span>
              </div>
              
              <div className="flex items-center gap-3">
                <Shield className="h-6 w-6 text-blue-300" />
                <span>Secure & Private Platform</span>
              </div>
              
              <div className="flex items-center gap-3">
                <GraduationCap className="h-6 w-6 text-blue-300" />
                <span>Personalized Guidance</span>
              </div>
            </div>
          </div>
          
          {/* Right side - White login form */}
          <div className="flex flex-col justify-center p-8 md:w-1/2">
            <h2 className="mb-2 text-center text-2xl font-bold text-gray-900">
              Sign In to UWI-GPT
            </h2>
            
            <p className="mb-6 text-center text-gray-600">
              Access your academic advisor
            </p>
            
            {/* Error message */}
            {(localError || error) && (
              <Alert variant="destructive" className="mb-4">
                <AlertDescription>
                  {localError || error}
                </AlertDescription>
              </Alert>
            )}
            
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Username Input */}
              <div className="space-y-2">
                <label htmlFor="username" className="text-sm font-medium text-gray-700">
                  Username / Student ID 
                </label>
                <Input
                  id="username"
                  type="text" 
                  placeholder="Enter your Student ID or Username" 
                  value={username} 
                  onChange={(e) => setUsername(e.target.value)} 
                  className="w-full"
                  required
                  disabled={isLoading}
                />
              </div>
              
              {/* Password Input */}
              <div className="space-y-2">
                <label htmlFor="password" className="text-sm font-medium text-gray-700">
                  Password
                </label>
                <Input
                  id="password"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full"
                  required
                  disabled={isLoading}
                />
              </div>
              
              {/* Remember Me & Forgot Password */}
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="remember"
                    checked={rememberMe}
                    onCheckedChange={(checked) => setRememberMe(!!checked)}
                    disabled={isLoading}
                  />
                  <label
                    htmlFor="remember"
                    className="text-sm font-medium text-gray-700"
                  >
                    Remember me
                  </label>
                </div>
                
                <Link
                  href="/forgot-password"
                  className="text-sm font-medium text-red-600 hover:text-red-500"
                >
                  Forgot password?
                </Link>
              </div>
              
              {/* Submit Button */}
              <Button
                type="submit"
                className="w-full bg-red-600 hover:bg-red-700"
                disabled={isLoading}
              >
                {isLoading ? 'Signing in...' : 'Sign In'}
              </Button>
              
              {/* Registration Link */}
              <p className="text-center text-sm text-gray-600">
                Don&apos;t have an account?{" "}
                <Link href="/register" className="font-medium text-red-600 hover:text-red-500">
                  Create Account
                </Link>
              </p>
            </form>
            
            <div className="mt-6 flex items-center justify-center text-sm text-gray-500">
              <Shield className="mr-2 h-4 w-4" />
              Secure login protected by UWI authentication
            </div>
          </div>
        </div>
      </Card>
    </div>
  ) }