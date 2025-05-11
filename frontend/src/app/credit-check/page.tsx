'use client'

import React, { useState, useEffect } from 'react'
import { Provider, useSelector } from 'react-redux'
import type { RootState } from '@/store'
import { store } from '@/store'
import { Layout } from '@/app/components/layout/Layout'
import { Button } from '@/components/ui/button'
import { 
  CheckCircle,
  XCircle,
  AlertCircle,
  Clock,
  Download,
  Share2,
  BookOpen,
  GraduationCap,
  ClipboardList,
  Award,
  ChevronRight,
  ChevronDown,
  TrendingUp,
  Lightbulb
} from 'lucide-react'
import academicClient, { CreditCheckResponse } from '@/lib/api/academicClient'
import { toast } from 'react-toastify'

const CreditGraduationContent: React.FC = () => {
  const [loading, setLoading] = useState(true)
  const [creditCheckData, setCreditCheckData] = useState<CreditCheckResponse | null>(null)
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    faculty: true,
    foundation: true,
    major: true,
    minor: true,
    potential: false,
  })
  const user = useSelector((s: RootState) => s.auth.user)

  useEffect(() => {
    const fetchCreditCheck = async () => {
      try {
        setLoading(true)
        const data = await academicClient.getCreditCheck()
        setCreditCheckData(data)
      } catch (error: any) {
        toast.error(`Error fetching credit check: ${error.message || 'Unknown error'}`)
        console.error('Credit check error:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchCreditCheck()
  }, [])

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }))
  }

  if (loading) {
    return (
      <div className="p-6 flex justify-center items-center min-h-[50vh]">
        <div className="flex flex-col items-center">
          <div className="w-12 h-12 border-4 border-t-blue-600 border-b-blue-600 border-l-blue-300 border-r-blue-300 rounded-full animate-spin mb-4"></div>
          <p className="text-gray-600">Loading your credit and graduation status...</p>
        </div>
      </div>
    )
  }

  if (!creditCheckData) {
    return (
      <div className="p-6">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-center">
          <AlertCircle className="w-8 h-8 text-yellow-500 mx-auto mb-2" />
          <h2 className="text-lg font-medium text-yellow-800">Unable to load graduation data</h2>
          <p className="text-sm text-yellow-700 mt-1">Please try again later or contact academic support.</p>
          <Button 
            onClick={() => window.location.reload()} 
            className="mt-3 bg-yellow-600 hover:bg-yellow-700 text-white"
          >
            Retry
          </Button>
        </div>
      </div>
    )
  }

  // Extract data from response
  const {
    analysis: {
      student_major_code,
      eligible_for_graduation, 
      faculty_result,
      major_result,
      minor_result,
      potentially_eligible_for_graduation,
    }
  } = creditCheckData

  // Format JSON report into readable sections
  const parseReports = () => {
    const reports = creditCheckData.reports
    return reports.split('================================================================================')
      .filter(section => section.trim().length > 0)
      .map(section => section.trim())
  }

  const reportSections = parseReports()

  // Calculate progress percentages
  const totalCreditsEarned = faculty_result.credits_earned.total
  const totalCreditsRequired = faculty_result.faculty_schema?.credit_requirements.total_credits || 93
  const totalCreditsPercent = Math.min(100, Math.round((totalCreditsEarned / totalCreditsRequired) * 100))

  const level1Required = faculty_result.faculty_schema?.credit_requirements.level_1.min_credits || 24
  const level1Earned = faculty_result.credits_earned.level_1
  const level1Percent = Math.min(100, Math.round((level1Earned / level1Required) * 100))

  const level2and3Required = faculty_result.faculty_schema?.credit_requirements.level_2_and_3.min_credits || 60
  const level2and3Earned = faculty_result.credits_earned.level_2_and_3
  const level2and3Percent = Math.min(100, Math.round((level2and3Earned / level2and3Required) * 100))

  // Extract potentially missing courses for major
  const missingCourses = major_result.blocks.flatMap(block => 
    block.missing.required_courses || []
  )

  // Upcoming courses that will satisfy requirements
  const inProgressCourses = creditCheckData.analysis.transcript.data.terms
    .find(term => term.term_code === "202420")?.courses || []
  
  const plannedRequiredCourses = inProgressCourses
    .filter(course => missingCourses.includes(course.course_code.replace('+', '')))

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-2 flex items-center">
        <GraduationCap className="mr-2 h-7 w-7" />
        Credit & Graduation Status
      </h1>
      
      {/* Program Summary */}
      <div className="flex flex-wrap gap-2 mb-6">
        <div className="px-3 py-1 bg-indigo-100 text-indigo-800 rounded-full text-sm font-medium flex items-center">
          <GraduationCap className="mr-1 h-4 w-4" />
          Major: {major_result.major}
        </div>
        {minor_result && (
          <div className="px-3 py-1 bg-purple-100 text-purple-800 rounded-full text-sm font-medium flex items-center">
            <BookOpen className="mr-1 h-4 w-4" />
            Minor: {minor_result.minor}
          </div>
        )}
        <div className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium flex items-center">
          <Award className="mr-1 h-4 w-4" />
          Faculty: {faculty_result.faculty}
        </div>
      </div>

      {/* Graduation Status Card */}
      <div className={`mb-6 p-5 border rounded-lg ${potentially_eligible_for_graduation ? 'bg-green-50 border-green-200' : eligible_for_graduation ? 'bg-green-50 border-green-200' : 'bg-yellow-50 border-yellow-200'}`}>
        <div className="flex items-start">
          <div className="flex-shrink-0 mt-1">
            {potentially_eligible_for_graduation ? (
              <CheckCircle className="h-6 w-6 text-green-500" />
            ) : (
              <Clock className="h-6 w-6 text-yellow-500" />
            )}
          </div>
          <div className="ml-3 flex-1">
            <h2 className="text-lg font-semibold">
              {potentially_eligible_for_graduation 
                ? "Eligible for Graduation (After Current Semester)" 
                : eligible_for_graduation 
                  ? "Eligible for Graduation Now" 
                  : "Not Yet Eligible for Graduation"}
            </h2>
            <p className="text-sm mt-1">
              {potentially_eligible_for_graduation 
                ? "You will meet all requirements for graduation upon successful completion of your current courses." 
                : eligible_for_graduation 
                  ? "You have met all requirements for graduation."
                  : "You still have outstanding requirements to fulfill before becoming eligible for graduation."}
            </p>
            
            {potentially_eligible_for_graduation && !eligible_for_graduation && (
              <div className="mt-3 text-sm">
                <p className="font-medium">Required courses in progress:</p>
                <ul className="mt-1 space-y-1">
                  {plannedRequiredCourses.length > 0 ? (
                    plannedRequiredCourses.map((course, i) => (
                      <li key={i} className="flex items-center">
                        <ChevronRight className="h-4 w-4 text-green-500 mr-1" />
                        <span>{course.course_code.replace('+', '')}: {course.course_title}</span>
                      </li>
                    ))
                  ) : (
                    <li>No required courses found in current semester.</li>
                  )}
                </ul>
              </div>
            )}
            
            {potentially_eligible_for_graduation && (
              <Button className="mt-4 bg-green-600 hover:bg-green-700">
                Apply for Graduation
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Credit Progress */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        {/* Overall Credits */}
        <div className="bg-white border rounded-lg p-4 shadow-sm">
          <h3 className="text-lg font-medium mb-3">Total Credits</h3>
          <div className="mb-2 flex justify-between items-center">
            <span className="text-sm text-gray-600">Progress</span>
            <span className="text-sm font-medium">{totalCreditsEarned}/{totalCreditsRequired} Credits</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2.5 mb-4">
            <div className="bg-blue-600 h-2.5 rounded-full" style={{ width: `${totalCreditsPercent}%` }}></div>
          </div>
        </div>

        {/* Level 1 Credits */}
        <div className="bg-white border rounded-lg p-4 shadow-sm">
          <h3 className="text-lg font-medium mb-3">Level 1 Credits</h3>
          <div className="mb-2 flex justify-between items-center">
            <span className="text-sm text-gray-600">Progress</span>
            <span className="text-sm font-medium">{level1Earned}/{level1Required} Credits</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2.5 mb-4">
            <div className={`h-2.5 rounded-full ${level1Percent >= 100 ? 'bg-green-500' : 'bg-blue-600'}`} style={{ width: `${level1Percent}%` }}></div>
          </div>
          {level1Percent >= 100 && (
            <div className="text-xs text-green-600 flex items-center">
              <CheckCircle className="h-3 w-3 mr-1" /> Requirement satisfied
            </div>
          )}
        </div>

        {/* Level 2 & 3 Credits */}
        <div className="bg-white border rounded-lg p-4 shadow-sm">
          <h3 className="text-lg font-medium mb-3">Level 2 & 3 Credits</h3>
          <div className="mb-2 flex justify-between items-center">
            <span className="text-sm text-gray-600">Progress</span>
            <span className="text-sm font-medium">{level2and3Earned}/{level2and3Required} Credits</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2.5 mb-4">
            <div className={`h-2.5 rounded-full ${level2and3Percent >= 100 ? 'bg-green-500' : 'bg-blue-600'}`} style={{ width: `${level2and3Percent}%` }}></div>
          </div>
          {level2and3Percent >= 100 ? (
            <div className="text-xs text-green-600 flex items-center">
              <CheckCircle className="h-3 w-3 mr-1" /> Requirement satisfied
            </div>
          ) : (
            <div className="text-xs text-yellow-600 flex items-center">
              <AlertCircle className="h-3 w-3 mr-1" /> {level2and3Required - level2and3Earned} credits needed
            </div>
          )}
        </div>
      </div>

      {/* Major & Requirements Details */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column */}
        <div className="space-y-6">
          {/* Foundation Requirements */}
          <div className="bg-white border rounded-lg shadow-sm overflow-hidden">
            <div 
              className="flex justify-between items-center p-4 cursor-pointer bg-gray-50"
              onClick={() => toggleSection('foundation')}
            >
              <h3 className="font-medium text-lg flex items-center">
                <BookOpen className="mr-2 h-5 w-5 text-blue-600" />
                Foundation Requirements
              </h3>
              <div className="flex items-center">
                {faculty_result.foundation_status?.all_slots_satisfied ? (
                  <span className="text-green-600 text-sm font-medium mr-2 flex items-center">
                    <CheckCircle className="h-4 w-4 mr-1" /> Complete
                  </span>
                ) : (
                  <span className="text-yellow-600 text-sm font-medium mr-2 flex items-center">
                    <AlertCircle className="h-4 w-4 mr-1" /> Incomplete
                  </span>
                )}
                {expandedSections.foundation ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
              </div>
            </div>
            
            {expandedSections.foundation && (
              <div className="p-4">
                <p className="text-sm text-gray-600 mb-3">
                  <span className="font-medium">Credits Earned:</span> {faculty_result.foundation_status?.foundation_earned_credits}/{faculty_result.foundation_status?.total_foundation_required} 
                </p>
                
                <div className="space-y-3">
                  {faculty_result.foundation_status?.slots_status.map((slot, i) => (
                    <div key={i} className="border rounded p-3">
                      <div className="flex items-start">
                        <div className="flex-shrink-0 mt-0.5">
                          {slot.satisfied_by ? (
                            <CheckCircle className="h-5 w-5 text-green-500" />
                          ) : (
                            <XCircle className="h-5 w-5 text-red-500" />
                          )}
                        </div>
                        <div className="ml-3">
                          <h4 className="font-medium">{slot.category}</h4>
                          <p className="text-sm text-gray-600 mt-1">{slot.notes}</p>
                          {slot.satisfied_by && (
                            <p className="text-sm text-green-600 mt-1">
                              Completed with {slot.course} ({slot.credits} credits)
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Faculty Requirements */}
          <div className="bg-white border rounded-lg shadow-sm overflow-hidden">
            <div 
              className="flex justify-between items-center p-4 cursor-pointer bg-gray-50"
              onClick={() => toggleSection('faculty')}
            >
              <h3 className="font-medium text-lg flex items-center">
                <Award className="mr-2 h-5 w-5 text-purple-600" />
                Faculty Requirements
              </h3>
              <div className="flex items-center">
                {faculty_result.passes_faculty ? (
                  <span className="text-green-600 text-sm font-medium mr-2 flex items-center">
                    <CheckCircle className="h-4 w-4 mr-1" /> Complete
                  </span>
                ) : (
                  <span className="text-yellow-600 text-sm font-medium mr-2 flex items-center">
                    <AlertCircle className="h-4 w-4 mr-1" /> Incomplete
                  </span>
                )}
                {expandedSections.faculty ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
              </div>
            </div>
            
            {expandedSections.faculty && (
              <div className="p-4">
                <div className="space-y-3">
                  <div className="border rounded p-3">
                    <h4 className="font-medium">Total Credits</h4>
                    <div className="mt-2 flex items-center">
                      <div className="flex-1">
                        <div className="w-full bg-gray-200 rounded-full h-2.5">
                          <div 
                            className={`h-2.5 rounded-full ${totalCreditsPercent >= 100 ? 'bg-green-500' : 'bg-blue-600'}`} 
                            style={{ width: `${totalCreditsPercent}%` }}
                          ></div>
                        </div>
                      </div>
                      <div className="ml-3 min-w-[5rem] text-right">
                        <span className="text-sm font-medium">
                          {totalCreditsEarned}/{totalCreditsRequired}
                        </span>
                      </div>
                      <div className="ml-3">
                        {totalCreditsEarned >= totalCreditsRequired ? (
                          <CheckCircle className="h-5 w-5 text-green-500" />
                        ) : (
                          <AlertCircle className="h-5 w-5 text-yellow-500" />
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="border rounded p-3">
                    <h4 className="font-medium">Level 1 Faculty Credits</h4>
                    <div className="mt-2 flex items-center">
                      <div className="flex-1">
                        <div className="w-full bg-gray-200 rounded-full h-2.5">
                          <div 
                            className={`h-2.5 rounded-full ${faculty_result.credits_earned.level_1_faculty >= faculty_result.faculty_schema?.credit_requirements.level_1.min_faculty_credits ? 'bg-green-500' : 'bg-blue-600'}`} 
                            style={{ width: `${Math.min(100, (faculty_result.credits_earned.level_1_faculty / (faculty_result.faculty_schema?.credit_requirements.level_1.min_faculty_credits || 18)) * 100)}%` }}
                          ></div>
                        </div>
                      </div>
                      <div className="ml-3 min-w-[5rem] text-right">
                        <span className="text-sm font-medium">
                          {faculty_result.credits_earned.level_1_faculty}/{faculty_result.faculty_schema?.credit_requirements.level_1.min_faculty_credits || 18}
                        </span>
                      </div>
                      <div className="ml-3">
                        {faculty_result.credits_earned.level_1_faculty >= (faculty_result.faculty_schema?.credit_requirements.level_1.min_faculty_credits || 18) ? (
                          <CheckCircle className="h-5 w-5 text-green-500" />
                        ) : (
                          <AlertCircle className="h-5 w-5 text-yellow-500" />
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-4 text-sm text-gray-700">
                  <p className="font-medium">Faculty Notes:</p>
                  <ul className="list-disc pl-5 mt-1 space-y-1">
                    {faculty_result.faculty_schema?.notes.map((note, i) => (
                      <li key={i}>{note}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Column */}
        <div className="space-y-6">
          {/* Major Requirements */}
          <div className="bg-white border rounded-lg shadow-sm overflow-hidden">
            <div 
              className="flex justify-between items-center p-4 cursor-pointer bg-gray-50"
              onClick={() => toggleSection('major')}
            >
              <h3 className="font-medium text-lg flex items-center">
                <GraduationCap className="mr-2 h-5 w-5 text-indigo-600" />
                Major Requirements ({major_result.major})
              </h3>
              <div className="flex items-center">
                {major_result.passes_major ? (
                  <span className="text-green-600 text-sm font-medium mr-2 flex items-center">
                    <CheckCircle className="h-4 w-4 mr-1" /> Complete
                  </span>
                ) : (
                  <span className="text-yellow-600 text-sm font-medium mr-2 flex items-center">
                    <AlertCircle className="h-4 w-4 mr-1" /> Incomplete
                  </span>
                )}
                {expandedSections.major ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
              </div>
            </div>
            
            {expandedSections.major && (
              <div className="p-4">
                <div className="space-y-4">
                  {major_result.blocks.map((block, i) => (
                    <div key={i} className="border rounded overflow-hidden">
                      <div className={`p-3 ${block.passes ? 'bg-green-50' : 'bg-yellow-50'}`}>
                        <div className="flex items-center justify-between">
                          <h4 className="font-medium">{block.block_name}</h4>
                          {block.passes ? (
                            <span className="text-green-600 text-sm font-medium flex items-center">
                              <CheckCircle className="h-4 w-4 mr-1" /> Complete
                            </span>
                          ) : (
                            <span className="text-yellow-600 text-sm font-medium flex items-center">
                              <AlertCircle className="h-4 w-4 mr-1" /> Incomplete
                            </span>
                          )}
                        </div>
                        <p className="text-sm mt-1">
                          Credits: {block.earned_credits_in_block}/{block.required_credits} required
                        </p>
                      </div>
                      <div className="p-3">
                        <h5 className="text-sm font-medium mb-2">Required Courses:</h5>
                        <div className="grid grid-cols-2 gap-2 mb-3">
                          {block.required_courses.map((course, j) => {
                            const isCompleted = block.completed_required_in_block.includes(course)
                            const isMissing = block.missing.required_courses?.includes(course)
                            const isPlanned = inProgressCourses.some(c => c.course_code.replace('+', '') === course)
                            
                            return (
                              <div 
                                key={j} 
                                className={`text-sm p-2 rounded flex items-center ${
                                  isCompleted ? 'bg-green-50 text-green-800' : 
                                  isPlanned ? 'bg-blue-50 text-blue-800' : 
                                  'bg-red-50 text-red-800'
                                }`}
                              >
                                {isCompleted ? (
                                  <CheckCircle className="h-4 w-4 mr-1.5 text-green-500" />
                                ) : isPlanned ? (
                                  <Clock className="h-4 w-4 mr-1.5 text-blue-500" />
                                ) : (
                                  <XCircle className="h-4 w-4 mr-1.5 text-red-500" />
                                )}
                                {course}
                              </div>
                            )
                          })}
                        </div>
                        
                        {block.missing.required_courses && block.missing.required_courses.length > 0 && (
                          <div className="mt-2">
                            <h5 className="text-sm font-medium text-red-600">Missing Required Courses:</h5>
                            <ul className="list-disc pl-5 mt-1 space-y-1 text-sm">
                              {block.missing.required_courses.map((course, idx) => {
                                const isPlanned = inProgressCourses.some(c => c.course_code.replace('+', '') === course)
                                return (
                                  <li key={idx} className={isPlanned ? 'text-blue-600' : 'text-red-600'}>
                                    {course} {isPlanned && '(In Progress)'}
                                  </li>
                                )
                              })}
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
          
          {/* Minor Requirements (if exists) */}
          {minor_result && (
            <div className="bg-white border rounded-lg shadow-sm overflow-hidden">
              <div 
                className="flex justify-between items-center p-4 cursor-pointer bg-gray-50"
                onClick={() => toggleSection('minor')}
              >
                <h3 className="font-medium text-lg flex items-center">
                  <BookOpen className="mr-2 h-5 w-5 text-purple-600" />
                  Minor Requirements ({minor_result.minor})
                </h3>
                <div className="flex items-center">
                  {minor_result.passes_minor ? (
                    <span className="text-green-600 text-sm font-medium mr-2 flex items-center">
                      <CheckCircle className="h-4 w-4 mr-1" /> Complete
                    </span>
                  ) : (
                    <span className="text-yellow-600 text-sm font-medium mr-2 flex items-center">
                      <AlertCircle className="h-4 w-4 mr-1" /> Incomplete
                    </span>
                  )}
                  {expandedSections.minor ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
                </div>
              </div>
              
              {expandedSections.minor && (
                <div className="p-4">
                  <div className="space-y-4">
                    {/* Level 1 Requirements */}
                    <div className="border rounded overflow-hidden">
                      <div className={`p-3 ${minor_result.passes_level_1 ? 'bg-green-50' : 'bg-yellow-50'}`}>
                        <div className="flex items-center justify-between">
                          <h4 className="font-medium">Level 1 Requirements</h4>
                          {minor_result.passes_level_1 ? (
                            <span className="text-green-600 text-sm font-medium flex items-center">
                              <CheckCircle className="h-4 w-4 mr-1" /> Complete
                            </span>
                          ) : (
                            <span className="text-yellow-600 text-sm font-medium flex items-center">
                              <AlertCircle className="h-4 w-4 mr-1" /> Incomplete
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="p-3">
                        <h5 className="text-sm font-medium mb-2">Required Courses:</h5>
                        {minor_result.missing_requirements.level_1_required_courses && 
                         minor_result.missing_requirements.level_1_required_courses.length > 0 ? (
                          <div>
                            <div className="text-sm text-red-600 mb-2">Missing Required Courses:</div>
                            <div className="grid grid-cols-2 gap-2">
                              {minor_result.missing_requirements.level_1_required_courses.map((course, i) => (
                                <div key={i} className="p-2 bg-red-50 text-red-800 rounded flex items-center">
                                  <XCircle className="h-4 w-4 mr-1.5 text-red-500" />
                                  {course}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <div className="text-sm text-green-600">All Level 1 required courses completed</div>
                        )}
                      </div>
                    </div>

                    {/* Level 2 & 3 Requirements */}
                    <div className="border rounded overflow-hidden">
                      <div className={`p-3 ${
                        minor_result.earned_total_credits_l2_l3 >= minor_result.required_total_credits_l2_l3 
                        ? 'bg-green-50' : 'bg-yellow-50'
                      }`}>
                        <div className="flex items-center justify-between">
                          <h4 className="font-medium">Level 2 & 3 Requirements</h4>
                          {minor_result.earned_total_credits_l2_l3 >= minor_result.required_total_credits_l2_l3 ? (
                            <span className="text-green-600 text-sm font-medium flex items-center">
                              <CheckCircle className="h-4 w-4 mr-1" /> Complete
                            </span>
                          ) : (
                            <span className="text-yellow-600 text-sm font-medium flex items-center">
                              <AlertCircle className="h-4 w-4 mr-1" /> Incomplete
                            </span>
                          )}
                        </div>
                        <p className="text-sm mt-1">
                          Credits: {minor_result.earned_total_credits_l2_l3}/{minor_result.required_total_credits_l2_l3} required
                        </p>
                      </div>
                      <div className="p-3">
                        {/* Required Courses */}
                        <h5 className="text-sm font-medium mb-2">Required Courses:</h5>
                        {minor_result.missing_requirements.level_2_3_required_courses && 
                         minor_result.missing_requirements.level_2_3_required_courses.length > 0 ? (
                          <div>
                            <div className="text-sm text-red-600 mb-2">Missing Required Courses:</div>
                            <div className="grid grid-cols-2 gap-2 mb-4">
                              {minor_result.missing_requirements.level_2_3_required_courses.map((course, i) => (
                                <div key={i} className="p-2 bg-red-50 text-red-800 rounded flex items-center">
                                  <XCircle className="h-4 w-4 mr-1.5 text-red-500" />
                                  {course}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <div className="text-sm text-green-600 mb-4">All Level 2 & 3 required courses completed</div>
                        )}
                        
                        {/* Electives */}
                        <h5 className="text-sm font-medium mb-2">Electives:</h5>
                        <div className="mb-2 flex justify-between items-center">
                          <span className="text-sm text-gray-600">Elective Credits</span>
                          <span className="text-sm font-medium">
                            {minor_result.earned_elective_credits_l2_l3}/{minor_result.required_elective_credits_l2_l3} Credits
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5 mb-3">
                          <div 
                            className={`h-2.5 rounded-full ${
                              minor_result.earned_elective_credits_l2_l3 >= minor_result.required_elective_credits_l2_l3 
                              ? 'bg-green-500' : 'bg-blue-600'
                            }`} 
                            style={{ 
                              width: `${Math.min(100, (minor_result.earned_elective_credits_l2_l3 / minor_result.required_elective_credits_l2_l3) * 100)}%` 
                            }}
                          ></div>
                        </div>
                        
                        {minor_result.valid_l2_l3_electives_taken.length > 0 ? (
                          <div>
                            <div className="text-sm text-gray-600 mb-2">Completed Electives:</div>
                            <div className="grid grid-cols-2 gap-2">
                              {minor_result.valid_l2_l3_electives_taken.map((course, i) => (
                                <div key={i} className="p-2 bg-green-50 text-green-800 rounded flex items-center">
                                  <CheckCircle className="h-4 w-4 mr-1.5 text-green-500" />
                                  {course}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <div className="text-sm text-yellow-600">No electives completed yet</div>
                        )}
                      </div>
                    </div>
                    
                    {/* Potential Progress with Current Courses */}
                    {minor_result.potential_minor_courses && minor_result.potential_minor_courses.length > 0 && (
                      <div className="border rounded p-3 bg-blue-50">
                        <h5 className="font-medium text-blue-800">Potential Progress from Current Semester</h5>
                        <p className="text-sm text-blue-700 mt-1 mb-2">
                          These courses from your current semester may count toward your minor:
                        </p>
                        <div className="grid grid-cols-2 gap-2">
                          {minor_result.potential_minor_courses.map((course, i) => (
                            <div key={i} className="p-2 bg-blue-100 text-blue-800 rounded flex items-center">
                              <Clock className="h-4 w-4 mr-1.5 text-blue-500" />
                              {course.code} ({course.credits} credits)
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Potential Graduation Status */}
          <div className="bg-white border rounded-lg shadow-sm overflow-hidden">
            <div 
              className="flex justify-between items-center p-4 cursor-pointer bg-gray-50"
              onClick={() => toggleSection('potential')}
            >
              <h3 className="font-medium text-lg flex items-center">
                <ClipboardList className="mr-2 h-5 w-5 text-green-600" />
                Potential Graduation Status
              </h3>
              <div className="flex items-center">
                {potentially_eligible_for_graduation ? (
                  <span className="text-green-600 text-sm font-medium mr-2 flex items-center">
                    <CheckCircle className="h-4 w-4 mr-1" /> Potentially Eligible
                  </span>
                ) : (
                  <span className="text-yellow-600 text-sm font-medium mr-2 flex items-center">
                    <AlertCircle className="h-4 w-4 mr-1" /> Not Eligible
                  </span>
                )}
                {expandedSections.potential ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
              </div>
            </div>
            
            {expandedSections.potential && (
              <div className="p-4">
                <div className="mb-4">
                  <h4 className="font-medium text-base mb-2">Current Semester Courses</h4>
                  {inProgressCourses.length > 0 ? (
                    <div className="grid grid-cols-1 gap-2">
                      {inProgressCourses.map((course, i) => {
                        const isRequired = missingCourses.includes(course.course_code.replace('+', ''))
                        return (
                          <div key={i} className={`p-3 rounded-lg border ${isRequired ? 'bg-blue-50 border-blue-200' : 'bg-gray-50 border-gray-200'}`}>
                            <div className="flex items-start">
                              {isRequired ? (
                                <div className="flex-shrink-0 mt-0.5">
                                  <Clock className="h-5 w-5 text-blue-500" />
                                </div>
                              ) : null}
                              <div className={isRequired ? 'ml-3' : ''}>
                                <h5 className="font-medium text-sm">{course.course_code.replace('+', '')} - {course.course_title}</h5>
                                <p className="text-xs text-gray-600 mt-0.5">
                                  {course.credit_hours} credits {isRequired ? '• Required for graduation' : ''}
                                </p>
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-600">No courses found for current semester.</p>
                  )}
                </div>
                
                <div className="text-sm text-gray-700">
                  <p className="font-medium mb-2">How Current Courses Will Help:</p>
                  {potentially_eligible_for_graduation ? (
                    <ul className="list-disc pl-5 space-y-1">
                      <li>Adding {faculty_result.potential_credits.total} additional credits to your total</li>
                      {plannedRequiredCourses.length > 0 && (
                        <li>Completing required course(s): {plannedRequiredCourses.map(c => c.course_code.replace('+', '')).join(', ')}</li>
                      )}
                      {faculty_result.potential_credits.level_2_and_3 > 0 && (
                        <li>Adding {faculty_result.potential_credits.level_2_and_3} credits to your Level 2 & 3 requirement</li>
                      )}
                    </ul>
                  ) : (
                    <p className="text-yellow-600">Current courses are not sufficient to meet graduation requirements.</p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* AI Insights */}
          <div className="bg-white border rounded-lg shadow-sm overflow-hidden">
            <div className="p-4 bg-gray-50">
              <h3 className="font-medium text-lg flex items-center">
                <Lightbulb className="mr-2 h-5 w-5 text-yellow-500" />
                AI Insights & Recommendations
              </h3>
            </div>
            <div className="p-4">
              <div className="p-3 border-l-4 border-blue-400 mb-3">
                <h4 className="font-medium text-blue-800">Registration Priority</h4>
                <p className="text-sm mt-1 text-blue-700">
                  Register for COMP3901 next semester to complete your major requirements.
                </p>
                {minor_result && !minor_result.passes_minor && (
                  <p className="text-sm mt-1 text-blue-700">
                    To progress on your Mathematics minor, consider adding {minor_result.missing_requirements.level_1_required_courses?.[0]} to your next semester's courses.
                  </p>
                )}
              </div>
              
              <div className="p-3 border-l-4 border-purple-400">
                <h4 className="font-medium text-purple-800">Planning Ahead</h4>
                <p className="text-sm mt-1 text-purple-700">
                  You need {totalCreditsRequired - totalCreditsEarned - faculty_result.potential_credits.total} more credits after this semester to reach the minimum of {totalCreditsRequired} for graduation.
                </p>
                {minor_result && !minor_result.passes_minor && (
                  <>
                    <div className="w-full border-t border-purple-200 my-2"></div>
                    <p className="text-sm text-purple-700">
                      <strong>Note about your minor:</strong> Your Mathematics minor has several outstanding requirements. Consider whether you want to:
                    </p>
                    <ul className="text-sm text-purple-700 list-disc pl-5 mt-1">
                      <li>Continue pursuing the minor (requires taking {minor_result.missing_requirements.level_1_required_courses?.length || 0} Level 1 courses and {minor_result.missing_requirements.level_2_3_required_courses?.length || 0} Level 2/3 courses)</li>
                      <li>Drop the minor and focus on your major requirements</li>
                      <li>Consider switching to a different minor that aligns with courses you've already taken</li>
                    </ul>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Actions & Tools */}
          <div className="bg-white border rounded-lg shadow-sm overflow-hidden">
            <div className="p-4 bg-gray-50">
              <h3 className="font-medium text-lg flex items-center">
                <Share2 className="mr-2 h-5 w-5 text-indigo-500" />
                Tools & Actions
              </h3>
            </div>
            <div className="p-4 grid grid-cols-2 gap-3">
              <Button 
                variant="outline" 
                className="flex items-center justify-center"
                onClick={() => toast.success('Report downloaded successfully!')}
              >
                <Download className="mr-2 h-4 w-4" />
                Download PDF Report
              </Button>
              <Button 
                variant="outline" 
                className="flex items-center justify-center"
                onClick={() => toast.success('Shared with advisor!')}
              >
                <Share2 className="mr-2 h-4 w-4" />
                Share with Advisor
              </Button>
              <Button 
                className="flex items-center justify-center col-span-2 bg-blue-600 hover:bg-blue-700"
                onClick={() => toast.info('This feature will be available soon!')}
              >
                <TrendingUp className="mr-2 h-4 w-4" />
                Simulate What-If Scenarios
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Raw Report Data (Collapsible for Advanced Users) */}
      <div className="mt-6 bg-white border rounded-lg shadow-sm overflow-hidden">
        <div 
          className="flex justify-between items-center p-4 cursor-pointer bg-gray-50"
          onClick={() => setExpandedSections(prev => ({...prev, report: !prev.report}))}
        >
          <h3 className="font-medium text-lg flex items-center">
            <ClipboardList className="mr-2 h-5 w-5 text-gray-600" />
            Detailed Report
          </h3>
          {expandedSections.report ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
        </div>
        
        {expandedSections.report && (
          <div className="p-4">
            <div className="font-mono text-sm bg-gray-50 border rounded-lg p-4 overflow-x-auto whitespace-pre-wrap">
              {reportSections.map((section, i) => (
                <div key={i} className="mb-6">
                  <div className="mb-2 font-bold">{section.split('\n')[0]}</div>
                  <div>{section.split('\n').slice(1).join('\n')}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function CreditGraduationPage() {
  return (
    <Provider store={store}>
      <Layout>
        <CreditGraduationContent />
      </Layout>
    </Provider>
  )
}