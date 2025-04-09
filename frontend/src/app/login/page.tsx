// app/login/page.tsx
"use client"

import { useState } from "react"
import Image from "next/image"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { Card, CardContent } from "@/components/ui/card"
import { Shield, GraduationCap, User } from "lucide-react"

export default function LoginPage() {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [rememberMe, setRememberMe] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // Handle login logic here
    console.log({ email, password, rememberMe })
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
            
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <label htmlFor="email" className="text-sm font-medium text-gray-700">
                  Email Address
                </label>
                <Input
                  id="email"
                  type="email"
                  placeholder="student@my.uwi.edu"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full"
                  required
                />
              </div>
              
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
                />
              </div>
              
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="remember"
                    checked={rememberMe}
                    onCheckedChange={(checked) => 
                      setRememberMe(checked as boolean)
                    }
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
              
              <Button
                type="submit"
                className="w-full bg-red-600 hover:bg-red-700"
              >
                Sign In
              </Button>
              
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
  )
}