// app/login/page.tsx
"use client"

import { useState, useEffect } from "react" // Import useEffect
import { useRouter } from "next/navigation"
import Image from "next/image"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { Card, CardContent } from "@/components/ui/card"
import { Shield, GraduationCap, User } from "lucide-react"
import { useAppDispatch, useAppSelector } from "@/store/hooks"
import { loginUser } from "@/store/slices/authSlice" // Ensure correct path
import { Alert, AlertDescription } from "@/components/ui/alert"

// Define localStorage keys (consider defining these in a shared constants file)
const USERNAME_KEY = 'moodle_username';
const PASSWORD_KEY = 'moodle_password'; // !!! INSECURE KEY !!!

export default function LoginPage() {
  const [username, setUsername] = useState("") 
  const [password, setPassword] = useState("")
  const [rememberMe, setRememberMe] = useState(false) // Consider linking rememberMe to saving credentials
  const [localError, setLocalError] = useState<string | null>(null)
  
  const dispatch = useAppDispatch()
  const { isLoading, error, isAuthenticated } = useAppSelector(state => state.auth)
  const router = useRouter()
  
  useEffect(() => {
    const savedUsername = localStorage.getItem(USERNAME_KEY);
    const savedPassword = localStorage.getItem(PASSWORD_KEY); 
    if (savedUsername) {
      setUsername(savedUsername);
    }
    if (savedPassword) {
      setPassword(savedPassword);
      setRememberMe(true); 
    }
  }, []);
  

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLocalError(null)
    
    try {
      await dispatch(loginUser({
        username, 
        password
      })).unwrap() // unwrap handles potential rejection from createAsyncThunk
      
      // On successful login, navigation will happen if unwrap() doesn't throw.
      // If 'rememberMe' is unchecked, clear the stored password (optional enhancement)
      if (!rememberMe) {
         localStorage.removeItem(PASSWORD_KEY); // Remove insecure password if not remembered
      }

      router.push('/dashboard') // Navigate after successful login

    } catch (rejectedValueOrSerializedError) {
      // Error handling if loginUser rejected
      setLocalError(rejectedValueOrSerializedError as string || 'Login failed');
      console.error('Login error:', rejectedValueOrSerializedError);
    }
  }

  // Handle 'Remember Me' checkbox change - decide if you want to clear stored password immediately
   const handleRememberMeChange = (checked: boolean) => {
     setRememberMe(checked);
     if (!checked) {
       // If unchecked, immediately remove the stored password
       localStorage.removeItem(PASSWORD_KEY); // !!! Remove insecure password !!!
     }
     // Note: Username might still be stored based on your logic in authSlice
   };


  return (
    <div className="flex min-h-screen items-center justify-center bg-blue-100 p-4">
      <Card className="w-full max-w-3xl overflow-hidden p-0 shadow-xl">
        <div className="flex flex-col md:flex-row">
          {/* Left side - Dark blue section */}
          {/* ... (left side content remains the same) ... */}
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
                    // Updated handler
                    onCheckedChange={(checked) => handleRememberMeChange(checked as boolean)}
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
                  href="/forgot-password" // Ensure this route exists
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
                  Create Account {/* Ensure this route exists */}
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