// src/types/moodle.ts

export interface MoodleUser {
    name: string;
    email: string;
    student_id: string;
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
    showcompletionconditions: boolean | null; // Verified against JSON sample (can be boolean or null)
    fullnamedisplay: string;
    viewurl: string;
    progress: number;
    hasprogress: boolean;
    isfavourite: boolean;
    hidden: boolean;
    showshortname: boolean;
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
    visible: number; // Verified against JSON sample (is a number, e.g., 1)
    timemodified: number;
    overdue: boolean;
    icon: {
      key: string;
      component: string;
      alttext: string;
      iconurl: string;
      iconclass: string;
    };
    course: MoodleCourse; // Assumes the nested course object matches MoodleCourse structure
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
  
  // Added interface for the auth_tokens object found in the JSON
  export interface MoodleAuthTokens {
    login_token: string;
    sesskey: string;
    moodle_session: string;
  }
  
  export interface MoodleData {
    user_info: MoodleUser;
    courses: {
      courses: MoodleCourse[];
      nextoffset: number;
    };
    calendar_events: {
      events: MoodleCalendarEvent[];
      firstid: number;
      lastid: number;
    };
    auth_tokens: MoodleAuthTokens; // Added property to match the JSON structure
  }
  
  // --- Below interfaces seem unrelated to the provided data sample but kept as is ---
  
  export interface MoodleLoginRequest {
    username: string;
    password: string;
  }
  
  export interface MoodleLoginResponse {
    token: string;
    privatetoken?: string;
  }
  
  export interface MoodleErrorResponse {
    error: string;
    errorcode?: string;
    stacktrace?: string;
    debuginfo?: string;
    reproductionlink?: string;
  }