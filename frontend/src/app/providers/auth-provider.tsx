// app/providers/auth-provider.tsx
'use client';

import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAppSelector, useAppDispatch } from '@/store/hooks';
import { checkAuthStatus } from '@/store/slices/authSlice';
import { checkAdminAuthStatus } from '@/store/slices/adminAuthSlice';

// Define the shape of our auth context
interface AuthContextType {
  isChecking: boolean;
  isUserAuthenticated: boolean;
  isAdminAuthenticated: boolean;
}

// Create auth context with default values
const AuthContext = createContext<AuthContextType>({
  isChecking: true,
  isUserAuthenticated: false,
  isAdminAuthenticated: false
});

// Public routes that don't require authentication
const PUBLIC_ROUTES = ['/login', '/register', '/forgot-password', '/admin/login'];

// Admin routes
const ADMIN_ROUTES = ['/admin', '/admin/dashboard', '/admin/slots', '/admin/bookings', '/admin/users', '/admin/settings'];

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isChecking, setIsChecking] = useState(true);
  const router = useRouter();
  const pathname = usePathname();
  const dispatch = useAppDispatch();
  
  // Get auth states from both slices
  const { isAuthenticated: isUserAuthenticated } = useAppSelector(state => state.auth);
  const { isAuthenticated: isAdminAuthenticated } = useAppSelector(state => state.adminAuth);
  
  console.log('Auth state:', { 
    pathname,
    isUserAuthenticated, 
    isAdminAuthenticated, 
    isChecking 
  });
  
  // Check both authentication statuses on mount
  useEffect(() => {
    async function checkAuth() {
      try {
        // Check both auth systems in parallel
        await Promise.all([
          dispatch(checkAuthStatus()),
          dispatch(checkAdminAuthStatus())
        ]);
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
    const isAdminRoute = pathname.startsWith('/admin');
    
    console.log('Checking routes:', { 
      pathname, 
      isPublicRoute, 
      isAdminRoute,
      isUserAuthenticated,
      isAdminAuthenticated
    });
    
    // Logic for admin routes
    if (isAdminRoute) {
      // Admin login page is accessible to everyone
      if (pathname === '/admin/login') {
        // If already admin authenticated, redirect to admin dashboard
        if (isAdminAuthenticated) {
          router.push('/admin/dashboard');
        }
        // Otherwise stay on admin login page
        return;
      }
      
      // For all other admin routes, require admin authentication
      if (!isAdminAuthenticated) {
        console.log('Redirecting to admin login from:', pathname);
        router.push('/admin/login');
      }
    } 
    // Logic for regular user routes
    else {
      if (!isUserAuthenticated && !isPublicRoute) {
        // Redirect to login if not authenticated and trying to access a protected user route
        console.log('Redirecting to login from:', pathname);
        router.push('/login');
      } else if (isUserAuthenticated && pathname === '/login') {
        // Redirect to dashboard if authenticated and trying to access login page
        router.push('/dashboard');
      }
    }
  }, [isUserAuthenticated, isAdminAuthenticated, pathname, router, isChecking]);
  
  // Show loading spinner while checking auth status
  if (isChecking) {
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent"></div>
      </div>
    );
  }
  
  // Determine if we should render children
  const shouldRenderChildren = 
    // Public routes are always accessible
    PUBLIC_ROUTES.includes(pathname) ||
    // Admin routes require admin authentication
    (pathname.startsWith('/admin') && isAdminAuthenticated) ||
    // Regular routes require user authentication
    (!pathname.startsWith('/admin') && isUserAuthenticated);
  
  console.log('Should render children:', shouldRenderChildren);
  
  return (
    <AuthContext.Provider value={{ 
      isChecking, 
      isUserAuthenticated, 
      isAdminAuthenticated 
    }}>
      {shouldRenderChildren ? children : null}
    </AuthContext.Provider>
  );
}

// Hook to use the auth context
export function useAuth() {
  return useContext(AuthContext);
}