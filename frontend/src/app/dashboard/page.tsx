// app/dashboard/page.tsx
"use client"

import Link from "next/link"
import { MessageSquare, Calendar, FileText, GraduationCap, BookOpen, Clock, ChevronRight } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Layout } from "@/app/components/layout/Layout"
import { useSelector } from "react-redux"
import { RootState } from "@/store"

export default function Dashboard() {
  // Get user from Redux store
  const user = useSelector((state: RootState) => state.auth.user);
  
  // Get courses from Redux store
  const courses = useSelector((state: RootState) => state.auth.courses) || [];
  
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
        <Link href="/chat" className="block h-full">
          <Card className="h-full">
            <CardContent className="p-4">
              <div className="flex flex-col items-center text-center">
                <div className="rounded-full bg-blue-100 p-3 flex items-center justify-center w-14 h-14 mb-3">
                  <MessageSquare className="h-6 w-6 text-blue-500" />
                </div>
                <p className="font-medium">Chat with Advisor</p>
              </div>
            </CardContent>
          </Card>
        </Link>
        
        <Link href="/schedule" className="block h-full">
          <Card className="h-full">
            <CardContent className="p-4">
              <div className="flex flex-col items-center text-center">
                <div className="rounded-full bg-blue-100 p-3 flex items-center justify-center w-14 h-14 mb-3">
                  <Calendar className="h-6 w-6 text-blue-500" />
                </div>
                <p className="font-medium">Schedule Meeting</p>
              </div>
            </CardContent>
          </Card>
        </Link>
        
        <Link href="/reports" className="block h-full">
          <Card className="h-full">
            <CardContent className="p-4">
              <div className="flex flex-col items-center text-center">
                <div className="rounded-full bg-blue-100 p-3 flex items-center justify-center w-14 h-14 mb-3">
                  <FileText className="h-6 w-6 text-blue-500" />
                </div>
                <p className="font-medium">View Reports</p>
              </div>
            </CardContent>
          </Card>
        </Link>
        
        <Link href="/academic-plan" className="block h-full">
          <Card className="h-full">
            <CardContent className="p-4">
              <div className="flex flex-col items-center text-center">
                <div className="rounded-full bg-blue-100 p-3 flex items-center justify-center w-14 h-14 mb-3">
                  <GraduationCap className="h-6 w-6 text-blue-500" />
                </div>
                <p className="font-medium">Academic Plan</p>
              </div>
            </CardContent>
          </Card>
        </Link>
      </div>
      
      {/* Current Courses */}
      <div className="bg-gray-50 py-4 px-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">Current Courses</h2>
          <Link href="/courses" className="text-blue-600 text-sm flex items-center">
            View All <ChevronRight className="h-4 w-4 ml-1" />
          </Link>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {courses.slice(0, 3).map((course) => (
            <div key={course.id} className="bg-white rounded-lg shadow">
              <div className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <div className={`${course.id === 1 ? 'bg-blue-100' : 'bg-purple-100'} rounded-md p-2 flex items-center justify-center h-10 w-10`}>
                      {course.id === 1 ? 
                        <div className="text-blue-500 text-lg">JS</div> : 
                        <div className="text-purple-500 text-lg">M</div>
                      }
                    </div>
                    <div>
                      <h3 className="font-medium text-base">{course.shortname || (course.id === 1 ? "COMP3385" : "MATH2410")}</h3>
                      <p className="text-sm text-gray-600">
                        {course.fullname}
                      </p>
                    </div>
                  </div>
                  <div>
                    <span className="inline-block bg-green-100 text-green-600 text-xs px-3 py-1 rounded-full">In Progress</span>
                  </div>
                </div>
                
                <div className="flex text-xs text-gray-500 mb-3 mt-3">
                  <div className="flex items-center mr-4">
                    <Clock className="h-4 w-4 mr-1 text-gray-400" />
                    <span>{course.id === 1 ? "Mon, Wed 10:00 AM" : "Thu, Fri 2:00 PM"}</span>
                  </div>
                  <div className="flex items-center">
                    <GraduationCap className="h-4 w-4 mr-1 text-gray-400" />
                    <span>{course.id === 1 ? "Dr. Smith" : "Dr. Johnson"}</span>
                  </div>
                </div>
              </div>
              
              <div className="border-t border-gray-100 px-4 py-3">
                <div className="flex justify-between items-center text-sm mb-2">
                  <div className="font-medium">Progress: {course.progress || (course.id === 1 ? "85" : "75")}%</div>
                  <div className="font-medium">Grade: {course.id === 1 ? "A-" : "B+"}</div>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-1.5">
                  <div 
                    className={course.id === 1 ? "bg-blue-500 h-1.5 rounded-full" : "bg-purple-500 h-1.5 rounded-full"} 
                    style={{ width: `${course.progress || (course.id === 1 ? 85 : 75)}%` }}
                  ></div>
                </div>
              </div>
            </div>
          ))}
          
          {/* If no courses are available from the store, show placeholder courses */}
          {courses.length === 0 && (
            <>
              <div className="bg-white rounded-lg shadow">
                <div className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <div className="bg-blue-100 rounded-md p-2 flex items-center justify-center h-10 w-10">
                        <div className="text-blue-500 text-lg">JS</div>
                      </div>
                      <div>
                        <h3 className="font-medium text-base">COMP3385</h3>
                        <p className="text-sm text-gray-600">Web Development</p>
                      </div>
                    </div>
                    <div>
                      <span className="inline-block bg-green-100 text-green-600 text-xs px-3 py-1 rounded-full">In Progress</span>
                    </div>
                  </div>
                  
                  <div className="flex text-xs text-gray-500 mb-3 mt-3">
                    <div className="flex items-center mr-4">
                      <Clock className="h-4 w-4 mr-1 text-gray-400" />
                      <span>Mon, Wed 10:00 AM</span>
                    </div>
                    <div className="flex items-center">
                      <GraduationCap className="h-4 w-4 mr-1 text-gray-400" />
                      <span>Dr. Smith</span>
                    </div>
                  </div>
                </div>
                
                <div className="border-t border-gray-100 px-4 py-3">
                  <div className="flex justify-between items-center text-sm mb-2">
                    <div className="font-medium">Progress: 85%</div>
                    <div className="font-medium">Grade: A-</div>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-1.5">
                    <div 
                      className="bg-blue-500 h-1.5 rounded-full" 
                      style={{ width: '85%' }}
                    ></div>
                  </div>
                </div>
              </div>
              
              <div className="bg-white rounded-lg shadow">
                <div className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <div className="bg-purple-100 rounded-md p-2 flex items-center justify-center h-10 w-10">
                        <div className="text-purple-500 text-lg">M</div>
                      </div>
                      <div>
                        <h3 className="font-medium text-base">MATH2410</h3>
                        <p className="text-sm text-gray-600">Advanced Calculus</p>
                      </div>
                    </div>
                    <div>
                      <span className="inline-block bg-green-100 text-green-600 text-xs px-3 py-1 rounded-full">In Progress</span>
                    </div>
                  </div>
                  
                  <div className="flex text-xs text-gray-500 mb-3 mt-3">
                    <div className="flex items-center mr-4">
                      <Clock className="h-4 w-4 mr-1 text-gray-400" />
                      <span>Thu, Fri 2:00 PM</span>
                    </div>
                    <div className="flex items-center">
                      <GraduationCap className="h-4 w-4 mr-1 text-gray-400" />
                      <span>Dr. Johnson</span>
                    </div>
                  </div>
                </div>
                
                <div className="border-t border-gray-100 px-4 py-3">
                  <div className="flex justify-between items-center text-sm mb-2">
                    <div className="font-medium">Progress: 75%</div>
                    <div className="font-medium">Grade: B+</div>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-1.5">
                    <div 
                      className="bg-purple-500 h-1.5 rounded-full" 
                      style={{ width: '75%' }}
                    ></div>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
      
      {/* Recent updates */}
      <div className="p-6">
        <h2 className="mb-4 text-xl font-semibold">Recent Updates</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <Card>
            <CardContent className="flex gap-4 p-4">
              <div className="rounded-full bg-blue-100 p-2 flex items-center justify-center h-10 w-10 shrink-0">
                <BookOpen className="h-5 w-5 text-blue-500" />
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
              <div className="rounded-full bg-green-100 p-2 flex items-center justify-center h-10 w-10 shrink-0">
                <MessageSquare className="h-5 w-5 text-green-500" />
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
              <div className="rounded-full bg-amber-100 p-2 flex items-center justify-center h-10 w-10 shrink-0">
                <Calendar className="h-5 w-5 text-amber-500" />
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