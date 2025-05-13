"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import Image from "next/image"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { Card, CardContent } from "@/components/ui/card"
import { Shield, Settings, User, Info } from "lucide-react"
import { useAppDispatch, useAppSelector } from "@/store/hooks"
import { loginAdmin, clearAdminError } from "@/store/slices/adminAuthSlice"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { UserLink } from "@/app/components/shared/user-link"
import { adminApi } from "@/lib/api/adminClient"

export default function AdminLoginPage() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [rememberMe, setRememberMe] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [debugInfo, setDebugInfo] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false); // MODIFICATION: Added local submitting state

  const dispatch = useAppDispatch()
  const { isLoading, error, isAuthenticated } = useAppSelector(state => state.adminAuth)
  const router = useRouter()

  // Check token on mount to help debug
  useEffect(() => {
    const isAuth = adminApi.isAuthenticated();
    console.log('Admin API authenticated on mount:', isAuth);
    if (isAuth) {
      setDebugInfo(`Auth token present, authenticated: ${isAuth}`);
    }
  }, []);

  // Clear errors when component mounts
  useEffect(() => {
    dispatch(clearAdminError())
    setLocalError(null)
    setStatusMessage(null)
  }, [dispatch])

  // Check if already authenticated and redirect if needed
  useEffect(() => {
    if (isAuthenticated) {
      console.log('Authenticated in Redux state, redirecting to dashboard');
      router.push('/admin/dashboard')
    }
  }, [isAuthenticated, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault() // Prevent default form submission
    
    // MODIFICATION: Prevent submission if already submitting
    if (isSubmitting) {
      console.log("Submission already in progress, preventing duplicate.");
      return;
    }

    setIsSubmitting(true); // MODIFICATION: Set submitting state immediately
    setLocalError(null)
    setStatusMessage(null)
    setDebugInfo(null)

    console.log("Admin login form submitted");

    if (!username || !password) {
      setLocalError("Please enter both login ID and password")
      setIsSubmitting(false); // MODIFICATION: Reset submitting state
      return
    }

    try {
      console.log('Attempting admin login with credentials:', { username });
      setStatusMessage("Logging in...") // This will also help disable the button via statusMessage !== null

      const loginResult = await dispatch(loginAdmin({
        username,
        password
      })).unwrap()

      console.log('Login successful, received tokens');
      setStatusMessage("Login successful! Fetching your data...")
      // router.push('/admin/dashboard') will be handled by useEffect watching isAuthenticated

      // Fallback navigation (already present)
      setTimeout(() => {
        if (adminApi.isAuthenticated() && router.pathname === '/admin/login') { 
          console.log('Still on login page after successful auth, manually navigating...');
          router.push('/admin/dashboard');
        }
      }, 2000);

    } catch (error: any) {
      console.error('Login error details:', error);

      // The error message from the screenshot is "Previous login attempt was not completed. Please try again."
      // This is a specific case of the thunk rejecting due to isLoading being true.
      if (error === "Login in progress, please wait..." || error?.message === "Login in progress, please wait...") {
        setStatusMessage("Login in progress, please wait...")
      } else if (error === "Already loading admin data" || error?.message === "Already loading admin data") {
        setStatusMessage("Verifying your credentials...")
      } else if (error === "Previous login attempt was not completed. Please try again." || error?.message === "Previous login attempt was not completed. Please try again.") {
        setLocalError(error?.message || error); // Show this specific error
        // statusMessage might still be "Logging in..." or null.
      }
      else {
        setLocalError(error?.message || error || 'Login failed. Please check your credentials.')
        setDebugInfo(`Error type: ${typeof error}, Details: ${JSON.stringify(error)}`)
      }
    } finally {
      setIsSubmitting(false); // MODIFICATION: Reset submitting state in all cases (success/error)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <Card className="w-full max-w-3xl overflow-hidden p-0 shadow-xl">
        <div className="flex flex-col md:flex-row">
          {/* Left side - Dark blue section */}
          <div className="relative flex flex-col justify-center bg-slate-900 p-8 text-white md:w-1/2">
            <div className="mb-6">
              <Image
                src="/uwi-logo.png"
                alt="UWI Logo"
                width={100}
                height={40}
                className="h-auto w-auto"
              />
            </div>
            <h1 className="mb-6 text-2xl font-bold">Admin Portal</h1>
            <p className="mb-10 text-lg">
              Manage UWI-GPT system operations, users, and resources from a centralized dashboard.
            </p>
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <User className="h-6 w-6 text-slate-300" />
                <span>User Management</span>
              </div>
              <div className="flex items-center gap-3">
                <Shield className="h-6 w-6 text-slate-300" />
                <span>Security Controls</span>
              </div>
              <div className="flex items-center gap-3">
                <Settings className="h-6 w-6 text-slate-300" />
                <span>System Configuration</span>
              </div>
            </div>
          </div>

          {/* Right side - White login form */}
          <div className="flex flex-col justify-center p-8 md:w-1/2">
            <h2 className="mb-2 text-center text-2xl font-bold text-gray-900">
              Admin Sign In
            </h2>
            <p className="mb-6 text-center text-gray-600">
              Access the administrator dashboard
            </p>

            {(localError || error) && ( // Display Redux error if localError is not set by a more specific condition
              <Alert variant="destructive" className="mb-4">
                <AlertDescription>
                  {localError || error}
                </AlertDescription>
              </Alert>
            )}

            {statusMessage && (
              <Alert variant="default" className="mb-4 bg-blue-50 text-blue-800 border-blue-200">
                <Info className="h-4 w-4 mr-2" />
                <AlertDescription>
                  {statusMessage}
                </AlertDescription>
              </Alert>
            )}

            {debugInfo && (
              <Alert variant="default" className="mb-4 bg-gray-50 text-gray-800 border-gray-200 text-xs">
                <AlertDescription>
                  <details>
                    <summary>Debug Info (click to expand)</summary>
                    <pre className="mt-2 whitespace-pre-wrap">{debugInfo}</pre>
                  </details>
                </AlertDescription>
              </Alert>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <label htmlFor="username" className="text-sm font-medium text-gray-700">
                  Login ID
                </label>
                <Input
                  id="username"
                  type="text"
                  placeholder="Enter your Admin Login ID"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full"
                  required
                  disabled={isSubmitting || isLoading} // MODIFICATION: Also disable on local isSubmitting
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
                  disabled={isSubmitting || isLoading} // MODIFICATION: Also disable on local isSubmitting
                />
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="remember"
                    checked={rememberMe}
                    onCheckedChange={(checked) => setRememberMe(!!checked)} 
                    disabled={isSubmitting || isLoading} // MODIFICATION: Also disable on local isSubmitting
                  />
                  <label
                    htmlFor="remember"
                    className="text-sm font-medium text-gray-700"
                  >
                    Remember me
                  </label>
                </div>
                <Link
                  href="/admin/forgot-password"
                  className="text-sm font-medium text-blue-600 hover:text-blue-500"
                >
                  Forgot password?
                </Link>
              </div>

              <Button
                type="submit"
                className="w-full bg-blue-600 hover:bg-blue-700"
                // MODIFICATION: Updated disabled condition
                disabled={isSubmitting || isLoading || statusMessage !== null}
              >
                {/* MODIFICATION: Updated button text condition */}
                {isSubmitting || isLoading ? 'Signing in...' : 'Sign In'}
              </Button>

              <p className="text-center text-sm text-gray-600">
                Need student access?{" "}
                <UserLink className="font-medium text-blue-600 hover:text-blue-500">
                  Student Login
                </UserLink>
              </p>
            </form>

            <div className="mt-6 flex items-center justify-center text-sm text-gray-500">
              <Shield className="mr-2 h-4 w-4" />
              Secure administrative access
            </div>
          </div>
        </div>
      </Card>
    </div>
  )
}
