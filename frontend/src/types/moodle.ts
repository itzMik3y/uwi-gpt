// src/types/moodle.ts

export interface MoodleUser {
  name: string;
  email: string;
  student_id: string;
  majors?: string | null;
  minors?: string | null;
  faculty?: string | null;
  
}

export interface MoodleCourse {
  id: number;
  fullname: string;
  shortname: string;
  idnumber: string;
  summary: string;
  summaryformat: number;
  startdate: number;
  enddate: number;
  visible: boolean;
  showactivitydates: boolean;
  showcompletionconditions: boolean | null;
  fullnamedisplay: string;
  viewurl: string;
  coursecategory: string;
}

export interface MoodleCalendarEvent {
  id: number;
  name: string;
  description: string;
  descriptionformat: number;
  location: string;
  categoryid: number | null;
  groupid: number | null;
  userid: number;
  repeatid: number | null;
  eventcount: number | null;
  component: string;
  modulename: string;
  activityname: string;
  activitystr: string;
  instance: number;
  eventtype: string;
  timestart: number;
  timeduration: number;
  timesort: number;
  timeusermidnight: number;
  visible: number;
  timemodified: number;
  overdue: boolean;
  icon: {
      key: string;
      component: string;
      alttext: string;
      iconurl: string;
      iconclass: string;
  };
  course: MoodleCourse;
  subscription: {
      displayeventsource: boolean;
  };
  canedit: boolean;
  candelete: boolean;
  deleteurl: string;
  editurl: string;
  viewurl: string;
  formattedtime: string;
  formattedlocation: string;
  isactionevent: boolean;
  iscourseevent: boolean;
  iscategoryevent: boolean;
  groupname: string | null;
  normalisedeventtype: string;
  normalisedeventtypetext: string;
  action: {
      name: string;
      url: string;
      itemcount: number;
      actionable: boolean;
      showitemcount: boolean;
  };
  purpose: string;
  url: string;
}

export interface MoodleAuthTokens {
  login_token: string;
  sesskey: string;
  moodle_session: string;
}

export interface MoodleData {
  user_info: MoodleUser;
  courses: {
      courses: MoodleCourse[];
      nextoffset: number | null;
  };
  calendar_events: {
      events: MoodleCalendarEvent[];
      firstid: number | null;
      lastid: number | null;
  };
  auth_tokens: MoodleAuthTokens;
}

// --- Interfaces for Grades Data ---
export interface GradeCourse {
  course_code: string;
  course_title: string;
  credit_hours: number;
  grade_earned: string;
  whatif_grade: string;
}

export interface GradeTerm {
  term_code: string;
  courses: GradeCourse[];
  semester_gpa: number | null;
  cumulative_gpa: number | null;
  degree_gpa: number | null;
  credits_earned_to_date: number | null;
}

export interface GradeOverall {
  cumulative_gpa: number | null;
  degree_gpa: number | null;
  total_credits_earned: number | null;
}

export interface GradesDataPayload {
  student_name: string;
  student_id: string;
  terms: GradeTerm[];
  overall: GradeOverall;
}

export interface GradesStatus {
  fetched: boolean;
  success: boolean;
  error: string | null;
}

// --- Login Request/Response ---

export interface MoodleLoginRequest {
  username: string;
  password: string;
}

// Auth response from /auth/token endpoint
export interface AuthResponse {
  access_token: string;
  token_type: string;
  refresh_token: string;
  expires_at: number; // Unix timestamp in seconds
}

// Response from /auth/me endpoint
export interface CombinedLoginResponse {
  moodle_data: MoodleData;
  grades_status: GradesStatus;
  grades_data: GradesDataPayload;
}

export interface MoodleErrorResponse {
  error: string;
  errorcode?: string;
  stacktrace?: string;
  debuginfo?: string;
  reproductionlink?: string;
}