// src/components/AuthGuard.tsx
"use client"; // This component needs client-side hooks

import React, { useEffect, ReactNode } from 'react';
import { useSelector } from 'react-redux';
import { useRouter, usePathname } from 'next/navigation'; // Import from next/navigation for App Router
import { RootState } from '@/store'; // Adjust path to your RootState type
// No need to import initializeAuth here, it's handled in ClientProviders

interface AuthGuardProps {
  children: ReactNode;
}

const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const isAuthenticated = useSelector((state: RootState) => state.auth.isAuthenticated);
  const isLoading = useSelector((state: RootState) => state.auth.isLoading);
  // PersistGate handles initial loading from persistence, but initializeAuth might still set isLoading.
  // We need to wait until the check triggered by initializeAuth is complete (isLoading is false)
  // AND check if the user is actually authenticated.

  const router = useRouter();
  const pathname = usePathname(); // Get the current URL path

  useEffect(() => {
    // Only perform checks and redirection *after* the initial loading/auth check is done.
    // We also don't want to redirect if we are already on the login page.
    if (!isLoading && !isAuthenticated && pathname !== '/login') {
      console.log(`AuthGuard: User not authenticated (isLoading: ${isLoading}, isAuthenticated: ${isAuthenticated}). Redirecting from ${pathname} to /login.`);
      router.replace('/login'); // Use replace to prevent issues with browser back button
    }
  }, [isAuthenticated, isLoading, pathname, router]); // Dependencies for the effect

  // While the initial auth check is loading, show a loading state
  // Note: PersistGate might render `null` initially, but checking isLoading
  // covers the async check from initializeAuth too.
  if (isLoading) {
    return <div>Loading authentication...</div>; // Or a proper loading spinner component
  }

  // If authenticated OR if we are currently on the login page, render the children
  if (isAuthenticated || pathname === '/login') {
    return <>{children}</>;
  }

  // If not authenticated and not on the login page,
  // render null while the redirect effect runs.
  return null;
};

export default AuthGuard;