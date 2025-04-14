// app/dashboard/page.tsx
"use client"

import { MessageSquare, Calendar, FileText, GraduationCap, BookOpen } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Layout } from "@/app/components/layout/Layout"
import { useSelector } from "react-redux"
import { RootState } from "@/store"

export default function Dashboard() {
  // Get user from Redux store
  const user = useSelector((state: RootState) => state.auth.user);
  
  // Parse first name from full name
  const fullName = user?.name || "User";
  // Split by space and take the first part as the first name
  const firstName = fullName.split(' ')[0];
  
  // Format current date
  const currentDate = new Date()
  const options: Intl.DateTimeFormatOptions = {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  }
  const formattedDate = currentDate.toLocaleDateString('en-US', options)
  
  // Format current time
  const timeOptions: Intl.DateTimeFormatOptions = {
    hour: 'numeric',
    minute: 'numeric',
    hour12: true
  }
  const formattedTime = currentDate.toLocaleTimeString('en-US', timeOptions)

  return (
    <Layout>
      {/* Welcome banner */}
      <div className="bg-blue-600 p-8 text-white">
        <h1 className="mb-1 text-3xl font-bold">Welcome back, {firstName}!</h1>
        <p className="mb-1">{formattedDate} | {formattedTime}</p>
        <p className="italic">"Excellence is not a skill. It's an attitude."</p>
      </div>
      
      {/* Quick actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 p-4">
        <Card className="flex flex-col items-center p-4 text-center hover:shadow-md cursor-pointer transition-all">
          <MessageSquare className="mb-2 h-8 w-8 text-blue-500" />
          <p className="font-medium">Chat with Advisor</p>
        </Card>
        <Card className="flex flex-col items-center p-4 text-center hover:shadow-md cursor-pointer transition-all">
          <Calendar className="mb-2 h-8 w-8 text-blue-500" />
          <p className="font-medium">Schedule Meeting</p>
        </Card>
        <Card className="flex flex-col items-center p-4 text-center hover:shadow-md cursor-pointer transition-all">
          <FileText className="mb-2 h-8 w-8 text-blue-500" />
          <p className="font-medium">View Reports</p>
        </Card>
        <Card className="flex flex-col items-center p-4 text-center hover:shadow-md cursor-pointer transition-all">
          <GraduationCap className="mb-2 h-8 w-8 text-blue-500" />
          <p className="font-medium">Academic Plan</p>
        </Card>
      </div>
      
      {/* Recent updates */}
      <div className="p-6">
        <h2 className="mb-4 text-xl font-semibold">Recent Updates</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <Card>
            <CardContent className="flex gap-4 p-4">
              <div className="rounded-full bg-blue-100 p-2 text-blue-500">
                <BookOpen className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <div className="mb-1 flex items-center justify-between">
                  <h3 className="font-medium">Course Registration Open</h3>
                  <span className="text-xs text-gray-500">2 hours ago</span>
                </div>
                <p className="text-sm text-gray-600">
                  Registration for Fall 2025 semester is now open. Please review your academic plan.
                </p>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="flex gap-4 p-4">
              <div className="rounded-full bg-green-100 p-2 text-green-500">
                <MessageSquare className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <div className="mb-1 flex items-center justify-between">
                  <h3 className="font-medium">Advisor Meeting Complete</h3>
                  <span className="text-xs text-gray-500">Yesterday</span>
                </div>
                <p className="text-sm text-gray-600">
                  Summary and notes from your recent advisor meeting are now available.
                </p>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="flex gap-4 p-4">
              <div className="rounded-full bg-amber-100 p-2 text-amber-500">
                <Calendar className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <div className="mb-1 flex items-center justify-between">
                  <h3 className="font-medium">Upcoming Deadline</h3>
                  <span className="text-xs text-gray-500">2 days ago</span>
                </div>
                <p className="text-sm text-gray-600">
                  Major declaration forms due in 5 days. Please submit through the portal.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  )
}