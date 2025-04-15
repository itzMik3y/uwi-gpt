// app/courses/page.tsx
"use client"

import { useState } from "react"
import { Search, Calendar, Smartphone, Database, ChevronRight } from "lucide-react"
import { Layout } from "@/app/components/layout/Layout"
import { useSelector } from "react-redux"
import { RootState } from "@/store"
import { Button } from "@/components/ui/button"
import Link from "next/link"
import { MoodleCourse } from "@/types/moodle"
export default function CoursesPage() {
  const [activeTab, setActiveTab] = useState("all")
  const courses = useSelector((state: RootState) => state.auth.courses) || []
  
  // Mock data as fallback if no courses in Redux store
  const mockCourses = [
    {
      id: 10079,
      fullname: "Group Project",
      shortname: "COMP3901 | S2_2024/25",
      idnumber: "COMP39010.202420",
      summary: "",
      summaryformat: 1,
      startdate: 1713070800,
      enddate: 1767993840,
      visible: true,
      showactivitydates: true,
      showcompletionconditions: true,
      fullnamedisplay: "COMP3901 | S2_2024/25 Group Project",
      viewurl: "https://vle.mona.uwi.edu/course/view.php?id=10079",
      progress: 0,
      hasprogress: false,
      isfavourite: false,
      hidden: false,
      showshortname: true,
      coursecategory: "COMP Undergraduate Courses"
    },
    {
      id: 10080,
      fullname: "Web Application Development",
      shortname: "COMP3385 | S1_2024/25",
      idnumber: "COMP33850.202410",
      progress: 35,
      coursecategory: "COMP Undergraduate Courses",
      startdate: 1693526400, // Sept 2023
      enddate: 1703980800, // Dec 2023
      summary: "Learn modern web development with HTML, CSS, JavaScript and frameworks.",
      summaryformat: 1,
      visible: true,
      showactivitydates: true,
      showcompletionconditions: true,
      fullnamedisplay: "COMP3385 | S1_2024/25 Web Application Development",
      viewurl: "/course/view.php?id=2",
      hasprogress: true,
      isfavourite: true,
      hidden: false,
      showshortname: true
    },
    {
      id: 10081,
      fullname: "Database Management Systems",
      shortname: "INFO3435 | S1_2024/25",
      idnumber: "INFO34350.202410",
      progress: 15,
      coursecategory: "COMP Undergraduate Courses",
      startdate: 1693526400, // Sept 2023
      enddate: 1703980800, // Dec 2023
      summary: "Learn database design, SQL, and database management principles.",
      summaryformat: 1,
      visible: true,
      showactivitydates: true,
      showcompletionconditions: true,
      fullnamedisplay: "INFO3435 | S1_2024/25 Database Management Systems",
      viewurl: "/course/view.php?id=3",
      hasprogress: true,
      isfavourite: false,
      hidden: false,
      showshortname: true
    }
  ];

  // Filter courses based on active tab
  const availableCourses = courses && courses.length > 0 ? courses : mockCourses;
  
  // Apply tab filtering
  const filteredCourses = activeTab === "all" 
    ? availableCourses
    : activeTab === "active" 
      ? availableCourses.filter(c => c.progress < 100)
      : availableCourses.filter(c => c.progress === 100);

  const formatDate = (timestamp: number) => {
    // Handle missing or invalid timestamps
    if (!timestamp) return "Not specified";
    
    try {
      // Check if timestamp is in seconds (Unix timestamp) and convert to milliseconds if needed
      const milliseconds = timestamp < 10000000000 ? timestamp * 1000 : timestamp;
      const date = new Date(milliseconds);
      
      // Check if date is valid
      if (isNaN(date.getTime())) return "Not specified";
      return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
    } catch (error) {
      return "Not specified";
    }
  }
  
  // Generate a course icon based on course code
  const getCourseIcon = (course: MoodleCourse) => {
    const shortname = course.shortname || "";
    
    if (shortname.includes('COMP') || shortname.includes('SWEN')) {
      return (
        <div className="bg-purple-100 text-purple-600 rounded-lg h-12 w-12 flex items-center justify-center">
          <div className="text-2xl font-mono">&lt;/&gt;</div>
        </div>
      );
    } else if (shortname.includes('INFO') || shortname.includes('DATA')) {
      return (
        <div className="bg-green-100 text-green-600 rounded-lg h-12 w-12 flex items-center justify-center">
          <Database className="h-6 w-6" />
        </div>
      );
    } else {
      return (
        <div className="bg-blue-100 text-blue-600 rounded-lg h-12 w-12 flex items-center justify-center">
          <Smartphone className="h-6 w-6" />
        </div>
      );
    }
  }

  return (
    <Layout>
      <div className="container mx-auto p-6 h-screen flex flex-col">
        <div className="mb-6">
          <h1 className="text-3xl font-bold mb-1">My Courses</h1>
          <p className="text-gray-600">Semester 1, 2024/25 Academic Year</p>
        </div>

        {/* Search and Filters */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
          <div className="relative w-full md:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search courses..."
              className="w-full rounded-lg border border-gray-300 pl-10 pr-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div className="flex gap-2">
            <Button
              variant={activeTab === "all" ? "default" : "outline"}
              onClick={() => setActiveTab("all")}
              className="rounded-md"
            >
              All Courses
            </Button>
            <Button
              variant={activeTab === "active" ? "default" : "outline"}
              onClick={() => setActiveTab("active")}
              className="rounded-md"
            >
              Active
            </Button>
            <Button
              variant={activeTab === "completed" ? "default" : "outline"}
              onClick={() => setActiveTab("completed")}
              className="rounded-md"
            >
              Completed
            </Button>
          </div>
        </div>

        {/* Course List - Scrollable Container */}
        <div className="overflow-y-auto flex-grow pr-1">
          <div className="space-y-6 pb-4">
            {filteredCourses.map((course) => (
              <div key={course.id} className="bg-white rounded-lg shadow border border-gray-100">
                <div className="flex flex-col md:flex-row md:items-center p-6 gap-4">
                  {/* Course Icon */}
                  <div className="flex-shrink-0">
                    {getCourseIcon(course)}
                  </div>

                  {/* Course Info */}
                  <div className="flex-grow">
                    <h2 className="text-xl font-semibold mb-1">{course.fullname}</h2>
                    <div className="text-sm text-gray-600 mb-2">
                      {/* Parse shortname to extract just the course code if needed */}
                      {course.shortname?.includes('|') ? course.shortname.split('|')[0].trim() : course.shortname} | {course.idnumber?.split('.')[0] || course.idnumber}
                    </div>
                    <div className="flex items-center text-xs text-gray-500">
                      <Calendar className="h-3.5 w-3.5 mr-1" />
                      <span>
                        {formatDate(course.startdate)} - {formatDate(course.enddate)}
                      </span>
                      <span className="mx-2">•</span>
                      <span>{course.coursecategory}</span>
                    </div>
                  </div>

                  {/* Course Progress */}
                  <div className="flex flex-col md:items-end gap-4 mt-4 md:mt-0">
                    <div className="flex flex-col items-center md:items-end">
                      <div className="text-sm font-medium mb-1">Progress</div>
                      <div className={`text-2xl font-bold ${
                        course.progress > 50 ? 'text-green-600' : 
                        course.progress > 20 ? 'text-purple-600' : 
                        'text-blue-600'
                      }`}>
                        {course.progress || 0}%
                      </div>
                    </div>
                    <Link href={`/courses/${course.id}`}>
                      <Button className="w-full md:w-auto">
                        View Course
                      </Button>
                    </Link>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Layout>
  )
}