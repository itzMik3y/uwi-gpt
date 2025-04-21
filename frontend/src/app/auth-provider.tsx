'use client';

import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAppSelector, useAppDispatch } from '@/store/hooks';
import { checkAuthStatus } from '@/store/slices/authSlice';

// Define the shape of our auth context
interface AuthContextType {
  isChecking: boolean;
}

// Create auth context with default values
const AuthContext = createContext<AuthContextType>({
  isChecking: true
});

// Public routes that don't require authentication
const PUBLIC_ROUTES = ['/login', '/register', '/forgot-password'];

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isChecking, setIsChecking] = useState(true);
  const router = useRouter();
  const pathname = usePathname();
  const dispatch = useAppDispatch();
  const { isAuthenticated } = useAppSelector(state => state.auth);
  
  // Check authentication status on mount
  useEffect(() => {
    async function checkAuth() {
      try {
        await dispatch(checkAuthStatus());
      } catch (error) {
        console.error('Auth check failed:', error);
      } finally {
        setIsChecking(false);
      }
    }
    
    checkAuth();
  }, [dispatch]);
  
  // Handle redirects based on auth status
  useEffect(() => {
    if (isChecking) return;
    
    const isPublicRoute = PUBLIC_ROUTES.includes(pathname);
    
    if (!isAuthenticated && !isPublicRoute) {
      // Redirect to login if not authenticated and trying to access a protected route
      router.push('/login');
    } else if (isAuthenticated && pathname === '/login') {
      // Redirect to dashboard if authenticated and trying to access login page
      router.push('/dashboard');
    }
  }, [isAuthenticated, pathname, router, isChecking]);
  
  // Show loading spinner while checking auth status
  if (isChecking) {
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent"></div>
      </div>
    );
  }
  
  // Only render children if:
  // - User is authenticated, or
  // - Current route is public
  const shouldRenderChildren = isAuthenticated || PUBLIC_ROUTES.includes(pathname);
  
  return (
    <AuthContext.Provider value={{ isChecking }}>
      {shouldRenderChildren ? children : null}
    </AuthContext.Provider>
  );
}

// Hook to use the auth context
export function useAuth() {
  return useContext(AuthContext);
}