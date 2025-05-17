// app/admin/dashboard/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Layout } from "@/app/components/layout/Layout";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { fetchAdminData, createSlots } from "@/store/slices/adminAuthSlice";
import { ChevronLeft, ChevronRight, Users, Info } from "lucide-react";
import Link from "next/link";
import { format, startOfMonth, endOfMonth, eachDayOfInterval, getDay, addMonths, subMonths, parseISO, isAfter, differenceInHours, isToday } from "date-fns";

export default function AdminDashboardPage() {
  const dispatch = useAppDispatch();
  const router = useRouter();
  const { admin, slots, isAuthenticated, isLoading } = useAppSelector(s => s.adminAuth);

  // calendar
  const [currentMonth, setCurrentMonth] = useState(new Date());
  // modal state
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({ date: "", startTime: "", endTime: "" });
  // slot info modal
  const [selectedSlot, setSelectedSlot] = useState<any>(null);
  const [showSlotInfoModal, setShowSlotInfoModal] = useState(false);

  // guard
  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.push("/admin/login");
    else if (isAuthenticated && !admin) dispatch(fetchAdminData());
  }, [isLoading, isAuthenticated, admin, dispatch, router]);

  if (isLoading || !admin) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-lg">Loading admin dashboard…</p>
      </div>
    );
  }

  // 🚀 Metrics
  const now = new Date();
  const weekStart = new Date(now);
  weekStart.setDate(now.getDate() - now.getDay()); // Sunday
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekStart.getDate() + 6);
  const thisMonthStart = startOfMonth(now);
  const thisMonthEnd = endOfMonth(now);

  const availableSlotsThisWeek = slots.filter(s => {
    if (s.is_booked) return false;
    const dt = parseISO(s.start_time!);
    return isAfter(dt, weekStart) && isAfter(weekEnd, dt);
  }).length;

  const bookedSlotsTotal = slots.filter(s => s.is_booked).length;

  // hours available this month = sum of durations (in hours) of unbooked slots this month
  const hoursAvailableThisMonth = slots.reduce((sum, s) => {
    if (s.is_booked) return sum;
    const start = parseISO(s.start_time!);
    if (start < thisMonthStart || start > thisMonthEnd) return sum;
    const end = parseISO(s.end_time!);
    return sum + differenceInHours(end, start);
  }, 0);

  // calendar grid
  const monthStart = startOfMonth(currentMonth);
  const monthEnd = endOfMonth(currentMonth);
  const days = eachDayOfInterval({ start: monthStart, end: monthEnd });
  const leadingBlanks = Array(getDay(monthStart)).fill(null);
  const grid = [...leadingBlanks, ...days];

  // handle slot creation
  function addSlot() {
    if (!form.date || !form.startTime || !form.endTime) return;
    dispatch(createSlots({
      slots: [{
        start_time: `${form.date}T${form.startTime}`,
        end_time:   `${form.date}T${form.endTime}`
      }]
    }))
    .then(() => {
      setShowModal(false);
      setForm({ date: "", startTime: "", endTime: "" });
    });
  }

  return (
    <Layout>
      <div className="container mx-auto p-6 space-y-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold">
              Welcome, {admin.firstname} {admin.lastname}
            </h1>
            <p className="text-gray-600">
              {admin.is_superadmin ? "Super Admin" : "Administrator"} | {admin.email}
            </p>
          </div>
          <Link
            href="/admin/bookings"
            className="mt-4 sm:mt-0 flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Users className="h-5 w-5 mr-2" />
            Student Appointments
          </Link>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white p-4 rounded-xl shadow-sm">
            <div className="text-sm text-gray-600">Available Slots</div>
            <div className="text-2xl font-semibold mt-1 text-green-600">
              {availableSlotsThisWeek}
            </div>
            <div className="text-xs text-gray-500 mt-1">This week</div>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-sm">
            <div className="text-sm text-gray-600">Booked Slots</div>
            <div className="text-2xl font-semibold mt-1">
              {bookedSlotsTotal}
            </div>
            <div className="text-xs text-green-600 mt-1 flex items-center">
              {/* you could compute delta from last week here */}
              <svg className="h-3 w-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
                <path d="M5 10l5-5 5 5H5z" />
              </svg>
              +2 from last week
            </div>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-sm">
            <div className="text-sm text-gray-600">Hours Available</div>
            <div className="text-2xl font-semibold mt-1">
              {hoursAvailableThisMonth}
            </div>
            <div className="text-xs text-gray-500 mt-1">This month</div>
          </div>
        </div>

        {/* Calendar Controls */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setCurrentMonth(subMonths(currentMonth, 1))}
              className="p-2 bg-white border rounded-lg hover:bg-gray-50"
            >
              <ChevronLeft />
            </button>
            <span className="text-lg font-medium">
              {format(currentMonth, "MMMM yyyy")}
            </span>
            <button
              onClick={() => setCurrentMonth(addMonths(currentMonth, 1))}
              className="p-2 bg-white border rounded-lg hover:bg-gray-50"
            >
              <ChevronRight />
            </button>
            <button
              onClick={() => setCurrentMonth(new Date())}
              className="px-4 py-2 bg-white border rounded-lg hover:bg-gray-50"
            >
              Today
            </button>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
          >
            + Add Available Time
          </button>
        </div>

        {/* Calendar Grid */}
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
          {/* Days of week */}
          <div className="grid grid-cols-7 border-b bg-gray-50">
            {["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].map(d => (
              <div key={d} className="p-2 text-center font-medium text-gray-600">
                {d}
              </div>
            ))}
          </div>
          {/* Dates */}
          <div className="grid grid-cols-7">
            {grid.map((day, i) => {
              if (!day) {
                return <div key={i} className="h-32 border bg-gray-50" />;
              }
              const iso = format(day, "yyyy-MM-dd");
              const daySlots = slots.filter(s =>
                format(parseISO(s.start_time!), "yyyy-MM-dd") === iso
              );
              const isCurrent = day.getMonth() === currentMonth.getMonth();
              const isCurrentDay = isToday(day);
              
              return (
                <div
                  key={i}
                  className={`h-32 border p-2 flex flex-col ${
                    isCurrent 
                      ? isCurrentDay 
                        ? "bg-blue-50" 
                        : "bg-white" 
                      : "bg-gray-50 text-gray-400"
                  }`}
                >
                  <div className={`text-sm font-semibold ${isCurrentDay ? "text-blue-600" : ""}`}>
                    {format(day, "d")}
                  </div>
                  <div className="mt-1 space-y-1 text-xs overflow-y-auto">
                    {daySlots.map(s => {
                      const start = format(parseISO(s.start_time!), "h:mm a");
                      const end   = format(parseISO(s.end_time!),   "h:mm a");
                      
                      return (
                        <button
                          key={s.id}
                          onClick={() => {
                            setSelectedSlot(s);
                            setShowSlotInfoModal(true);
                          }}
                          className={`w-full text-left px-1 py-0.5 rounded flex items-center justify-between ${
                            s.is_booked
                              ? "bg-blue-100 text-blue-800 hover:bg-blue-200"
                              : "bg-green-100 text-green-800 hover:bg-green-200"
                          }`}
                        >
                          <span>
                            {start} – {end}
                            {s.is_booked && s.booking?.student && (
                              <span className="block text-xs truncate">
                                {s.booking.student.firstname} {s.booking.student.lastname}
                              </span>
                            )}
                          </span>
                          {s.is_booked && (
                            <Info className="h-3.5 w-3.5 flex-shrink-0" />
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Add Slot Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-96">
            <h3 className="text-lg font-semibold mb-4">Add Available Time Slot</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm mb-1">Date</label>
                <input
                  type="date"
                  className="w-full p-2 border rounded-lg"
                  value={form.date}
                  onChange={e => setForm(f => ({ ...f, date: e.target.value }))}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm mb-1">Start Time</label>
                  <input
                    type="time"
                    className="w-full p-2 border rounded-lg"
                    value={form.startTime}
                    onChange={e => setForm(f => ({ ...f, startTime: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="block text-sm mb-1">End Time</label>
                  <input
                    type="time"
                    className="w-full p-2 border rounded-lg"
                    value={form.endTime}
                    onChange={e => setForm(f => ({ ...f, endTime: e.target.value }))}
                  />
                </div>
              </div>
              <div className="flex justify-end space-x-2 pt-4">
                <button
                  className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                  onClick={() => setShowModal(false)}
                >
                  Cancel
                </button>
                <button
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
                  onClick={addSlot}
                >
                  Add Time Slot
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Slot Info Modal */}
      {showSlotInfoModal && selectedSlot && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-96 max-w-md">
            <h3 className="text-lg font-semibold mb-4">
              {selectedSlot.is_booked ? "Booked Appointment" : "Available Time Slot"}
            </h3>
            <div className="space-y-3">
              <div>
                <div className="text-sm text-gray-600">Date</div>
                <div className="font-medium">
                  {format(parseISO(selectedSlot.start_time), "EEEE, MMMM d, yyyy")}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-600">Time</div>
                <div className="font-medium">
                  {format(parseISO(selectedSlot.start_time), "h:mm a")} - {format(parseISO(selectedSlot.end_time), "h:mm a")}
                </div>
              </div>
              
              {selectedSlot.is_booked && selectedSlot.booking?.student ? (
                <div className="border-t pt-3 mt-3">
                  <div className="text-sm font-semibold text-gray-700 mb-2">Student Information</div>
                  <div className="space-y-2">
                    <div>
                      <div className="text-sm text-gray-600">Name</div>
                      <div className="font-medium">
                        {selectedSlot.booking.student.firstname} {selectedSlot.booking.student.lastname}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600">Student ID</div>
                      <div className="font-medium">
                        {selectedSlot.booking.student.student_id}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600">Email</div>
                      <div className="font-medium">
                        {selectedSlot.booking.student.email}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600">Booked On</div>
                      <div className="font-medium">
                        {format(parseISO(selectedSlot.booking.created_at), "MMM d, yyyy 'at' h:mm a")}
                      </div>
                    </div>
                  </div>
                </div>
              ) : selectedSlot.is_booked ? (
                <div className="text-amber-600 mt-2">
                  Student information not available. View complete details in the Student Appointments page.
                </div>
              ) : null}
              
              <div className="flex justify-end space-x-2 pt-4 mt-2">
                <button
                  className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                  onClick={() => {
                    setSelectedSlot(null);
                    setShowSlotInfoModal(false);
                  }}
                >
                  Close
                </button>
                {selectedSlot.is_booked && (
                  <Link
                    href="/admin/bookings"
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                  >
                    View All Bookings
                  </Link>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}