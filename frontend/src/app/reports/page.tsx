'use client'

import React, { useState } from 'react'
import { Provider, useSelector } from 'react-redux'
import type { RootState } from '@/store'
import { store } from '@/store'
import { Layout } from '@/app/components/layout/Layout'
import { Button } from '@/components/ui/button'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  BarChart,
  Bar
} from 'recharts'
import {
  ChevronRight,
  ChevronDown,
  RefreshCw,
  TrendingUp,
  Download,
  Share2,
  Lightbulb,
  ArrowUp,
  ArrowDown
} from 'lucide-react'
import { formatTermLabel } from '@/utils/termUtils'

/** Chart with multiple views including all‑time distribution,
 * all per‑term charts left‑to‑right chronological.
 */
const GradeTrendsChart: React.FC = () => {
  const [view, setView] = useState<
    | 'semester'
    | 'cumulative'
    | 'credits'
    | 'courses'
    | 'atRisk'
    | 'distribution'
  >('semester')
  const gradesData = useSelector((s: RootState) => s.auth.gradesData)

  // build per‑term metrics
  const terms =
    gradesData?.terms
      .filter((t) => t.term_code !== 'CURRENT')
      .map((t) => ({
        term: formatTermLabel(t.term_code),
        semester: t.semester_gpa ?? 0,
        cumulative: t.cumulative_gpa ?? 0,
        credits: t.courses.reduce((sum, c) => sum + c.credit_hours, 0),
        courses: t.courses.length,
        atRisk: t.courses.filter((c) => /^F|EI/.test(c.grade_earned)).length
      })) || []

  // reversed for chronological left‑to‑right
  const chartTerms = [...terms].reverse()

  // build all‑time grade distribution
  const allCourses = gradesData?.terms.flatMap((t) => t.courses) || []
  const distCounts: Record<string, number> = {}
  allCourses.forEach((c) => {
    distCounts[c.grade_earned] = (distCounts[c.grade_earned] || 0) + 1
  })
  const distribution = Object.entries(distCounts)
    .map(([grade, count]) => ({ grade, count }))
    .sort((a, b) => b.count - a.count)

  const options = [
    { key: 'semester', label: 'Semester GPA' },
    { key: 'cumulative', label: 'Cumulative GPA' },
    { key: 'credits', label: 'Credits/Term' },
    { key: 'courses', label: 'Courses/Term' },
    { key: 'atRisk', label: 'At‑Risk Count' },
    { key: 'distribution', label: 'All‑Time Distribution' }
  ] as const

  return (
    <div>
      {/* View selector */}
      <div className="flex flex-wrap justify-end gap-2 mb-3">
        {options.map((opt) => (
          <button
            key={opt.key}
            onClick={() => setView(opt.key)}
            className={`px-3 py-1 rounded-full text-xs font-medium ${
              view === opt.key
                ? 'bg-blue-600 text-white'
                : 'bg-gray-200 text-gray-700'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Chart area */}
      <ResponsiveContainer width="100%" height={300}>
        {view === 'distribution' ? (
          <BarChart data={distribution} margin={{ top: 10, bottom: 20 }}>
            <XAxis dataKey="grade" tick={{ fontSize: 12 }} />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="count" name="Courses" fill="#f97316" />
          </BarChart>
        ) : view === 'credits' || view === 'courses' || view === 'atRisk' ? (
          <BarChart data={chartTerms} margin={{ top: 10, bottom: 5 }}>
            <XAxis dataKey="term" tick={{ fontSize: 12 }} />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Bar
              dataKey={view}
              name={
                view === 'credits'
                  ? 'Credits'
                  : view === 'courses'
                  ? 'Courses'
                  : 'At‑Risk'
              }
              fill={
                view === 'atRisk'
                  ? '#ef4444'
                  : view === 'courses'
                  ? '#10b981'
                  : '#8b5cf6'
              }
            />
          </BarChart>
        ) : (
          <LineChart data={chartTerms} margin={{ top: 10, bottom: 5 }}>
            <XAxis dataKey="term" tick={{ fontSize: 12 }} />
            <YAxis domain={[0, view === 'semester' ? 4 : undefined]} />
            <Tooltip />
            <Legend />
            <Line
              type="monotone"
              dataKey={view}
              name={view === 'semester' ? 'Term GPA' : 'Cumulative GPA'}
              stroke="#3b82f6"
              strokeWidth={2}
            />
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}

/** Collapsible transcript section */
type SemesterSectionProps = {
  term: {
    term_code: string
    courses: {
      course_code: string
      course_title: string
      grade_earned: string
      credit_hours: number
    }[]
    semester_gpa: number | null
    cumulative_gpa: number | null
  }
  isOpen: boolean
  onToggle: () => void
}
const SemesterSection: React.FC<SemesterSectionProps> = ({
  term,
  isOpen,
  onToggle
}) => (
  <div className="border rounded-md overflow-hidden">
    <div
      className="flex items-center justify-between p-2 bg-gray-50 cursor-pointer"
      onClick={onToggle}
    >
      <h3 className="font-medium text-base">
        {formatTermLabel(term.term_code)}
      </h3>
      {isOpen ? <ChevronDown /> : <ChevronRight />}
    </div>
    {isOpen && (
      <div className="p-3 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="text-left">Course</th>
              <th className="text-center">Grade</th>
              <th className="text-center">Credits</th>
            </tr>
          </thead>
          <tbody>
            {term.courses.map((c, i) => (
              <tr key={i} className="border-t">
                <td className="py-1">
                  {c.course_code} – {c.course_title}
                </td>
                <td className="text-center py-1">{c.grade_earned}</td>
                <td className="text-center py-1">{c.credit_hours}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-gray-500">
          Semester GPA: {term.semester_gpa ?? 'N/A'} | 
          Cumulative GPA: {term.cumulative_gpa ?? 'N/A'}
        </p>
      </div>
    )}
  </div>
)

/** Main dashboard content */
const GradesDashboardContent: React.FC = () => {
  const gradesData = useSelector((s: RootState) => s.auth.gradesData)
  if (!gradesData) return <p>Loading…</p>

  const nonCurrent = gradesData.terms.filter((t) => t.term_code !== 'CURRENT')
  const latest = nonCurrent[0] || null
  const prev = nonCurrent[1] || null

  const currentGPA = latest?.semester_gpa ?? 0
  const delta = prev ? currentGPA - (prev.semester_gpa ?? 0) : 0

  const cumulativeGPA =
    gradesData.overall?.cumulative_gpa ?? latest?.cumulative_gpa ?? 0
  const cumPrev = prev?.cumulative_gpa ?? 0
  const cumDelta = cumulativeGPA - cumPrev

  const earnedCredits =
    gradesData.overall?.total_credits_earned ?? latest?.credits_earned_to_date ?? 0

  const atRisk =
    latest?.courses.filter((c) => /^F|EI/.test(c.grade_earned)) || []

  const classifyStanding = (g: number) => {
    if (g >= 3.7) return 'First Class'
    if (g >= 3.0) return 'Second Class (Upper)'
    if (g >= 2.0) return 'Second Class (Lower)'
    return 'Pass'
  }
  const standing = classifyStanding(cumulativeGPA)

  const [openTerms, setOpenTerms] = useState<string[]>([])
  const toggleTerm = (code: string) =>
    setOpenTerms((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    )

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">My Grades & Insights</h1>

      {/* Summary cards */}
      <div className="grid grid-cols-5 gap-4 mb-8">
        {/* Current GPA */}
        <div className="p-4 bg-white border rounded-lg shadow-sm">
          <div className="flex justify-between mb-1 text-xs text-gray-600">
            <span>Current GPA</span>
            <TrendingUp className="text-blue-500" />
          </div>
          <div className="text-2xl font-semibold">{currentGPA.toFixed(2)}</div>
          {prev && (
            <div
              className={`mt-1 flex items-center text-xs font-medium ${
                delta >= 0 ? 'text-green-600' : 'text-red-600'
              }`}
            >
              {delta >= 0 ? <ArrowUp className="h-4 w-4 mr-1" /> : <ArrowDown className="h-4 w-4 mr-1" />}
              {delta >= 0 ? '+' : ''}{delta.toFixed(2)} from last term
            </div>
          )}
        </div>

        {/* Cumulative GPA */}
        <div className="p-4 bg-white border rounded-lg shadow-sm">
          <div className="flex justify-between mb-1 text-xs text-gray-600">
            <span>Cumulative GPA</span>
            <TrendingUp className="text-blue-500" />
          </div>
          <div className="text-2xl font-semibold">{cumulativeGPA.toFixed(2)}</div>
          {prev && (
            <div
              className={`mt-1 flex items-center text-xs font-medium ${
                cumDelta >= 0 ? 'text-green-600' : 'text-red-600'
              }`}
            >
              {cumDelta >= 0 ? <ArrowUp className="h-4 w-4 mr-1" /> : <ArrowDown className="h-4 w-4 mr-1" />}
              {cumDelta >= 0 ? '+' : ''}{cumDelta.toFixed(2)} from last term
            </div>
          )}
        </div>

        {/* Credits Earned */}
        <div className="p-4 bg-white border rounded-lg shadow-sm">
          <div className="flex justify-between mb-1 text-xs text-gray-600">
            <span>Credits Earned</span>
            <svg className="h-4 w-4 text-purple-500" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
              <path d="M6 12v5c0 2 2 3 6 3s6-1 6-3v-5" />
            </svg>
          </div>
          <div className="text-2xl font-semibold">{earnedCredits}</div>
        </div>

        {/* At‑Risk Courses */}
        <div className="p-4 bg-white border rounded-lg shadow-sm">
          <div className="flex justify-between mb-1 text-xs text-gray-600">
            <span>At‑Risk Courses</span>
            <svg className="h-4 w-4 text-red-500" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </div>
          <div className="text-2xl font-semibold">{atRisk.length}</div>
          {atRisk.length > 0 && <div className="mt-1 text-xs text-red-600">Action needed</div>}
        </div>

        {/* Class Standing */}
        <div className="p-4 bg-white border rounded-lg shadow-sm">
          <div className="flex justify-between mb-1 text-xs text-gray-600">
            <span>Class Standing</span>
            <svg className="h-4 w-4 text-yellow-500" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path d="M12 2v20" />
              <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
            </svg>
          </div>
          <div className="text-xl font-semibold">{standing}</div>
        </div>
      </div>

      {/* Main layout */}
      <div className="grid grid-cols-5 gap-6">
        {/* Left column */}
        <div className="col-span-3 space-y-6">
          <div className="bg-white border rounded-lg p-4">
            <h2 className="text-lg font-medium mb-4">Grade Trends</h2>
            <GradeTrendsChart />
          </div>
          <div className="bg-white border rounded-lg p-4">
            <h2 className="text-lg font-medium mb-4">Current Courses & Predictions</h2>
            {latest?.courses.map((c, i) => {
              const risk = /^F|EI/.test(c.grade_earned)
              return (
                <div
                  key={i}
                  className={`flex justify-between p-3 border rounded-lg mb-2 ${
                    risk ? 'bg-red-50 border-red-200' : ''
                  }`}
                >
                  <div>
                    <h3 className="font-medium">{c.course_title}</h3>
                    <span className="text-sm text-gray-500">{c.course_code}</span>
                  </div>
                  <span
                    className={`px-2 py-1 rounded-full text-sm ${
                      risk ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'
                    }`}
                  >
                    {risk ? `At Risk: ${c.grade_earned}` : `Predicted: ${c.grade_earned}`}
                  </span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Right column */}
        <div className="col-span-2 space-y-6">
          <div className="bg-white border rounded-lg p-4">
            <div className="flex justify-between mb-4">
              <h2 className="text-lg font-medium">AI Insights</h2>
              <RefreshCw className="cursor-pointer text-gray-400" />
            </div>
            <div className="p-3 border-l-4 border-yellow-400 mb-4">
              <Lightbulb className="inline-block mr-2" />
              Focus area identified: algorithm complexity in COMP3901.
            </div>
            <div className="p-3 border-l-4 border-green-400 bg-green-50">
              <TrendingUp className="inline-block mr-2 text-green-600" />
              Positive trend: mobile development improving.
            </div>
          </div>

          <div className="bg-white border rounded-lg p-4">
            <h2 className="text-lg font-medium mb-4">Academic Transcript</h2>
            <div className="space-y-4 overflow-y-auto max-h-96 px-1 pb-1">
              {nonCurrent.map((term) => (
                <SemesterSection
                  key={term.term_code}
                  term={term}
                  isOpen={openTerms.includes(term.term_code)}
                  onToggle={() => toggleTerm(term.term_code)}
                />
              ))}
            </div>
            <div className="flex space-x-2 mt-4">
              <Button className="flex items-center bg-blue-600 hover:bg-blue-700">
                <Download className="mr-2" />Export PDF
              </Button>
              <Button variant="outline" className="flex items-center">
                <Share2 className="mr-2" />Share
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function GradesDashboardPage() {
  return (
    <Provider store={store}>
      <Layout>
        <GradesDashboardContent />
      </Layout>
    </Provider>
  )
}
