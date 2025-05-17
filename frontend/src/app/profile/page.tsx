// app/profile/page.tsx
"use client"

import React from "react";
import { useSelector, useDispatch } from "react-redux";
import { RootState, AppDispatch } from "@/store";
import { Layout } from "@/app/components/layout/Layout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { User, Mail, Briefcase, Award, BookOpen, Building, AlertTriangle } from "lucide-react";
import { deleteUserAccount } from "@/store/slices/authSlice"; // Removed unused 'logout' import here
import { useRouter } from 'next/navigation';

export default function ProfilePage() {
  const dispatch = useDispatch<AppDispatch>();
  const router = useRouter();

  const user = useSelector((state: RootState) => state.auth.user);
  const isLoading = useSelector((state: RootState) => state.auth.isLoading);
  const error = useSelector((state: RootState) => state.auth.error);
  const isAuthenticated = useSelector((state: RootState) => state.auth.isAuthenticated);
  // **MOVED THIS LINE UP**
  const isAuthInitialized = useSelector((state: RootState) => state.auth.isAuthInitialized);

  const handleDeleteAccount = async () => {
    const confirmed = window.confirm(
      "Are you absolutely sure you want to delete your account?\n\nTHIS ACTION IS PERMANENT AND CANNOT BE UNDONE.\nAll your personal information, course data, bookings, and grades will be erased from the system."
    );
    if (confirmed) {
      try {
        await dispatch(deleteUserAccount()).unwrap();
        alert("Your account has been successfully deleted.");
        router.push('/login');
      } catch (deletionError: any) {
        console.error("Account deletion failed:", deletionError);
        // Error is handled by the error state in Redux and displayed in the UI
      }
    }
  };

  React.useEffect(() => {
    // Ensure isAuthInitialized is true before attempting redirect based on !isAuthenticated
    if (isAuthInitialized && !isLoading && !isAuthenticated && !user) {
      router.push('/login');
    }
  }, [isAuthenticated, isLoading, user, router, isAuthInitialized]);


  if (!isAuthInitialized && isLoading) { // Initial loading state for auth initialization
    return (
      <Layout>
        <div className="flex justify-center items-center h-screen">
          <p>Initializing...</p>
        </div>
      </Layout>
    );
  }

  const actionInProgress = isLoading && isAuthInitialized; // When an action like delete is happening

  if (!user && isAuthInitialized && !actionInProgress) {
    return (
      <Layout>
        <div className="p-4 md:p-8 text-center">
          <h1 className="text-2xl font-bold">Not Logged In</h1>
          <p>Please log in to view your profile.</p>
          <Button onClick={() => router.push('/login')} className="mt-4">Go to Login</Button>
        </div>
      </Layout>
    );
  }

  if (!user && actionInProgress) { // Still loading (e.g. after login, fetching user data)
     return (
      <Layout>
        <div className="flex justify-center items-center h-screen">
          <p>Loading profile data...</p>
        </div>
      </Layout>
    );
  }
  
  if (!user) { // Fallback if user is still null after checks (should ideally be caught by above)
    return (
         <Layout>
        <div className="p-4 md:p-8 text-center">
          <h1 className="text-2xl font-bold">User Data Unavailable</h1>
          <p>Could not retrieve user information. You might be logged out.</p>
           <Button onClick={() => router.push('/login')} className="mt-4">Go to Login</Button>
        </div>
      </Layout>
    )
  }

  const profileItems = [
    {
      icon: <User className="h-5 w-5 text-blue-500" />,
      label: "Full Name",
      value: user.name,
    },
    {
      icon: <Mail className="h-5 w-5 text-blue-500" />,
      label: "Email Address",
      value: user.email,
    },
    {
      icon: <Briefcase className="h-5 w-5 text-blue-500" />,
      label: "Student ID",
      value: user.student_id,
    },
    {
      icon: <Award className="h-5 w-5 text-blue-500" />,
      label: "Major(s)",
      value: user.majors || "Not Specified",
    },
    {
      icon: <BookOpen className="h-5 w-5 text-blue-500" />,
      label: "Minor(s)",
      value: user.minors || "Not Specified",
    },
    {
      icon: <Building className="h-5 w-5 text-blue-500" />,
      label: "Faculty",
      value: user.faculty || "Not Specified",
    },
  ];

  return (
    <Layout>
      <div className="bg-gray-100 min-h-screen">
        <div className="bg-blue-600 p-6 md:p-8 text-white">
          <h1 className="text-3xl font-bold mb-1">Student Profile</h1>
          <p className="text-blue-100">View and manage your personal information.</p>
        </div>

        <div className="p-4 md:p-8">
          {error && (
            <Card className="mb-6 bg-red-50 border-red-300">
              <CardHeader>
                <CardTitle className="text-red-700 flex items-center">
                  <AlertTriangle className="h-5 w-5 mr-2" />
                  Operation Failed
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-red-600">{error}</p>
              </CardContent>
            </Card>
          )}

          <Card className="shadow-lg mb-8">
            <CardHeader>
              <CardTitle className="text-2xl font-semibold text-gray-800">
                {user.name}
              </CardTitle>
              <CardDescription>
                Student ID: {user.student_id}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-6">
                {profileItems.map((item, index) => (
                  <div key={index} className="flex items-start space-x-4 p-3 border-b last:border-b-0">
                    <div className="flex-shrink-0 mt-1 bg-blue-100 p-2 rounded-full">
                      {item.icon}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-500">{item.label}</p>
                      <p className="text-md font-semibold text-gray-700">{item.value}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-lg border-red-200">
            <CardHeader>
              <CardTitle className="text-xl font-semibold text-red-700">Account Management</CardTitle>
              <CardDescription className="text-gray-600">
                This section contains dangerous actions. Proceed with caution.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div>
                  <h3 className="font-medium text-gray-800">Delete Account</h3>
                  <p className="text-sm text-gray-500 mb-3">
                    Permanently delete your account and all associated data from our system. This action cannot be undone.
                  </p>
                  <Button
                    variant="destructive"
                    onClick={handleDeleteAccount}
                    disabled={actionInProgress}
                  >
                    {actionInProgress ? 'Processing...' : 'Delete My Account'}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  );
}