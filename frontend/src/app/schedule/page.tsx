"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Layout } from "@/app/components/layout/Layout";
import { useAppSelector } from "@/store/hooks";
import { moodleApi } from "@/lib/api/moodleClient";
import { ChevronLeft, ChevronRight, AlertCircle, CheckCircle2 } from "lucide-react";
import { 
  format, 
  startOfMonth, 
  endOfMonth, 
  eachDayOfInterval, 
  getDay, 
  addMonths, 
  subMonths, 
  parseISO, 
  isToday,
  isSameDay, // Added for checking if a booking is on the current day
  startOfWeek, // Added for week view logic
  endOfWeek // Added for week view logic
} from "date-fns";
import { StudentBooking } from "@/types/moodle";

// Interface for slot
interface Slot {
  id: number;
  admin_id: number;
  start_time: string;
  end_time: string;
  is_booked: boolean;
  admin?: {
    id: number;
    firstname: string;
    lastname: string;
    email: string;
    login_id: number;
  }
}

export default function BookAppointmentPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading, user } = useAppSelector(s => s.auth);
  
  // States
  const [availableSlots, setAvailableSlots] = useState<Slot[]>([]);
  const [userBookings, setUserBookings] = useState<StudentBooking[]>([]);
  const [isLoadingSlots, setIsLoadingSlots] = useState(true);
  const [bookingSuccess, setBookingSuccess] = useState<string | null>(null);
  const [bookingError, setBookingError] = useState<string | null>(null);
  const [cancelSuccess, setCancelSuccess] = useState<string | null>(null);
  
  // Calendar state
  const [currentDate, setCurrentDate] = useState(new Date()); // Renamed from currentMonth for clarity with week view
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [slotToCancel, setSlotToCancel] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<'week' | 'month'>('month'); // Default to month view

  // Load data function
  const loadData = async () => {
    try {
      setIsLoadingSlots(true);
      // Fetch both available slots and user's bookings in parallel
      const [slots, bookings] = await Promise.all([
        moodleApi.getAvailableSlots(),
        moodleApi.getStudentBookings()
      ]);
      setAvailableSlots(slots);
      setUserBookings(bookings);
    } catch (error) {
      console.error("Failed to fetch data:", error);
      setBookingError("Failed to load appointment data. Please try refreshing the page.");
    } finally {
      setIsLoadingSlots(false);
    }
  };

  // Effect to load data when authenticated
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login");
      return;
    }
    
    if (isAuthenticated) {
      loadData();
    }
  }, [isLoading, isAuthenticated, router]);

  // Book slot function
  const bookSlot = async () => {
    if (!selectedSlot) return;
    
    try {
      setBookingError(null);
      setBookingSuccess(null); // Clear previous success message
      await moodleApi.bookSlot(selectedSlot.id);
      
      setBookingSuccess(`Appointment successfully booked for ${format(parseISO(selectedSlot.start_time), "EEEE, MMMM d, yyyy 'at' h:mm a")}`);
      setShowConfirmModal(false);
      setSelectedSlot(null);
      
      // Refresh data
      await loadData();
    } catch (error: any) {
      console.error("Booking error:", error);
      setBookingError(error.message || "Failed to book appointment. Please try again.");
      setShowConfirmModal(false); // Close modal on error too
    }
  };

  // Cancel booking function
  const cancelBooking = async () => {
    if (slotToCancel == null) return;
    try {
      setBookingError(null);
      setCancelSuccess(null); // Clear previous success message
      await moodleApi.cancelBooking(slotToCancel);
      setCancelSuccess("Appointment successfully cancelled");
      setShowCancelModal(false);
      setSlotToCancel(null);
      await loadData(); // Refresh data
    } catch (err: any) {
      console.error("Cancellation error:", err);
      setBookingError(err.message || "Failed to cancel appointment");
      setShowCancelModal(false); // Close modal on error too
    }
  };
  

  if (isLoading || (!isAuthenticated && !isLoading)) { // Show loading if auth is loading or if not authenticated yet
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-lg">Loading user data…</p>
      </div>
    );
  }
  
  if (isLoadingSlots && isAuthenticated) { // Show loading for slots if authenticated and slots are loading
     return (
      <Layout>
        <div className="flex h-full items-center justify-center p-6">
          <p className="text-lg">Loading appointments…</p>
        </div>
      </Layout>
    );
  }


  // Calendar setup for Month View
  const monthStart = startOfMonth(currentDate);
  const monthEnd = endOfMonth(currentDate);
  const monthDays = eachDayOfInterval({ start: monthStart, end: monthEnd });
  const leadingBlanks = Array(getDay(monthStart)).fill(null);
  const monthGrid = [...leadingBlanks, ...monthDays];

  // Calendar setup for Week View
  // Ensure week starts on Sunday for getDay compatibility, adjust if your locale is different
  const weekViewStart = startOfWeek(currentDate, { weekStartsOn: 0 }); 
  const weekViewEnd = endOfWeek(currentDate, { weekStartsOn: 0 });
  const weekDays = eachDayOfInterval({ start: weekViewStart, end: weekViewEnd });


  const handlePrev = () => {
    if (viewMode === 'month') {
      setCurrentDate(subMonths(currentDate, 1));
    } else {
      setCurrentDate(subMonths(currentDate, 1)); // For week view, go to previous month, then select week
    }
  };

  const handleNext = () => {
    if (viewMode === 'month') {
      setCurrentDate(addMonths(currentDate, 1));
    } else {
      setCurrentDate(addMonths(currentDate, 1)); // For week view, go to next month, then select week
    }
  };
  
  const handleToday = () => {
    setCurrentDate(new Date());
  };


  return (
    <Layout>
      <div className="container mx-auto p-4 sm:p-6 space-y-6">
        {/* Success messages */}
        {bookingSuccess && (
          <div className="bg-green-100 border-l-4 border-green-500 text-green-700 p-4 rounded-md relative flex items-start shadow">
            <CheckCircle2 className="h-5 w-5 mr-3 mt-0.5 flex-shrink-0" />
            <span className="block sm:inline flex-grow">{bookingSuccess}</span>
            <button 
              onClick={() => setBookingSuccess(null)}
              className="ml-4 p-1 text-green-700 hover:text-green-900"
              aria-label="Close success message"
            >
              <span className="text-2xl">&times;</span>
            </button>
          </div>
        )}

        {cancelSuccess && (
          <div className="bg-green-100 border-l-4 border-green-500 text-green-700 p-4 rounded-md relative flex items-start shadow">
            <CheckCircle2 className="h-5 w-5 mr-3 mt-0.5 flex-shrink-0" />
            <span className="block sm:inline flex-grow">{cancelSuccess}</span>
            <button 
              onClick={() => setCancelSuccess(null)}
              className="ml-4 p-1 text-green-700 hover:text-green-900"
              aria-label="Close success message"
            >
              <span className="text-2xl">&times;</span>
            </button>
          </div>
        )}

        {/* Error message */}
        {bookingError && (
          <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 rounded-md relative flex items-start shadow">
            <AlertCircle className="h-5 w-5 mr-3 mt-0.5 flex-shrink-0" />
            <span className="block sm:inline flex-grow">{bookingError}</span>
            <button 
              onClick={() => setBookingError(null)}
              className="ml-4 p-1 text-red-700 hover:text-red-900"
              aria-label="Close error message"
            >
              <span className="text-2xl">&times;</span>
            </button>
          </div>
        )}

        {/* Your Upcoming Appointments */}
        {userBookings.length > 0 && (
          <div className="bg-white p-4 sm:p-6 rounded-xl shadow-lg space-y-4">
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-800">Your Upcoming Appointments</h2>
            <div className="space-y-3">
              {userBookings
                .filter(booking => booking.slot && new Date(booking.slot.start_time) >= new Date()) // Show only future or current bookings
                .sort((a, b) => new Date(a.slot.start_time).getTime() - new Date(b.slot.start_time).getTime()) // Sort by date
                .map(booking => {
                const slotInfo = booking.slot;
                if (!slotInfo) return null;
                
                return (
                  <div key={booking.id} className="flex flex-col sm:flex-row items-start sm:items-center justify-between p-3 bg-indigo-50 rounded-lg border border-indigo-200">
                    <div className="mb-2 sm:mb-0">
                      <p className="font-medium text-indigo-700">{format(parseISO(slotInfo.start_time), "EEEE, MMMM d, yyyy")}</p>
                      <p className="text-gray-600">{format(parseISO(slotInfo.start_time), "h:mm a")} - {format(parseISO(slotInfo.end_time), "h:mm a")}</p>
                      {slotInfo.admin && (
                        <p className="text-gray-500 text-sm">with {slotInfo.admin.firstname} {slotInfo.admin.lastname}</p>
                      )}
                    </div>
                    <button 
                      className="px-3 py-1.5 bg-red-500 text-white rounded-lg hover:bg-red-600 text-sm font-medium transition-colors"
                      onClick={() => {
                        setSlotToCancel(slotInfo.id);
                        setShowCancelModal(true);
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                );
              })}
              {userBookings.filter(booking => booking.slot && new Date(booking.slot.start_time) >= new Date()).length === 0 && (
                <p className="text-gray-500">You have no upcoming appointments.</p>
              )}
            </div>
          </div>
        )}
        
        {userBookings.length === 0 && !isLoadingSlots && (
             <div className="bg-white p-4 sm:p-6 rounded-xl shadow-lg space-y-4">
                <h2 className="text-xl sm:text-2xl font-semibold text-gray-800">Your Appointments</h2>
                <p className="text-gray-500">You have no appointments scheduled.</p>
            </div>
        )}


        {/* Calendar Section */}
        <div className="bg-white p-4 sm:p-6 rounded-xl shadow-lg">
            <h2 className="text-xl sm:text-2xl font-semibold text-gray-800 mb-4">Available Slots</h2>
            {/* Calendar Controls */}
            <div className="flex flex-col sm:flex-row items-center justify-between mb-4 gap-2">
                <div className="flex items-center space-x-2">
                <button
                    onClick={handlePrev}
                    className="p-2 bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200 transition-colors"
                    aria-label="Previous month"
                >
                    <ChevronLeft className="h-5 w-5 text-gray-600" />
                </button>
                <span className="text-lg font-medium text-gray-700 w-32 text-center">
                    {format(currentDate, "MMMM yyyy")}
                </span>
                <button
                    onClick={handleNext}
                    className="p-2 bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200 transition-colors"
                    aria-label="Next month"
                >
                    <ChevronRight className="h-5 w-5 text-gray-600" />
                </button>
                <button
                    onClick={handleToday}
                    className="px-3 py-2 bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200 text-sm font-medium text-gray-700 transition-colors"
                >
                    Today
                </button>
                </div>

                <div className="flex space-x-1 border border-gray-300 rounded-lg p-0.5 bg-gray-100">
                <button
                    onClick={() => setViewMode('week')}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    viewMode === 'week'
                        ? 'bg-blue-600 text-white shadow-sm'
                        : 'text-gray-600 hover:bg-gray-200'
                    }`}
                >
                    Week
                </button>
                <button
                    onClick={() => setViewMode('month')}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    viewMode === 'month'
                        ? 'bg-blue-600 text-white shadow-sm'
                        : 'text-gray-600 hover:bg-gray-200'
                    }`}
                >
                    Month
                </button>
                </div>
            </div>

            {/* Calendar Grid */}
            <div className="overflow-x-auto">
                <div className="grid grid-cols-7 border-b border-gray-200 bg-gray-50">
                {["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].map(d => (
                    <div key={d} className="p-2 text-center font-medium text-xs sm:text-sm text-gray-500">
                    {d}
                    </div>
                ))}
                </div>
                
                {/* Dates - Week View */}
                {viewMode === 'week' && (
                <div className="grid grid-cols-7 min-w-[600px] sm:min-w-full"> {/* Ensure minimum width for smaller screens */}
                    {weekDays.map((day, i) => {
                    const isoDate = format(day, "yyyy-MM-dd");
                    // Available slots for the current day
                    const daySlots = availableSlots.filter(s =>
                        format(parseISO(s.start_time), "yyyy-MM-dd") === isoDate && !s.is_booked
                    ).sort((a,b) => parseISO(a.start_time).getTime() - parseISO(b.start_time).getTime());
                    
                    // User's booked appointments for the current day
                    const bookedAppointmentsOnDay = userBookings.filter(booking =>
                        booking.slot && format(parseISO(booking.slot.start_time), "yyyy-MM-dd") === isoDate
                    ).sort((a,b) => parseISO(a.slot.start_time).getTime() - parseISO(b.slot.start_time).getTime());

                    const isCurrentDisplayMonth = day.getMonth() === currentDate.getMonth();

                    return (
                        <div
                        key={`week-${isoDate}-${i}`}
                        className={`h-40 border border-gray-200 p-1.5 flex flex-col ${
                            isToday(day) ? "bg-blue-50" : isCurrentDisplayMonth ? "bg-white" : "bg-gray-50"
                        }`}
                        >
                        <div className={`text-xs sm:text-sm font-semibold mb-1 ${isToday(day) ? "text-blue-600" : isCurrentDisplayMonth ? "text-gray-700" : "text-gray-400"}`}>
                            {format(day, "d")}
                        </div>
                        <div className="flex-grow space-y-1 text-xs overflow-y-auto pr-1">
                            {/* Display User's Booked Appointments */}
                            {bookedAppointmentsOnDay.map(booking => (
                            <div
                                key={`booked-week-${booking.id}`}
                                className="w-full px-1.5 py-1 rounded bg-indigo-100 text-indigo-700 text-left text-[10px] sm:text-xs leading-tight"
                            >
                                {format(parseISO(booking.slot.start_time), "h:mma")} - {format(parseISO(booking.slot.end_time), "h:mma")}
                                <span className="block font-medium">(Booked)</span>
                                {booking.slot.admin && <span className="block text-indigo-600 text-[9px] sm:text-[10px]">w/ {booking.slot.admin.firstname.charAt(0)}. {booking.slot.admin.lastname}</span>}
                            </div>
                            ))}
                            {/* Display Available Slots */}
                            {daySlots.map(slot => (
                            <button
                                key={`available-week-${slot.id}`}
                                onClick={() => {
                                setSelectedSlot(slot);
                                setShowConfirmModal(true);
                                }}
                                className="w-full px-1.5 py-1 rounded bg-green-100 text-green-700 hover:bg-green-200 text-left text-[10px] sm:text-xs leading-tight transition-colors"
                            >
                                {format(parseISO(slot.start_time), "h:mma")} – {format(parseISO(slot.end_time), "h:mma")}
                                {slot.admin && <span className="block text-green-600 text-[9px] sm:text-[10px]">w/ {slot.admin.firstname.charAt(0)}. {slot.admin.lastname}</span>}
                            </button>
                            ))}
                            {daySlots.length === 0 && bookedAppointmentsOnDay.length === 0 && isCurrentDisplayMonth && (
                                <p className="text-gray-400 text-[10px] sm:text-xs mt-1">No slots</p>
                            )}
                        </div>
                        </div>
                    );
                    })}
                </div>
                )}
                
                {/* Dates - Month View */}
                {viewMode === 'month' && (
                <div className="grid grid-cols-7 min-w-[600px] sm:min-w-full"> {/* Ensure minimum width for smaller screens */}
                    {monthGrid.map((day, i) => {
                    if (!day) {
                        return <div key={`blank-month-${i}`} className="h-32 sm:h-40 border border-gray-200 bg-gray-50" />;
                    }
                    
                    const isoDate = format(day, "yyyy-MM-dd");
                    // Available slots for the current day
                    const daySlots = availableSlots.filter(s =>
                        format(parseISO(s.start_time), "yyyy-MM-dd") === isoDate && !s.is_booked
                    ).sort((a,b) => parseISO(a.start_time).getTime() - parseISO(b.start_time).getTime());

                    // User's booked appointments for the current day
                    const bookedAppointmentsOnDay = userBookings.filter(booking =>
                        booking.slot && format(parseISO(booking.slot.start_time), "yyyy-MM-dd") === isoDate
                    ).sort((a,b) => parseISO(a.slot.start_time).getTime() - parseISO(b.slot.start_time).getTime());
                    
                    const isCurrentDisplayMonth = day.getMonth() === currentDate.getMonth();
                    
                    return (
                        <div
                        key={`month-${isoDate}-${i}`}
                        className={`h-32 sm:h-40 border border-gray-200 p-1.5 flex flex-col ${
                            isCurrentDisplayMonth ? (isToday(day) ? "bg-blue-50" : "bg-white") : "bg-gray-50"
                        }`}
                        >
                        <div className={`text-xs sm:text-sm font-semibold mb-1 ${isToday(day) ? "text-blue-600" : isCurrentDisplayMonth ? "text-gray-700" : "text-gray-400"}`}>
                            {format(day, "d")}
                        </div>
                        <div className="flex-grow space-y-1 text-xs overflow-y-auto pr-1"> {/* Added pr-1 for scrollbar spacing */}
                            {/* Display User's Booked Appointments */}
                            {bookedAppointmentsOnDay.map(booking => (
                            <div
                                key={`booked-month-${booking.id}`}
                                className="w-full px-1.5 py-1 rounded bg-indigo-100 text-indigo-700 text-left text-[10px] sm:text-xs leading-tight"
                            >
                                {format(parseISO(booking.slot.start_time), "h:mma")} - {format(parseISO(booking.slot.end_time), "h:mma")}
                                <span className="block font-medium">(Booked)</span>
                                {booking.slot.admin && <span className="block text-indigo-600 text-[9px] sm:text-[10px]">w/ {booking.slot.admin.firstname.charAt(0)}. {booking.slot.admin.lastname}</span>}
                            </div>
                            ))}
                            {/* Display Available Slots */}
                            {daySlots.map(slot => (
                            <button
                                key={`available-month-${slot.id}`}
                                onClick={() => {
                                setSelectedSlot(slot);
                                setShowConfirmModal(true);
                                }}
                                className="w-full px-1.5 py-1 rounded bg-green-100 text-green-700 hover:bg-green-200 text-left text-[10px] sm:text-xs leading-tight transition-colors"
                            >
                                {format(parseISO(slot.start_time), "h:mma")} – {format(parseISO(slot.end_time), "h:mma")}
                                {slot.admin && <span className="block text-green-600 text-[9px] sm:text-[10px]">w/ {slot.admin.firstname.charAt(0)}. {slot.admin.lastname}</span>}
                            </button>
                            ))}
                            {daySlots.length === 0 && bookedAppointmentsOnDay.length === 0 && isCurrentDisplayMonth && (
                                <p className="text-gray-400 text-[10px] sm:text-xs mt-1">No slots</p>
                            )}
                        </div>
                        </div>
                    );
                    })}
                </div>
                )}
            </div>
        </div>
      </div>

      {/* Booking Confirmation Modal */}
      {showConfirmModal && selectedSlot && (
        <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-2xl">
            <h3 className="text-lg font-semibold mb-1 text-gray-800">Confirm Appointment</h3>
            <p className="text-sm text-gray-600 mb-4">Please confirm the details below.</p>
            
            <div className="space-y-3 bg-gray-50 p-4 rounded-lg mb-6">
              <p className="text-gray-700">
                <span className="font-medium">Date:</span> {format(parseISO(selectedSlot.start_time), "EEEE, MMMM d, yyyy")}
              </p>
              <p className="text-gray-700">
                <span className="font-medium">Time:</span> {format(parseISO(selectedSlot.start_time), "h:mm a")} - {format(parseISO(selectedSlot.end_time), "h:mm a")}
              </p>
              {selectedSlot.admin && (
                <p className="text-gray-700">
                    <span className="font-medium">Advisor:</span> {selectedSlot.admin.firstname} {selectedSlot.admin.lastname}
                </p>
              )}
            </div>

            {bookingError && ( // Show error within modal if booking fails
                <div className="bg-red-100 border border-red-300 text-red-700 px-3 py-2 rounded-md text-sm mb-4 flex items-start">
                    <AlertCircle className="h-4 w-4 mr-2 mt-0.5 flex-shrink-0" />
                    <span>{bookingError}</span>
                </div>
            )}

            <div className="flex justify-end space-x-3">
              <button
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-100 transition-colors text-sm font-medium"
                onClick={() => {
                  setSelectedSlot(null);
                  setShowConfirmModal(false);
                  setBookingError(null); // Clear error when cancelling
                }}
              >
                Cancel
              </button>
              <button
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
                onClick={bookSlot}
              >
                Confirm Booking
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Cancel Confirmation Modal */}
      {showCancelModal && slotToCancel !== null && (
         <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-2xl">
                <h3 className="text-lg font-semibold mb-1 text-gray-800">Cancel Appointment</h3>
                <p className="text-sm text-gray-600 mb-6">Are you sure you want to cancel this appointment?</p>
                
                {/* Optionally, show details of the appointment to be cancelled */}
                {(() => {
                    const bookingToCancel = userBookings.find(b => b.slot_id === slotToCancel)?.slot;
                    if (bookingToCancel) {
                        return (
                            <div className="space-y-2 bg-gray-50 p-3 rounded-lg mb-6 text-sm">
                                <p><span className="font-medium">Date:</span> {format(parseISO(bookingToCancel.start_time), "EEEE, MMMM d, yyyy")}</p>
                                <p><span className="font-medium">Time:</span> {format(parseISO(bookingToCancel.start_time), "h:mm a")} - {format(parseISO(bookingToCancel.end_time), "h:mm a")}</p>
                                {bookingToCancel.admin && <p><span className="font-medium">Advisor:</span> {bookingToCancel.admin.firstname} {bookingToCancel.admin.lastname}</p>}
                            </div>
                        );
                    }
                    return null;
                })()}

                {bookingError && ( // Show error within modal if cancellation fails
                    <div className="bg-red-100 border border-red-300 text-red-700 px-3 py-2 rounded-md text-sm mb-4 flex items-start">
                        <AlertCircle className="h-4 w-4 mr-2 mt-0.5 flex-shrink-0" />
                        <span>{bookingError}</span>
                    </div>
                )}

                <div className="flex justify-end space-x-3">
                <button
                    className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-100 transition-colors text-sm font-medium"
                    onClick={() => {
                    setSlotToCancel(null);
                    setShowCancelModal(false);
                    setBookingError(null); // Clear error when cancelling
                    }}
                >
                    No, Keep It
                </button>
                <button
                    className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-sm font-medium"
                    onClick={cancelBooking}
                >
                    Yes, Cancel
                </button>
                </div>
            </div>
        </div>
      )}
    </Layout>
  );
}
