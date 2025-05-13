// src/types/admin.ts
import { MoodleLoginRequest } from './moodle';

export interface AdminUser {
  id: number;
  login_id: number;
  firstname: string;
  lastname: string;
  email: string;
  is_superadmin: boolean;
}

export interface AdminLoginRequest extends MoodleLoginRequest {
  // Same as MoodleLoginRequest (username, password)
}

export interface AdminDataResponse {
  admin: AdminUser;  // <-- expecting "admin", not "admin_info"
  slots: AdminSlotWithBooking[];
}
export interface AdminAuthResponse {
  access_token: string;
  token_type: string;
  refresh_token: string;
  expires_at: number; // Unix timestamp in seconds
}

export interface AdminSlot {
  id: number;
  admin_id: number;
  start_time: string; // ISO date string
  end_time: string; // ISO date string
  is_booked: boolean;
}

export interface AdminBooking {
  id: number;
  slot_id: number;
  student_id: number;
  created_at: string; // ISO date string
  student?: {
    id: number;
    firstname: string;
    lastname: string;
    email: string;
    student_id: string;
  };
}

export interface AdminSlotWithBooking extends AdminSlot {
  booking: AdminBooking | null;
}

export interface AdminDataResponse {
  admin: AdminUser;
  slots: AdminSlotWithBooking[];
}

export interface CreateSlotsRequest {
  slots: {
    start_time: string; // ISO date string
    end_time: string; // ISO date string
  }[];
}