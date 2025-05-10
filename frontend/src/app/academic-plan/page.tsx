'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { Provider, useSelector } from 'react-redux'
import type { RootState } from '@/store' // Assuming store setup
import { store } from '@/store' // Assuming store setup
import { Layout } from '@/app/components/layout/Layout' // Assuming layout component
import { Button } from '@/components/ui/button' // Assuming Button component
import {
  ChevronRight,
  ChevronLeft,
  Plus,
  Download,
  Share2,
  Calendar,
  FileText,
  Copy,
  Clock,
  FileCheck,
  Search,
  X,
  Trash2,
  AlertCircle, // Used for prerequisite warning
  CheckCircle2,
  RefreshCw,
  GraduationCap,
  Info,
  ClipboardList // Used for "Already in plan"
} from 'lucide-react'
import Image from 'next/image'
import academicClient, { CourseDetail } from '@/lib/api/academicClient' // Assuming academicClient
import { DndProvider, useDrag, useDrop } from 'react-dnd'
import { HTML5Backend } from 'react-dnd-html5-backend'

// DnD item types
const ItemTypes = {
  COURSE: 'course',
  EMPTY_SLOT: 'emptySlot'
}

// Interface for course items in the plan
interface CourseItem {
  id: string;
  code: string;
  title: string;
  credits: number;
  department?: string;
  grade?: string;
  status: 'completed' | 'in-progress' | 'planned';
  prereq?: any; // This is for display, not logic
  term_code?: string;
}

// Type for the raw prerequisite item from CourseDetail
type PrerequisiteJsonItem = CourseDetail['prerequisites'][0];

// Interface for transcript data
interface TranscriptData {
  terms: Array<{
    term_code: string;
    courses: Array<{
      course_code: string;
      course_title: string;
      credit_hours: number;
      grade_earned: string;
      whatif_grade: string;
    }>;
    semester_gpa: number | null;
    cumulative_gpa: number | null;
    degree_gpa: number | null;
    credits_earned_to_date: number | null;
  }>;
  overall: {
    cumulative_gpa: number | null;
    degree_gpa: number | null;
    total_credits_earned: number | null;
  };
}

// Interface for major result data
interface MajorResult {
  major: string;
  faculty: string;
  blocks: Array<{
    block_name: string;
    required_credits: number;
    required_courses: string[];
    alternative_substitutions: any[];
    earned_credits_in_block: number;
    potential_credits_in_block: number;
    completed_required_in_block: string[];
    missing: Record<string, any>;
    passes: boolean;
    notes: string;
  }>;
  passes_major: boolean;
  potential_courses: {
    credits_by_level: Record<string, number>;
    codes: string[];
  };
}

// Interface for faculty result data
interface FacultyResult {
  faculty: string;
  passes_faculty: boolean;
  credits_earned: {
    total: number;
    level_1: number;
    level_1_faculty: number;
    level_2_and_3: number;
    faculty_specific_status: Record<string, any>;
  };
  potential_credits: {
    total: number;
    level_1: number;
    level_1_faculty: number;
    level_2_and_3: number;
  };
  foundation_status: {
    all_slots_satisfied: boolean;
    meets_total_credits: boolean;
    slots_status: any[];
    foundation_earned_credits: number;
    total_foundation_required: number;
    excluded_courses_taken: any[];
    substitutions_used: number;
    max_substitutions_allowed: number;
  };
  language_status: any;
  missing_requirements: Record<string, any>;
  level1_faculty_courses_list: [string, number][];
}

// Interface for credit check response
interface CreditCheckResponse {
  analysis: {
    student_major_code: string;
    eligible_for_graduation: boolean;
    passes_all_requirements: boolean;
    potentially_eligible_for_graduation: boolean;
    potential_all_requirements_satisfied: boolean;
    faculty_result: FacultyResult;
    major_result: MajorResult;
    minor_result: any;
    faculty_schema: any; 
    major_schema: any; 
    minor_schema: any; 
    transcript: {
      data: TranscriptData;
    };
  };
  reports: string;
}

// Type for year data structure in the plan
interface YearPlanData {
  year: number; 
  academicYear: string; 
  semesters: Array<{
    id: string;
    number: number; 
    status: 'completed' | 'in-progress' | 'planning';
    courses: CourseItem[];
  }>;
}


/* —————————————————— Helper function to normalize course codes (remove + suffix) —————————————————— */
const normalizeCourseCode = (code: string): string => {
  if (!code) return '';
  return code.replace(/\+$/, ''); 
};

/* —————————————————— Progress Bar Component —————————————————— */
const ProgressBar: React.FC<{
  label: string;
  value: number;
  max: number;
  color: string;
}> = ({ label, value, max, color }) => (
  <div className="flex flex-col">
    <div className="flex justify-between mb-1">
      <span className="text-sm font-medium">{label}</span>
      <span className="text-sm text-gray-600">{value}/{max > 0 ? max : "?"}</span>
    </div>
    <div className="h-2 w-full bg-gray-200 rounded-full">
      <div
        className={`h-2 rounded-full ${color}`}
        style={{ width: `${max > 0 ? (value / max) * 100 : 0}%` }}
      ></div>
    </div>
  </div>
);

/* —————————————————— Graduation Status Component —————————————————— */
const GraduationStatus: React.FC<{
  creditCheck: CreditCheckResponse | null;
}> = ({ creditCheck }) => {
  if (!creditCheck) return null;

  const { 
    eligible_for_graduation, 
    potentially_eligible_for_graduation,
    potential_all_requirements_satisfied
  } = creditCheck.analysis;

  const inProgressCourses = creditCheck.analysis.transcript.data.terms
    .filter(term => term.courses.some(course => course.grade_earned === 'NA'))
    .flatMap(term => term.courses.filter(course => course.grade_earned === 'NA'));

  const isCourseTakenInProgress = (requiredCourse: string) => {
    const normalizedRequired = normalizeCourseCode(requiredCourse);
    return inProgressCourses.some(course => 
      normalizeCourseCode(course.course_code) === normalizedRequired
    );
  };

  const getMissingRequirements = () => {
    const missing = [];
    if (creditCheck.analysis.faculty_result && !creditCheck.analysis.faculty_result.passes_faculty && creditCheck.analysis.faculty_result.missing_requirements) {
      const facultyMissing = creditCheck.analysis.faculty_result.missing_requirements;
      if (facultyMissing.total_credits) {
        missing.push(`Total Credits: Need ${facultyMissing.total_credits} more`);
      }
      if (facultyMissing.level_2_and_3_credits) {
        missing.push(`Level 2/3 Credits: Need ${facultyMissing.level_2_and_3_credits} more`);
      }
    }
    if (creditCheck.analysis.major_result && !creditCheck.analysis.major_result.passes_major && 
        creditCheck.analysis.major_result.blocks && creditCheck.analysis.major_result.blocks.some(block => !block.passes)) {
      const incompleteBlocks = creditCheck.analysis.major_result.blocks.filter(block => !block.passes);
      incompleteBlocks.forEach(block => {
        if (block.missing && block.missing.required_courses?.length) {
          const missingReqCourses = block.missing.required_courses.filter((course: string) => !isCourseTakenInProgress(course));
          if (missingReqCourses.length > 0) {
            missing.push(`Missing Required Courses (${block.block_name || 'Major'}): ${missingReqCourses.join(', ')}`);
          }
        }
      });
    }
    return missing;
  };
  
  const missingRequirements = getMissingRequirements();
  const isGraduationReadyAfterCurrent = potentially_eligible_for_graduation && potential_all_requirements_satisfied;

  const getMissingCoursesBeingTaken = () => {
    if (!creditCheck.analysis.major_result?.blocks) return [];
    const allMissingCourses: string[] = [];
    creditCheck.analysis.major_result.blocks.forEach(block => {
      if (block.missing?.required_courses) {
        allMissingCourses.push(...block.missing.required_courses);
      }
    });
    return allMissingCourses.filter(course => isCourseTakenInProgress(course));
  };
  
  const missingCoursesBeingTaken = getMissingCoursesBeingTaken();

  return (
    <div className="bg-white border rounded-lg p-4">
      <h2 className="text-lg font-semibold mb-2 flex items-center">
        <GraduationCap className="h-5 w-5 mr-2" />
        Graduation Status
      </h2>
      <div className="mb-3 p-3 rounded-lg border border-gray-200">
        <div className="flex items-center mb-2">
          <div className={`w-3 h-3 rounded-full mr-2 ${eligible_for_graduation ? 'bg-green-500' : 'bg-red-500'}`}></div>
          <h3 className="font-medium">Current Status</h3>
        </div>
        <p className="text-sm">
          {eligible_for_graduation 
            ? "You are eligible to graduate based on completed courses."
            : "You are not currently eligible to graduate."}
        </p>
        {missingRequirements.length > 0 && !eligible_for_graduation && (
          <div className="mt-2">
            <p className="text-sm font-medium">Missing Requirements:</p>
            <ul className="text-xs text-gray-600 list-disc list-inside">
              {missingRequirements.map((req, i) => (
                <li key={i}>{req}</li>
              ))}
            </ul>
          </div>
        )}
        {missingCoursesBeingTaken.length > 0 && (
          <div className="mt-2 p-2 bg-blue-50 rounded">
            <p className="text-xs text-blue-700">
              <span className="font-medium">Note:</span> You are currently taking required course(s) that will satisfy some graduation requirements: {missingCoursesBeingTaken.join(', ')}.
            </p>
          </div>
        )}
      </div>
      {inProgressCourses.length > 0 && (
        <div className={`p-3 rounded-lg border ${isGraduationReadyAfterCurrent ? 'border-green-300 bg-green-50' : 'border-gray-200'}`}>
          <div className="flex items-center mb-2">
            <div className={`w-3 h-3 rounded-full mr-2 ${isGraduationReadyAfterCurrent ? 'bg-green-500' : 'bg-yellow-500'}`}></div>
            <h3 className="font-medium">After Current Courses</h3>
          </div>
          {isGraduationReadyAfterCurrent ? (
            <div className="mb-3">
              <p className="text-sm font-medium text-green-700">
                You will be eligible to graduate after completing your current courses!
              </p>
              <p className="text-xs text-green-600 mt-1">
                All graduation requirements will be satisfied when you pass these courses.
              </p>
            </div>
          ) : (
            <p className="text-sm mb-2">
              {potentially_eligible_for_graduation 
                ? "You will be closer to graduation requirements after your current courses."
                : "You will still need additional requirements after your current courses."}
            </p>
          )}
          {inProgressCourses.length > 0 && (
            <div className="mt-2">
              <p className="text-sm font-medium">In-Progress Courses:</p>
              <div className="flex flex-wrap gap-1 mt-1">
                {inProgressCourses.map((course, i) => {
                  const isMissingRequirement = creditCheck.analysis.major_result?.blocks?.some(block => 
                    block.missing?.required_courses?.some((requiredCourse: string) => 
                      normalizeCourseCode(requiredCourse) === normalizeCourseCode(course.course_code)
                    )
                  ) || false;
                  return (
                    <span 
                      key={i} 
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        isMissingRequirement 
                          ? 'bg-purple-100 text-purple-800' 
                          : isGraduationReadyAfterCurrent 
                            ? 'bg-green-100 text-green-800' 
                            : 'bg-blue-100 text-blue-800'
                      }`}
                      title={isMissingRequirement ? "Fulfills a missing requirement" : ""}
                    >
                      {course.course_code}
                      {isMissingRequirement && (
                        <span className="ml-1 text-purple-800">★</span>
                      )}
                    </span>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
      <div className="mt-3 p-2 bg-blue-50 rounded text-xs text-blue-700 flex items-start">
        <Info className="h-4 w-4 mr-1 flex-shrink-0 mt-0.5" />
        <div>
          {isGraduationReadyAfterCurrent 
            ? "Maintain good academic standing in your current courses to remain eligible for graduation."
            : "Review your plan and the detailed graduation report to fulfill all requirements."}
        </div>
      </div>
    </div>
  );
};

/* —————————————————— Draggable Course Item Component (in plan) —————————————————— */
const PlannedCourseItem: React.FC<{ 
  course: CourseItem; 
  onRemove?: (id: string) => void;
  isDraggable?: boolean;
}> = ({ course, onRemove, isDraggable = true }) => {
  const statusStyles = {
    completed: 'bg-white border-green-200 border',
    'in-progress': 'bg-blue-50 border-2 border-dashed border-blue-200',
    planned: 'bg-white border-2 border-dashed border-green-200'
  };

  const [{ isDragging }, drag] = useDrag(() => ({
    type: ItemTypes.COURSE,
    item: { ...course }, 
    collect: (monitor) => ({
      isDragging: !!monitor.isDragging()
    }),
    canDrag: isDraggable && course.status !== 'completed'
  }));

  return (
    <div 
      ref={isDraggable ? drag : null}
      className={`p-3 rounded-lg ${statusStyles[course.status]} ${isDragging ? 'opacity-50' : ''} ${isDraggable && course.status !== 'completed' ? 'cursor-grab' : 'cursor-default'} hover:shadow-sm transition-shadow relative`}
    >
      <div className="flex justify-between items-center">
        <div>
          <h3 className="font-medium">{course.code}</h3>
          <span className="text-sm text-gray-500">{course.title}</span>
          {course.term_code && (
            <div className="text-xs text-gray-400 mt-1">Term: {formatTermCode(course.term_code)}</div>
          )}
        </div>
        <div className="flex items-center">
          {course.grade && (
            <span className={`mr-2 px-1.5 py-0.5 rounded text-xs font-semibold ${getGradeColor(course.grade)}`}>
              {course.grade}
            </span>
          )}
          {course.status === 'in-progress' && !course.grade && (
            <span className="text-blue-500 mr-2"><Clock size={16} /></span>
          )}
          {course.status === 'planned' && onRemove && (
            <button 
              onClick={() => onRemove(course.id)}
              className="text-red-400 hover:text-red-600 p-1 rounded-full hover:bg-red-50"
              aria-label={`Remove ${course.code}`}
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/* Helper function to format term codes FOR DISPLAY in PlannedCourseItem */
const formatTermCode = (termCode: string): string => {
  if (termCode === 'CURRENT') return 'Current Term';
  const year = termCode.slice(0, 4); 
  const suffix = termCode.slice(4); 
  const nextYearShort = String(parseInt(year) + 1).slice(2); 
  let name: string;
  switch (suffix) {
    case '10': name = 'Semester I'; break;
    case '20': name = 'Semester II'; break;
    case '40': name = 'Summer School'; break;
    default: name = `Term ${suffix}`; 
  }
  // This formatting is for display inside the course card, matching common university notation.
  // The academicYear string (YYYY/YY) for YearBlock headers is determined differently in populateDegreePlanFromTranscript.
  return `${year}/${nextYearShort} ${name}`;
};

/* Helper function to get color based on grade */
const getGradeColor = (grade: string): string => {
  if (!grade) return 'bg-gray-100 text-gray-800';
  if (grade.startsWith('A')) return 'bg-green-100 text-green-800';
  if (grade.startsWith('B')) return 'bg-blue-100 text-blue-800';
  if (grade.startsWith('C')) return 'bg-yellow-100 text-yellow-800';
  if (grade.startsWith('D')) return 'bg-orange-100 text-orange-800';
  if (grade.startsWith('F')) return 'bg-red-100 text-red-800';
  if (grade === 'NA') return 'bg-gray-100 text-gray-800'; 
  return 'bg-gray-100 text-gray-800';
};

/* —————————————————— Droppable Empty Course Slot Component —————————————————— */
const EmptyCourseSlot: React.FC<{
  semesterId: string;
  onDrop: (item: CourseItem & { rawPrerequisites?: CourseDetail['prerequisites'] }, semesterId: string) => void;
}> = ({ semesterId, onDrop }) => {
  const [{ isOver, canDrop }, drop] = useDrop(() => ({
    accept: ItemTypes.COURSE,
    drop: (item: CourseItem & { rawPrerequisites?: CourseDetail['prerequisites'] }) => onDrop(item, semesterId),
    collect: (monitor) => ({
      isOver: !!monitor.isOver(),
      canDrop: !!monitor.canDrop(),
    }),
  }));

  return (
    <div 
      ref={drop}
      className={`p-3 rounded-lg flex items-center justify-between border-2 ${isOver && canDrop ? 'border-green-400 bg-green-50' : 'border-dashed border-gray-300 bg-gray-50'} min-h-[60px] transition-colors`}
    >
      <span className="font-medium text-gray-400">
        {isOver && canDrop ? 'Drop to Add Course' : 'Drop Course Here'}
      </span>
      <Plus size={16} className={`${isOver && canDrop ? 'text-green-500' : 'text-gray-400'}`} />
    </div>
  );
}

/* —————————————————— Semester Block Component —————————————————— */
// From page.tsx
const SemesterBlock: React.FC<{
  id: string;
  number: number;
  status: 'completed' | 'in-progress' | 'planning';
  courses: CourseItem[];
  onAddCourse: (item: CourseItem & { rawPrerequisites?: CourseDetail['prerequisites'] }, semesterId: string) => void;
  onRemoveCourse: (courseId: string, semesterId: string) => void;
}> = ({ id, number, status, courses, onAddCourse, onRemoveCourse }) => {
  const statusStyles = {
    completed: 'text-green-600',
    'in-progress': 'text-blue-600',
    planning: 'text-orange-600'
  };

  const semesterName = () => {
    switch(number) {
      case 1: return "Semester I";
      case 2: return "Semester II";
      case 3: return "Summer School";
      default: return `Semester ${number}`;
    }
  };

  return (
    <div className="mb-4 bg-gray-50 rounded-xl p-4">
      <div className="flex justify-between mb-2">
        <h3 className="font-medium">{semesterName()}</h3>
        <span className={`text-sm ${statusStyles[status]}`}>
          {status.charAt(0).toUpperCase() + status.slice(1).replace('-', ' ')}
        </span>
      </div>
      <div className="space-y-2 overflow-y-auto max-h-56 pr-1">
        {courses.map((course) => (
          <PlannedCourseItem
            key={course.id}
            course={course}
            onRemove={status !== 'completed' ?
              (courseId) => onRemoveCourse(courseId, id) :
              undefined
            }
            isDraggable={status !== 'completed'}
          />
        ))}
        {status !== 'completed' && courses.length < 7 && (
          <EmptyCourseSlot
            semesterId={id}
            onDrop={(item, semesterId) => onAddCourse(item, semesterId)}
          />
        )}
      </div>
      <div className="mt-2 text-xs text-gray-500 flex justify-between items-center">
        <span>{courses.length} course{courses.length !== 1 ? 's' : ''}</span>
        {courses.length > 4 && <span className="text-blue-500">(Scroll for more)</span>}
      </div>
    </div>
  );
}

/* —————————————————— Year Block Component —————————————————— */
const YearBlock: React.FC<{
  year: number;
  academicYear?: string; 
  semesters: Array<{
    id: string;
    number: number;
    status: 'completed' | 'in-progress' | 'planning';
    courses: CourseItem[];
  }>;
  onAddCourse: (item: CourseItem & { rawPrerequisites?: CourseDetail['prerequisites'] }, semesterId: string) => void;
  onRemoveCourse: (courseId: string, semesterId: string) => void;
}> = ({ year, academicYear, semesters, onAddCourse, onRemoveCourse }) => {
  const totalCredits = semesters.reduce((sum, semester) => {
    return sum + semester.courses.reduce((semSum, course) => semSum + course.credits, 0);
  }, 0);
  const displayYear = academicYear || `Year ${year}`;

  return (
    <div className="bg-white border rounded-xl shadow-sm p-4 h-full flex flex-col">
      <div className="mb-3 pb-2 border-b flex justify-between items-center">
        <h2 className="text-lg font-semibold">{displayYear}</h2>
        <span className="text-sm text-gray-600">{totalCredits} credits</span>
      </div>
      <div className="flex-grow overflow-y-auto pr-1" style={{ maxHeight: '650px' }}>
        {semesters.map((semester) => (
          <SemesterBlock
            key={semester.id}
            id={semester.id}
            number={semester.number}
            status={semester.status}
            courses={semester.courses}
            onAddCourse={onAddCourse}
            onRemoveCourse={onRemoveCourse}
          />
        ))}
      </div>
    </div>
  );
}

/* —————————————————— Draggable Available Course Component —————————————————— */
interface AvailableCourseProps {
  id: string;
  code: string;
  title: string;
  credits: number;
  department?: string;
  prereq?: string | React.ReactNode; 
  rawPrerequisites?: CourseDetail['prerequisites']; 
  isCompleted?: boolean; 
  inProgress?: boolean;
  isPlanned?: boolean; 
  prerequisitesCurrentlyMet?: boolean; 
}

const AvailableCourse: React.FC<AvailableCourseProps> = ({ 
  id, code, title, credits, department, prereq, rawPrerequisites, 
  isCompleted, inProgress, isPlanned, prerequisitesCurrentlyMet
}) => {
  const courseItemForDrag: CourseItem & { rawPrerequisites?: CourseDetail['prerequisites'] } = {
    id, 
    code,
    title, 
    credits,
    department,
    status: 'planned', 
    rawPrerequisites 
  };

  const canBeDragged = !isCompleted && !inProgress && !isPlanned;

  const [{ isDragging }, drag] = useDrag(() => ({
    type: ItemTypes.COURSE,
    item: courseItemForDrag,
    collect: (monitor) => ({
      isDragging: !!monitor.isDragging()
    }),
    canDrag: canBeDragged
  }));

  let cardStyles = 'hover:shadow-md';
  if (isDragging) {
    cardStyles = 'opacity-50 border-green-400';
  } else if (isCompleted) {
    cardStyles = 'border-gray-300 bg-gray-50 opacity-75';
  } else if (inProgress) {
    cardStyles = 'border-blue-200 bg-blue-50';
  } else if (isPlanned) {
    cardStyles = 'border-purple-200 bg-purple-50';
  } else if (rawPrerequisites && rawPrerequisites.filter(p => p.course_code && p.course_code.trim() !== '').length > 0 && !prerequisitesCurrentlyMet) {
    cardStyles = 'border-red-300 bg-red-50';
  }


  return (
    <div 
      ref={drag}
      className={`p-4 border rounded-lg ${cardStyles} transition-shadow ${!canBeDragged ? 'cursor-not-allowed' : 'cursor-grab'}`}
    >
      <div className="flex justify-between mb-2">
        <h3 className="font-medium">{code}</h3>
        <span className="text-sm text-blue-600">{credits} Credits</span>
      </div>
      <p className="text-sm text-gray-600 mb-1">{title}</p>
      {department && (
        <p className="text-xs text-gray-500 mb-2">{department}</p>
      )}
      
      {isCompleted && (
        <div className="mt-2 bg-green-50 border border-green-200 rounded-md p-1.5 flex items-center">
          <CheckCircle2 className="w-4 h-4 mr-1 text-green-600" />
          <span className="text-xs text-green-700">Already completed</span>
        </div>
      )}
      
      {!isCompleted && inProgress && ( 
        <div className="mt-2 bg-blue-50 border border-blue-200 rounded-md p-1.5 flex items-center">
          <Clock className="w-4 h-4 mr-1 text-blue-600" />
          <span className="text-xs text-blue-700">Currently in progress</span>
        </div>
      )}

      {!isCompleted && !inProgress && isPlanned && ( 
         <div className="mt-2 bg-purple-50 border border-purple-200 rounded-md p-1.5 flex items-center">
          <ClipboardList className="w-4 h-4 mr-1 text-purple-600" />
          <span className="text-xs text-purple-700">Already in your plan</span>
        </div>
      )}
      
      {!isCompleted && !inProgress && !isPlanned && rawPrerequisites && rawPrerequisites.filter(p => p.course_code && p.course_code.trim() !== '').length > 0 && !prerequisitesCurrentlyMet && (
        <div className="mt-2 bg-red-50 border border-red-200 rounded-md p-1.5 flex items-center">
          <AlertCircle className="w-4 h-4 mr-1 text-red-600" />
          <span className="text-xs text-red-700">Prerequisites not met</span>
        </div>
      )}
      
      {prereq && ( 
        <div className="mt-2 border-t pt-2">
          <div className="text-xs font-medium text-gray-700 mb-1">Prerequisites:</div>
          <div className="text-xs text-gray-600">{prereq}</div>
        </div>
      )}
    </div>
  );
}

/* —————————————————— Action Button Component —————————————————— */
const ActionButton: React.FC<{
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}> = ({ icon, label, onClick, disabled = false }) => (
  <button
    className={`flex items-center w-full py-2 rounded-lg mb-2 transition-all text-sm ${
      disabled ? 'opacity-50 cursor-not-allowed' : 'hover:bg-opacity-80'
    }`}
    style={{ 
      backgroundColor: label.includes("Clone") ? "rgba(59, 130, 246, 0.1)" : 
                       label.includes("GPA") ? "rgba(139, 92, 246, 0.1)" : 
                       label.includes("Share") ? "rgba(16, 185, 129, 0.1)" : 
                       label.includes("Schedule") ? "rgba(107, 114, 128, 0.1)" : 
                       label.includes("Refresh") ? "rgba(251, 146, 60, 0.1)" : 
                       label.includes("PDF") ? "rgba(239, 68, 68, 0.1)" : 
                       "rgba(59, 130, 246, 0.1)",
      color: label.includes("Clone") ? "#2563eb" : 
             label.includes("GPA") ? "#7c3aed" : 
             label.includes("Share") ? "#059669" : 
             label.includes("Schedule") ? "#4b5563" : 
             label.includes("Refresh") ? "#ea580c" : 
             label.includes("PDF") ? "#dc2626" : 
             "#2563eb"
    }}
    onClick={onClick}
    disabled={disabled}
  >
    <span className="mx-auto flex items-center">
      {icon}
      <span className="ml-2">{label}</span>
    </span>
  </button>
);

/* —————————————————— Format Prerequisites for Display —————————————————— */
const formatPrerequisites = (prerequisites: CourseDetail['prerequisites'] | undefined): React.ReactNode | null => {
  if (!prerequisites || prerequisites.length === 0) return "None";
  
  const validPrereqs = prerequisites.filter(p => p.course_code && p.course_code.trim() !== '');
  if (validPrereqs.length === 0) return "None";

  let displayString = "";
  let currentGroup: string[] = [];
  // Initialize with a default that won't match the first operator if it's specific
  let lastLogicalOperator = ""; 

  validPrereqs.forEach((prereq, index) => {
    const currentCourseDisplay = prereq.course_code + (prereq.grade ? ` (${prereq.grade})` : "");
    // Determine the operator for the current item. If null (first item), treat as AND conceptually unless it's the start of an OR group.
    const currentOperator = prereq.and_or === "Or" ? "OR" : "AND";
    
    if (index === 0) { 
      currentGroup.push(currentCourseDisplay);
      lastLogicalOperator = currentOperator; // The first item sets the initial operator context for its group
    } else {
      if (currentOperator === lastLogicalOperator && currentGroup.length > 0) {
        // Continues the current group (e.g., A AND B, or A OR B)
        currentGroup.push(currentCourseDisplay);
      } else { 
        // Operator changed, or currentGroup was empty (shouldn't happen after first)
        // Finalize previous group
        if (currentGroup.length > 0) {
          displayString += (displayString.length > 0 ? ` ${lastLogicalOperator} ` : "") + 
                           (currentGroup.length > 1 ? `(${currentGroup.join(` ${lastLogicalOperator} `)})` : currentGroup[0]);
        }
        // Start new group with the current item and its operator
        currentGroup = [currentCourseDisplay];
        lastLogicalOperator = currentOperator;
      }
    }
  });

  // Append the last/current group
  if (currentGroup.length > 0) {
    displayString += (displayString.length > 0 ? ` ${lastLogicalOperator} ` : "") + 
                     (currentGroup.length > 1 ? `(${currentGroup.join(` ${lastLogicalOperator} `)})` : currentGroup[0]);
  }
  
  return displayString || "None";
};


/* —————————————————— Main Degree Planner Component —————————————————— */

const isPrereqPotentiallyCoveredInPlan = (
    courseCode: string,
    currentPlan: YearPlanData[]
): boolean => {
    const normalizedCode = normalizeCourseCode(courseCode);
    for (const year of currentPlan) {
        for (const semester of year.semesters) {
            for (const courseInPlan of semester.courses) {
                if (normalizeCourseCode(courseInPlan.code) === normalizedCode &&
                    (courseInPlan.status === 'completed' || 
                     courseInPlan.status === 'in-progress' ||
                     courseInPlan.status === 'planned')) { 
                    return true;
                }
            }
        }
    }
    return false;
};

const parsePrerequisitesToArrayOfOrGroups = (
    prerequisites: CourseDetail['prerequisites'] | undefined
): string[][] => {
    if (!prerequisites || prerequisites.length === 0) return [];
    const validPrereqs = prerequisites.filter(p => p.course_code && p.course_code.trim() !== '');
    if (validPrereqs.length === 0) return [];

    const overallRequirement: string[][] = [];
    let currentOrGroup: string[] = [];

    for (let i = 0; i < validPrereqs.length; i++) {
        const prereq = validPrereqs[i];
        const normalizedCode = normalizeCourseCode(prereq.course_code);
        if (prereq.and_or === null || prereq.and_or === "And") {
            if (currentOrGroup.length > 0) {
                overallRequirement.push([...currentOrGroup]);
            }
            currentOrGroup = [normalizedCode];
        } else if (prereq.and_or === "Or") {
            if (currentOrGroup.length === 0) { 
                const lastAndGroup = overallRequirement.pop(); 
                if (lastAndGroup) {
                    currentOrGroup = [...lastAndGroup, normalizedCode];
                } else { 
                    currentOrGroup = [normalizedCode];
                }
            } else { 
               currentOrGroup.push(normalizedCode);
            }
        }
    }
    if (currentOrGroup.length > 0) {
        overallRequirement.push([...currentOrGroup]);
    }
    return overallRequirement;
};

const checkPrerequisitesGeneral = (
    prerequisites: CourseDetail['prerequisites'] | undefined,
    currentPlan: YearPlanData[]
): boolean => {
    if (!prerequisites || prerequisites.length === 0) {
        return true; 
    }
    const validRawPrereqs = prerequisites.filter(p => p.course_code && p.course_code.trim() !== '');
    if (validRawPrereqs.length === 0) return true; 

    const parsedPrereqs = parsePrerequisitesToArrayOfOrGroups(prerequisites); 
    if (parsedPrereqs.length === 0 && validRawPrereqs.length > 0) { 
      return false; 
    }
    if (parsedPrereqs.length === 0) return true;

    for (const orGroup of parsedPrereqs) {
        if (orGroup.length === 0) continue; 
        let orGroupSatisfied = false;
        for (const prereqCourseCodeInOrGroup of orGroup) {
            if (isPrereqPotentiallyCoveredInPlan(prereqCourseCodeInOrGroup, currentPlan)) { 
                orGroupSatisfied = true;
                break;
            }
        }
        if (!orGroupSatisfied) {
            return false; 
        }
    }
    return true; 
};


const DegreePlannerContent: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [searchResults, setSearchResults] = useState<CourseDetail[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const resultsPerPage = 6;
  const [currentYearPage, setCurrentYearPage] = useState(0);
  const yearsPerPage = 4;
  const [creditCheckData, setCreditCheckData] = useState<CreditCheckResponse | null>(null);
  const [isLoadingCreditCheck, setIsLoadingCreditCheck] = useState(false);
  const [creditCheckError, setCreditCheckError] = useState<string | null>(null);
  const [yearData, setYearData] = useState<YearPlanData[]>([]);

  useEffect(() => {
    fetchCreditCheckData();
  }, []);

  const fetchCreditCheckData = async () => {
    setIsLoadingCreditCheck(true);
    setCreditCheckError(null);
    try {
      const data = await academicClient.getCreditCheck();
      setCreditCheckData(data);
      populateDegreePlanFromTranscript(data); 
    } catch (error: any) {
      console.error('Credit check error:', error);
      setCreditCheckError(error.message || 'Failed to load credit check data');
    } finally {
      setIsLoadingCreditCheck(false);
    }
  };

  // Restored populateDegreePlanFromTranscript from user's original file (content from uploaded:page.tsx)
  const populateDegreePlanFromTranscript = (data: CreditCheckResponse) => {
    const transcript = data.analysis.transcript.data;
    
    const termMapping: Record<string, { year: number, academicYear: string, semester: number, status: 'completed' | 'in-progress' | 'planning' }> = {};
    
    const sortedTerms = [...transcript.terms].sort((a, b) => {
      if (a.term_code === 'CURRENT') return 1;
      if (b.term_code === 'CURRENT') return -1;
      return a.term_code.localeCompare(b.term_code);
    });
    
    const academicYears: Record<string, {yearNum: number, yearLabel: string}> = {};
    let currentAcademicYear = 1; // This is the sequential year number (Year 1, Year 2, etc.)
    
    sortedTerms.forEach(term => {
      if (term.term_code === 'CURRENT') return; 
      
      const year = term.term_code.substring(0, 4);
      const period = term.term_code.substring(4);
      
      // User's original logic for determining the academic year key:
      // Sem I, II, and Summer of a calendar year 'YYYY' all belong to an academic year starting in 'YYYY'.
      const academicYearKey = period === '10' ? year : 
                              (period === '20' ? year : 
                              (period === '40' ? year : year)); // This line was from the original user file
      
      if (!academicYears[academicYearKey]) {
        const nextYearShort = String(parseInt(academicYearKey) + 1).substring(2, 4);
        academicYears[academicYearKey] = {
          yearNum: currentAcademicYear++, 
          yearLabel: `${academicYearKey}/${nextYearShort}`
        };
      }
    });
    
    sortedTerms.forEach(term => {
      let academicYearKeyForTerm: string;
      let semesterNum: number;
      let termStatus: 'completed' | 'in-progress' | 'planning' = 'completed';

      if (term.term_code === 'CURRENT') {
        const currentDate = new Date();
        const currentMonth = currentDate.getMonth() + 1; 
        const termYearStr = currentDate.getFullYear().toString();
        
        // This logic for CURRENT term needs to align with how academicYearKey was determined above
        // If Sem II / Summer of YYYY belong to AY YYYY/YYYY+1 (as per key logic above)
        if (currentMonth >= 9 && currentMonth <= 12) { // Sep-Dec is Sem 1 of AY YYYY/YYYY+1
            semesterNum = 1;
            academicYearKeyForTerm = termYearStr; 
        } else if (currentMonth >= 1 && currentMonth <= 4) { // Jan-Apr is Sem 2 of AY YYYY/YYYY+1
            semesterNum = 2;
            academicYearKeyForTerm = termYearStr; // Belongs to the same calendar year as academic year key
        } else { // May-Aug is Summer of AY YYYY/YYYY+1
            semesterNum = 3;
            academicYearKeyForTerm = termYearStr; // Belongs to the same calendar year as academic year key
        }
        termStatus = 'in-progress';
        
        if (!academicYears[academicYearKeyForTerm]) {
            const nextYearShort = String(parseInt(academicYearKeyForTerm) + 1).substring(2,4);
            academicYears[academicYearKeyForTerm] = {
                yearNum: currentAcademicYear++, 
                yearLabel: `${academicYearKeyForTerm}/${nextYearShort}`
            };
        }
      } else { 
        const year = term.term_code.substring(0, 4);
        const period = term.term_code.substring(4);
        
        academicYearKeyForTerm = period === '10' ? year : 
                                 (period === '20' ? year : 
                                 (period === '40' ? year : year));

        switch(period) {
          case '10': semesterNum = 1; break;
          case '20': semesterNum = 2; break;
          case '40': semesterNum = 3; break;
          default: semesterNum = 1; 
        }
        if (term.courses.some(course => course.grade_earned === 'NA')) {
          termStatus = 'in-progress';
        }
      }
      
      const yearInfo = academicYears[academicYearKeyForTerm];
      if (yearInfo) { 
          termMapping[term.term_code] = { 
            year: yearInfo.yearNum, 
            academicYear: yearInfo.yearLabel, 
            semester: semesterNum, 
            status: termStatus 
          };
      } else {
        // Fallback if a term's academic year key wasn't pre-calculated (e.g., only CURRENT term exists)
        const newYearNum = Math.max(1, ...Object.values(academicYears).map(ay => ay.yearNum), 0) + 1;
        const newAyLabel = `${academicYearKeyForTerm}/${String(parseInt(academicYearKeyForTerm)+1).substring(2,4)}`;
        academicYears[academicYearKeyForTerm] = { yearNum: newYearNum, yearLabel: newAyLabel};
        termMapping[term.term_code] = {
            year: newYearNum,
            academicYear: newAyLabel,
            semester: semesterNum,
            status: termStatus
        };
      }
    });
    
    const initialYearData: YearPlanData[] = [];
    // Max sequential year found in the transcript
    const maxTranscriptYearNum = Math.max(0, ...Object.values(termMapping).map(item => item.year));
    // Ensure we display at least 4 years or more if transcript data goes further
    const totalYearsToDisplay = Math.max(maxTranscriptYearNum, 4); 

    // Get sorted academic year info (sequential number and label)
    const sortedKnownAcademicYears = Object.values(academicYears).sort((a,b) => a.yearNum - b.yearNum);

    for (let i = 1; i <= totalYearsToDisplay; i++) {
      const sequentialYearNum = i;
      let academicYearDisplayLabel = `Year ${sequentialYearNum}`; // Fallback

      const foundAcademicYear = sortedKnownAcademicYears.find(ay => ay.yearNum === sequentialYearNum);
      if (foundAcademicYear) {
        academicYearDisplayLabel = foundAcademicYear.yearLabel;
      } else if (i > maxTranscriptYearNum && sortedKnownAcademicYears.length > 0) {
          // Extrapolate for future planning years
          const lastKnownAy = sortedKnownAcademicYears[sortedKnownAcademicYears.length - 1];
          const lastKnownStartYear = parseInt(lastKnownAy.yearLabel.split('/')[0]);
          const diff = sequentialYearNum - lastKnownAy.yearNum;
          const currentStartYear = lastKnownStartYear + diff;
          academicYearDisplayLabel = `${currentStartYear}/${String(currentStartYear + 1).substring(2,4)}`;
      }
      
      initialYearData.push({
        year: sequentialYearNum, 
        academicYear: academicYearDisplayLabel,
        semesters: [
          { id: `y${sequentialYearNum}s1`, number: 1, status: 'planning', courses: [] },
          { id: `y${sequentialYearNum}s2`, number: 2, status: 'planning', courses: [] },
          { id: `y${sequentialYearNum}s3`, number: 3, status: 'planning', courses: [] }
        ]
      });
    }
    
    sortedTerms.forEach(term => {
      if (!termMapping[term.term_code]) return;
      
      const { year: sequentialYearNum, semester: semesterNum, status: termOverallStatus } = termMapping[term.term_code];
      
      const yearIndex = initialYearData.findIndex(y => y.year === sequentialYearNum);
      if (yearIndex === -1) return;
      
      const semesterIndex = semesterNum - 1;
      if (semesterIndex < 0 || semesterIndex > 2) return;

      initialYearData[yearIndex].semesters[semesterIndex].status = termOverallStatus;
      
      term.courses.forEach(course => {
        const courseId = `${normalizeCourseCode(course.course_code)}-${term.term_code}-${Math.random().toString(36).substr(2, 5)}`;
        let courseStatusInPlan: 'completed' | 'in-progress' | 'planned' = 'completed';
        if (course.grade_earned === 'NA') {
          courseStatusInPlan = 'in-progress';
        }
        
        initialYearData[yearIndex].semesters[semesterIndex].courses.push({
          id: courseId,
          code: course.course_code,
          title: course.course_title,
          credits: course.credit_hours,
          grade: course.grade_earned,
          status: courseStatusInPlan,
          term_code: term.term_code 
        });
      });
    });
    
    setYearData(initialYearData);
  };


  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(searchQuery), 500);
    return () => clearTimeout(timer);
  }, [searchQuery]);
  
  useEffect(() => {
    if (debouncedQuery) {
      handleSearch();
      setCurrentPage(1);
    } else {
        setSearchResults([]); 
    }
  }, [debouncedQuery]);
  
  const getUserData = () => {
    if (!creditCheckData) {
      return {
        program: "Loading...",
        credits: { total: { earned: 0, required: 0 }, core: { earned: 0, required: 0 }, elective: { earned: 0, required: 0 }},
        gpa: 0
      };
    }
    const { faculty_result, major_result, faculty_schema } = creditCheckData.analysis;
    const transcript = creditCheckData.analysis.transcript.data;
    const latestTermWithGPA = transcript.terms
      .filter(term => term.term_code !== 'CURRENT' && typeof term.degree_gpa === 'number')
      .sort((a, b) => b.term_code.localeCompare(a.term_code))[0];
    
    return {
      program: `${major_result?.major || 'N/A'} (${creditCheckData.analysis.student_major_code || 'N/A'})`,
      credits: {
        total: { earned: faculty_result?.credits_earned?.total || 0, required: faculty_schema?.credit_requirements?.total_credits || 0 },
        core: { earned: faculty_result?.credits_earned?.level_1 || 0, required: faculty_schema?.credit_requirements?.level_1?.min_credits || 0 },
        elective: { earned: faculty_result?.credits_earned?.level_2_and_3 || 0, required: faculty_schema?.credit_requirements?.level_2_and_3?.min_credits || 0 }
      },
      gpa: latestTermWithGPA?.degree_gpa ?? transcript.overall?.degree_gpa ?? 0
    };
  };

  const handleSearch = useCallback(async () => {
    if (!debouncedQuery.trim()) {
      setSearchResults([]);
      return;
    }
    setIsSearching(true);
    setSearchError(null);
    try {
      const params = { q: debouncedQuery.trim() };
      const results = await academicClient.searchCourses(params);
      setSearchResults(results);
    } catch (error: any) {
      console.error('Search error:', error);
      setSearchError(error.message || 'Failed to search courses');
    } finally {
      setIsSearching(false);
    }
  }, [debouncedQuery]);


  const isCourseSatisfiedInPlanForAdd = (
      prereqCourseCode: string,
      targetYearIndex: number, 
      targetSemesterIndex: number, 
      currentPlan: YearPlanData[]
  ): boolean => {
      const normalizedPrereqCode = normalizeCourseCode(prereqCourseCode);

      for (let yIdx = 0; yIdx < currentPlan.length; yIdx++) { 
          const yearInPlan = currentPlan[yIdx]; // currentPlan is 0-indexed by sequential year
          // targetYearIndex is also 0-indexed sequential year
          for (let sIdx = 0; sIdx < yearInPlan.semesters.length; sIdx++) { 
              const semesterInPlan = yearInPlan.semesters[sIdx];
              
              const isStrictlyBefore = yIdx < targetYearIndex || (yIdx === targetYearIndex && sIdx < targetSemesterIndex);
              const isCurrentTargetSemester = yIdx === targetYearIndex && sIdx === targetSemesterIndex;

              for (const courseInPlan of semesterInPlan.courses) {
                  if (normalizeCourseCode(courseInPlan.code) === normalizedPrereqCode) {
                      if (isStrictlyBefore) { 
                          return true;
                      } else if (isCurrentTargetSemester) { 
                          if (courseInPlan.status === 'completed' || courseInPlan.status === 'in-progress') {
                              return true;
                          }
                      }
                  }
              }
          }
      }
      return false;
  };

  const handleAddCourse = (
    item: CourseItem & { rawPrerequisites?: CourseDetail['prerequisites'] }, 
    semesterId: string 
  ) => {
    const courseCodeToAdd = normalizeCourseCode(item.code); 

    let courseExists = false;
    yearData.forEach(year => {
      year.semesters.forEach(semester => {
        if (semester.courses.some(c => normalizeCourseCode(c.code) === courseCodeToAdd)) {
          courseExists = true;
        }
      });
    });

    if (courseExists) {
      alert(`Course ${item.code} is already in your degree plan.`);
      return;
    }

    const prerequisitesFromItem = item.rawPrerequisites;
    if (prerequisitesFromItem && prerequisitesFromItem.length > 0) {
        const parsedPrereqs = parsePrerequisitesToArrayOfOrGroups(prerequisitesFromItem);
        
        let targetSequentialYearIndex = -1; 
        let targetSemesterIndex = -1; 

        const targetYearObj = yearData.find(y => y.semesters.some(s => s.id === semesterId));
        if (targetYearObj) {
            targetSequentialYearIndex = yearData.indexOf(targetYearObj); // This gives the 0-indexed position in the yearData array
            const targetSemObj = targetYearObj.semesters.find(s => s.id === semesterId);
            if (targetSemObj) {
                targetSemesterIndex = targetYearObj.semesters.indexOf(targetSemObj);
            }
        }

        if (targetSequentialYearIndex === -1 || targetSemesterIndex === -1) {
            console.error("Target semester/year not found for prerequisite check. Semester ID:", semesterId);
            alert("Error: Target semester not found. Cannot add course.");
            return;
        }

        for (const orGroup of parsedPrereqs) {
            if (orGroup.length === 0) continue;
            let orGroupSatisfied = false;
            for (const prereqCourseCodeInOrGroup of orGroup) { 
                if (isCourseSatisfiedInPlanForAdd(prereqCourseCodeInOrGroup, targetSequentialYearIndex, targetSemesterIndex, yearData)) {
                    orGroupSatisfied = true;
                    break; 
                }
            }
            if (!orGroupSatisfied) {
                const missingCoursesMessage = orGroup.join(' OR ');
                alert(`Cannot add ${item.code}. Prerequisite not met: You need to complete or plan one of (${missingCoursesMessage}) in an earlier semester/year, or have it completed/in-progress in the current semester if it's a co-requisite.`);
                return;
            }
        }
    }

    const courseToAdd: CourseItem = {
      id: `${item.code}-${semesterId}-${Date.now()}`, 
      code: item.code, 
      title: item.title,
      credits: item.credits,
      department: item.department,
      status: 'planned',
    };

    setYearData(prevYearData => 
      prevYearData.map(year => ({
        ...year,
        semesters: year.semesters.map(semester => {
          if (semester.id === semesterId) {
            if (semester.courses.length >= 7) { 
                alert(`Semester full. Cannot add more than 7 courses to ${semester.id}.`);
                return semester; 
            }
            return {
              ...semester,
              courses: [...semester.courses, courseToAdd]
            };
          }
          return semester;
        })
      }))
    );
  };

  const handleRemoveCourse = (courseId: string, semesterId: string) => {
    setYearData(prevYearData => 
      prevYearData.map(year => ({
        ...year,
        semesters: year.semesters.map(semester => {
          if (semester.id === semesterId) {
            return {
              ...semester,
              courses: semester.courses.filter(course => course.id !== courseId)
            };
          }
          return semester;
        })
      }))
    );
  };

  const getCourseStatusInPlan = (courseCode: string): { completed: boolean; inProgress: boolean; planned: boolean } => {
    let completed = false;
    let inProgress = false;
    let planned = false; 
    const normalizedSearchCode = normalizeCourseCode(courseCode);
    
    yearData.forEach(year => {
      year.semesters.forEach(semester => {
        semester.courses.forEach(courseInPlan => { 
          if (normalizeCourseCode(courseInPlan.code) === normalizedSearchCode) {
            if (courseInPlan.status === 'completed') completed = true;
            else if (courseInPlan.status === 'in-progress') inProgress = true;
            else if (courseInPlan.status === 'planned') planned = true;
          }
        });
      });
    });
    return { completed, inProgress, planned };
  };

  const availableCourses = searchResults.length > 0
    ? searchResults.map(course => {
        const status = getCourseStatusInPlan(course.course_code); 
        const meetsPrereqsCurrently = checkPrerequisitesGeneral(course.prerequisites, yearData); 
        return {
          id: `search-${course.course_code}-${course.ban_id || Math.random().toString(36).substring(2,9)}`, 
          code: course.course_code,
          title: course.course_title,
          credits: course.credit_hour_high || course.credit_hour_low || 0,
          department: course.department,
          prereq: formatPrerequisites(course.prerequisites), 
          rawPrerequisites: course.prerequisites, 
          isCompleted: status.completed,
          inProgress: status.inProgress,
          isPlanned: status.planned,
          prerequisitesCurrentlyMet: meetsPrereqsCurrently, 
        };
      })
    : []; 
    
  const totalPages = Math.ceil(availableCourses.length / resultsPerPage);
  const currentCourses = availableCourses.slice(
    (currentPage - 1) * resultsPerPage,
    currentPage * resultsPerPage
  );
  
  const handleNextPage = () => currentPage < totalPages && setCurrentPage(currentPage + 1);
  const handlePrevPage = () => currentPage > 1 && setCurrentPage(currentPage - 1);

  const userData = getUserData();
  const shouldPaginateYears = yearData.length > yearsPerPage;
  const maxYearPage = Math.ceil(yearData.length / yearsPerPage) - 1;
  
  useEffect(() => {
    if (currentYearPage > maxYearPage && maxYearPage >= 0) {
      setCurrentYearPage(maxYearPage);
    }
  }, [currentYearPage, maxYearPage]);
  
  const visibleYears = shouldPaginateYears
    ? yearData.slice(currentYearPage * yearsPerPage, (currentYearPage * yearsPerPage) + yearsPerPage)
    : yearData;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      {/* Top Bar */}
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-blue-700">Degree Planner</h1>
        <div className="flex items-center space-x-2">
          {isLoadingCreditCheck ? (
            <span className="text-sm text-gray-500 flex items-center"><RefreshCw className="w-4 h-4 mr-1 animate-spin" />Loading data...</span>
          ) : creditCheckError ? (
            <span className="text-sm text-red-500 flex items-center"><AlertCircle className="w-4 h-4 mr-1" />Error loading data</span>
          ) : (
            <span className="text-sm text-green-500 flex items-center"><CheckCircle2 className="w-4 h-4 mr-1" />Data loaded</span>
          )}
          <Button 
            onClick={fetchCreditCheckData} 
            variant="outline"
            size="sm"
            disabled={isLoadingCreditCheck}
          >
            <RefreshCw className="w-4 h-4 mr-1" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Progress Bars */}
      <div className="bg-white rounded-xl shadow p-6 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <ProgressBar label="Total Credits" value={userData.credits.total.earned} max={userData.credits.total.required} color="bg-yellow-500" />
          <ProgressBar label="Core Credits" value={userData.credits.core.earned} max={userData.credits.core.required} color="bg-blue-500" />
          <ProgressBar label="Elective Credits" value={userData.credits.elective.earned} max={userData.credits.elective.required} color="bg-green-500" />
          <ProgressBar label="GPA" value={userData.gpa} max={4.0} color="bg-purple-500" />
        </div>
      </div>

      {/* Main Content - Years and Semesters with Pagination */}
      <div className="mb-6">
        <div className="flex justify-between items-center mb-3">
          <h2 className="text-xl font-semibold text-gray-700">Academic Plan</h2>
          {shouldPaginateYears && (
            <div className="flex items-center space-x-2">
              <Button variant="ghost" size="sm" onClick={() => currentYearPage > 0 && setCurrentYearPage(currentYearPage - 1)} disabled={currentYearPage === 0}>
                <ChevronLeft className="h-4 w-4 mr-1" /> Prev
              </Button>
              <span className="text-sm text-gray-600">Year Block {currentYearPage + 1} of {Math.ceil(yearData.length / yearsPerPage)}</span>
              <Button variant="ghost" size="sm" onClick={() => currentYearPage < maxYearPage && setCurrentYearPage(currentYearPage + 1)} disabled={currentYearPage >= maxYearPage}>
                Next <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          )}
        </div>
        
        <div className="overflow-x-auto pb-4">
          <div className="flex space-x-5" style={{ minWidth: 'max-content' }}>
            {visibleYears.length > 0 ? visibleYears.map((yearDataEntry) => ( // Renamed to avoid conflict with yearData state
              <div key={yearDataEntry.academicYear} className="w-[380px] flex-shrink-0"> 
                <YearBlock
                  year={yearDataEntry.year} 
                  academicYear={yearDataEntry.academicYear} 
                  semesters={yearDataEntry.semesters}
                  onAddCourse={handleAddCourse}
                  onRemoveCourse={handleRemoveCourse}
                />
              </div>
            )) : <p className="text-gray-500">No academic years to display. Try refreshing data.</p>}
          </div>
        </div>
      </div>

      {/* Course Pool and Tools Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Available Courses - Takes 2 columns on larger screens */}
        <div className="lg:col-span-2 bg-white border rounded-lg p-4 flex flex-col shadow">
          <div className="flex flex-col sm:flex-row justify-between items-center mb-4 gap-2">
            <h2 className="text-xl font-semibold text-gray-700">Available Courses</h2>
            <div className="relative w-full sm:w-72">
              <input
                type="text"
                placeholder="Search courses (e.g., COMP1126)"
                className="w-full p-2 pl-10 pr-4 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <Search className="w-5 h-5 text-gray-400 absolute left-3 top-1/2 transform -translate-y-1/2" />
              {searchQuery && (
                <button 
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600"
                  onClick={() => setSearchQuery('')}
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
          
          <div className="mb-2 min-h-6 text-sm">
            {isSearching && <p className="text-gray-600 flex items-center"><RefreshCw className="w-4 h-4 mr-2 animate-spin text-blue-500"/>Searching...</p>}
            {searchError && <p className="text-red-600 bg-red-50 p-2 rounded">{searchError}</p>}
            {!isSearching && debouncedQuery && searchResults.length > 0 && (
              <p className="text-gray-600">Found {searchResults.length} course(s). Drag to add to your plan.</p>
            )}
            {!isSearching && debouncedQuery && searchResults.length === 0 && !searchError && (
              <p className="text-gray-600">No courses found for "{debouncedQuery}". Try different keywords.</p>
            )}
          </div>

          <div className="overflow-y-auto flex-grow" style={{ height: '450px' }}> 
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-1">
              {currentCourses.map((course) => (
                <AvailableCourse
                  key={course.id} 
                  {...course} 
                />
              ))}
              {availableCourses.length === 0 && !isSearching && !debouncedQuery && (
                <div className="col-span-full flex flex-col items-center justify-center py-10 text-gray-500 h-full">
                  <Search className="h-12 w-12 mb-3 text-gray-300" />
                  <p>Search for courses by code or title.</p>
                </div>
              )}
            </div>
          </div>
          
          {availableCourses.length > resultsPerPage && (
            <div className="mt-4 pt-3 border-t flex justify-between items-center">
              <span className="text-sm text-gray-500">
                Page {currentPage} of {totalPages}
              </span>
              <div className="flex space-x-2">
                <Button variant="outline" size="sm" onClick={handlePrevPage} disabled={currentPage <= 1}>Previous</Button>
                <Button variant="outline" size="sm" onClick={handleNextPage} disabled={currentPage >= totalPages}>Next</Button>
              </div>
            </div>
          )}
        </div>

        {/* Right sidebar for tools */}
        <div className="space-y-4">
          <GraduationStatus creditCheck={creditCheckData} />
          <div className="bg-white border rounded-lg p-4 shadow">
            <h2 className="text-lg font-semibold mb-3 text-gray-700">Program Information</h2>
            <div className="text-sm space-y-2">
              <div className="flex justify-between"><span className="text-gray-600">Program:</span> <span className="font-medium text-right">{userData.program}</span></div>
              <div className="flex justify-between"><span className="text-gray-600">Total Credits:</span> <span className="font-medium">{userData.credits.total.earned} / {userData.credits.total.required || '?'}</span></div>
              <div className="flex justify-between"><span className="text-gray-600">GPA:</span> <span className={`font-medium ${userData.gpa >= 3.0 ? 'text-green-600' : userData.gpa >= 2.0 ? 'text-orange-600' : 'text-red-600'}`}>{userData.gpa.toFixed(2)}</span></div>
            </div>
          </div>
          <div className="bg-white border rounded-lg p-4 shadow">
            <h2 className="text-lg font-semibold mb-3 text-gray-700">Tools & Actions</h2>
            <ActionButton icon={<Copy className="h-4 w-4" />} label="Clone Current Plan" onClick={() => alert("Clone plan: Not implemented")} />
            <ActionButton icon={<FileCheck className="h-4 w-4" />} label="GPA Simulator" onClick={() => alert("GPA Simulator: Not implemented")} />
            <ActionButton icon={<Share2 className="h-4 w-4" />} label="Share with Advisor" onClick={() => alert("Share: Not implemented")} />
            <ActionButton icon={<FileText className="h-4 w-4" />} label="Download PDF" onClick={() => alert("Download PDF: Not implemented")} />
          </div>
        </div>
      </div>
    </div>
  )
}

export default function DegreePlannerPage() {
  return (
    <Provider store={store}>
      <DndProvider backend={HTML5Backend}>
        <Layout> 
          <DegreePlannerContent />
        </Layout>
      </DndProvider>
    </Provider>
  )
}

