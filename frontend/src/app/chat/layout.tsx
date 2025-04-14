// app/dashboard/layout.tsx
import AuthGuard from '../components/AuthGuard'; // Adjust based on actual folder structure'; // Adjust the import path if necessary
import React from 'react';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Apply the AuthGuard to all pages within the /dashboard segment
  return <AuthGuard>{children}</AuthGuard>;
}