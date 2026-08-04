export const student = {
  name: "Aarav Menon",
  id: "2022BCS0142",
  branch: "Computer Science & Engineering",
  semester: 6,
  batch: "2022–2026",
  email: "aarav.menon@iiitkottayam.ac.in",
  cgpa: 8.62,
  attendance: 87,
  credits: { earned: 118, total: 160 },
};

export const todaysClasses = [
  { time: "09:00", end: "09:55", code: "CS304", title: "Machine Learning", room: "LH-3", faculty: "Dr. Rekha Nair", status: "done" },
  { time: "10:00", end: "10:55", code: "CS312", title: "Computer Networks", room: "LH-1", faculty: "Dr. Vivek Sharma", status: "done" },
  { time: "11:10", end: "12:05", code: "CS306", title: "Compiler Design", room: "LH-2", faculty: "Dr. Anita George", status: "live" },
  { time: "14:00", end: "16:00", code: "CS318", title: "ML Lab", room: "Lab-B", faculty: "Dr. Rekha Nair", status: "upcoming" },
  { time: "16:15", end: "17:10", code: "HS210", title: "Engineering Economics", room: "LH-5", faculty: "Prof. S. Kurian", status: "upcoming" },
];

export const weekTimetable = [
  { day: "Mon", slots: ["CS304", "CS312", "CS306", "—", "CS318 Lab", "HS210"] },
  { day: "Tue", slots: ["CS312", "CS306", "MA301", "—", "CS304", "—"] },
  { day: "Wed", slots: ["CS306", "CS304", "CS312", "—", "CS320 Lab", "CS320 Lab"] },
  { day: "Thu", slots: ["MA301", "CS304", "HS210", "—", "CS312", "—"] },
  { day: "Fri", slots: ["CS312", "MA301", "CS306", "—", "Mentoring", "Clubs"] },
];

export const slotTimes = ["09:00", "10:00", "11:10", "12:05", "14:00", "16:15"];

export const courses = [
  { code: "CS304", title: "Machine Learning", credits: 4, faculty: "Dr. Rekha Nair", attendance: 91, assignments: 2, progress: 68 },
  { code: "CS312", title: "Computer Networks", credits: 3, faculty: "Dr. Vivek Sharma", attendance: 84, assignments: 1, progress: 72 },
  { code: "CS306", title: "Compiler Design", credits: 4, faculty: "Dr. Anita George", attendance: 78, assignments: 3, progress: 55 },
  { code: "MA301", title: "Probability & Statistics", credits: 3, faculty: "Dr. P. Ramesh", attendance: 93, assignments: 0, progress: 80 },
  { code: "HS210", title: "Engineering Economics", credits: 2, faculty: "Prof. S. Kurian", attendance: 88, assignments: 1, progress: 61 },
  { code: "CS318", title: "Machine Learning Lab", credits: 2, faculty: "Dr. Rekha Nair", attendance: 96, assignments: 1, progress: 74 },
];

export const faculty = [
  { name: "Dr. Rekha Nair", dept: "CSE", role: "Associate Professor", cabin: "AB-214", email: "rekha@iiitkottayam.ac.in", phone: "+91 98470 11223", available: true, hours: "Mon–Wed, 3–5 PM", research: "Deep Learning, Vision", subjects: ["CS304", "CS318"] },
  { name: "Dr. Vivek Sharma", dept: "CSE", role: "Assistant Professor", cabin: "AB-118", email: "vivek@iiitkottayam.ac.in", phone: "+91 98470 44551", available: false, hours: "Tue & Thu, 2–4 PM", research: "Networks, Edge Systems", subjects: ["CS312"] },
  { name: "Dr. Anita George", dept: "CSE", role: "Professor", cabin: "AB-301", email: "anita@iiitkottayam.ac.in", phone: "+91 98470 88112", available: true, hours: "Daily, 4–5 PM", research: "Compilers, PL Theory", subjects: ["CS306"] },
  { name: "Dr. P. Ramesh", dept: "Mathematics", role: "Associate Professor", cabin: "BB-105", email: "ramesh@iiitkottayam.ac.in", phone: "+91 98470 33447", available: true, hours: "Wed–Fri, 11–1 PM", research: "Stochastic Processes", subjects: ["MA301"] },
  { name: "Prof. S. Kurian", dept: "Humanities", role: "Professor", cabin: "BB-208", email: "kurian@iiitkottayam.ac.in", phone: "+91 98470 66778", available: false, hours: "Mon, 10–12 PM", research: "Development Economics", subjects: ["HS210"] },
  { name: "Dr. Neha Pillai", dept: "ECE", role: "Assistant Professor", cabin: "AB-402", email: "neha@iiitkottayam.ac.in", phone: "+91 98470 99001", available: true, hours: "Tue–Thu, 3–4 PM", research: "VLSI, Embedded", subjects: ["EC205"] },
];

export const announcements = [
  { id: 1, title: "Mid-semester exam schedule released", body: "Mid-sem exams begin 18 Aug. Hall tickets are live in the Exams module. Check seating plans before reporting.", tag: "Academics", priority: "high", pinned: true, time: "2h ago", author: "Academic Section" },
  { id: 2, title: "Hostel water supply maintenance", body: "Block C water supply will be interrupted on Saturday between 10 AM and 2 PM.", tag: "Hostel", priority: "medium", pinned: true, time: "5h ago", author: "Hostel Office" },
  { id: 3, title: "TechFest ORION'26 registrations open", body: "Register for 24 events across coding, robotics and design. Early-bird closes Friday.", tag: "Events", priority: "low", pinned: false, time: "1d ago", author: "Student Council" },
  { id: 4, title: "Library extended hours during exams", body: "The central library will remain open until 1 AM from 12 Aug to 30 Aug.", tag: "Library", priority: "low", pinned: false, time: "2d ago", author: "Library" },
  { id: 5, title: "CS306 lab sheet 4 uploaded", body: "Compiler Design lab sheet 4 with the LALR parser assignment is now available.", tag: "Department", priority: "medium", pinned: false, time: "3d ago", author: "Dr. Anita George" },
];

export const assignments = [
  { title: "ML: CNN from scratch", course: "CS304", due: "Aug 06", left: "2 days", progress: 60 },
  { title: "CN: Socket programming report", course: "CS312", due: "Aug 09", left: "5 days", progress: 20 },
  { title: "CD: LALR parser", course: "CS306", due: "Aug 12", left: "8 days", progress: 0 },
];

export const exams = [
  { code: "CS304", title: "Machine Learning", date: "18 Aug 2026", time: "09:30 – 11:30", venue: "Hall A", seat: "A-42", status: "upcoming" },
  { code: "CS312", title: "Computer Networks", date: "20 Aug 2026", time: "09:30 – 11:30", venue: "Hall B", seat: "B-11", status: "upcoming" },
  { code: "CS306", title: "Compiler Design", date: "22 Aug 2026", time: "14:00 – 16:00", venue: "Hall A", seat: "A-07", status: "upcoming" },
  { code: "MA301", title: "Probability & Statistics", date: "12 Jun 2026", time: "09:30 – 11:30", venue: "Hall C", seat: "C-19", status: "completed", grade: "A" },
  { code: "HS210", title: "Engineering Economics", date: "10 Jun 2026", time: "14:00 – 16:00", venue: "Hall B", seat: "B-30", status: "completed", grade: "A+" },
];

export const messMenu = [
  { meal: "Breakfast", time: "07:30 – 09:15", items: ["Idli & sambar", "Coconut chutney", "Banana", "Filter coffee"], rating: 4.2 },
  { meal: "Lunch", time: "12:15 – 14:00", items: ["Kerala rice", "Sambar", "Beans thoran", "Fish curry / Paneer", "Curd"], rating: 4.5, special: true },
  { meal: "Snacks", time: "16:30 – 17:30", items: ["Parippu vada", "Tea"], rating: 3.9 },
  { meal: "Dinner", time: "19:30 – 21:00", items: ["Chapati", "Veg kurma", "Egg roast", "Rice & rasam"], rating: 4.0 },
];

export const clubs = [
  { name: "Codex", category: "Technical", members: 214, desc: "Competitive programming & open source guild.", joined: true },
  { name: "Pixel Studio", category: "Design", members: 96, desc: "UI, motion and game-art collective.", joined: false },
  { name: "Robotix", category: "Technical", members: 132, desc: "Robotics, drones and embedded builds.", joined: false },
  { name: "Rhythmix", category: "Cultural", members: 178, desc: "Music, dance and campus performances.", joined: true },
  { name: "Lens", category: "Media", members: 88, desc: "Photography and campus storytelling.", joined: false },
  { name: "Trailblazers", category: "Sports", members: 143, desc: "Trekking, athletics and fitness.", joined: false },
];

export const events = [
  { name: "ORION TechFest 2026", date: "22 Aug", time: "09:00", venue: "Main Auditorium", tag: "Fest", seats: "412 registered" },
  { name: "GSoC Info Session", date: "07 Aug", time: "17:30", venue: "Seminar Hall 2", tag: "Talk", seats: "86 registered" },
  { name: "Inter-hostel Football Final", date: "09 Aug", time: "16:00", venue: "Sports Ground", tag: "Sports", seats: "Open" },
  { name: "Pixel Jam 48h", date: "15 Aug", time: "10:00", venue: "Design Lab", tag: "Hackathon", seats: "62 registered" },
];

export const calendarEvents = [
  { date: "05 Aug", label: "Assignment deadline — CS304", type: "deadline" },
  { date: "12 Aug", label: "Library extended hours begin", type: "event" },
  { date: "15 Aug", label: "Independence Day — Holiday", type: "holiday" },
  { date: "18 Aug", label: "Mid-semester examinations begin", type: "exam" },
  { date: "26 Aug", label: "Mid-semester examinations end", type: "exam" },
  { date: "02 Sep", label: "Project review — Phase I", type: "deadline" },
];

export const documents = [
  { name: "Academic Regulations 2026", category: "Academics", size: "1.8 MB", updated: "12 Jul" },
  { name: "Hostel Handbook", category: "Hostel", size: "920 KB", updated: "03 Jun" },
  { name: "Bonafide Certificate Format", category: "Forms", size: "180 KB", updated: "22 May" },
  { name: "Anti-ragging Policy", category: "Policy", size: "410 KB", updated: "10 Jan" },
  { name: "Scholarship Guidelines", category: "Finance", size: "640 KB", updated: "28 Apr" },
];

export const notifications = [
  { group: "Today", items: [
    { title: "CS306 class moved to LH-2", time: "10 min ago", unread: true, type: "timetable" },
    { title: "New announcement: Hall tickets live", time: "2h ago", unread: true, type: "announcement" },
  ] },
  { group: "Yesterday", items: [
    { title: "Assignment graded — MA301", time: "1d ago", unread: false, type: "academics" },
    { title: "Codex club meetup at 6 PM", time: "1d ago", unread: false, type: "clubs" },
  ] },
];

export const attendanceTrend = [
  { month: "Feb", value: 78 },
  { month: "Mar", value: 82 },
  { month: "Apr", value: 80 },
  { month: "May", value: 86 },
  { month: "Jun", value: 90 },
  { month: "Jul", value: 87 },
];

export const uploads = [
  { file: "timetable_s6_cse.pdf", type: "Timetable", status: "approved", date: "02 Aug", confidence: 97 },
  { file: "mess_menu_week32.jpg", type: "Mess Menu", status: "pending", date: "03 Aug", confidence: 88 },
  { file: "notice_midsem.pdf", type: "Announcement", status: "rejected", date: "01 Aug", confidence: 64 },
  { file: "lab_rotation_b.png", type: "Timetable", status: "approved", date: "28 Jul", confidence: 93 },
];

export const adminStats = [
  { label: "Active users", value: 1284, delta: "+6.2%" },
  { label: "AI queries today", value: 3471, delta: "+18.4%" },
  { label: "OCR accuracy", value: 94, suffix: "%", delta: "+1.1%" },
  { label: "Storage used", value: 62, suffix: "%", delta: "+3.0%" },
];

export const usageTrend = [
  { day: "Mon", users: 640, queries: 1820 },
  { day: "Tue", users: 720, queries: 2140 },
  { day: "Wed", users: 810, queries: 2610 },
  { day: "Thu", users: 770, queries: 2380 },
  { day: "Fri", users: 900, queries: 3120 },
  { day: "Sat", users: 520, queries: 1450 },
  { day: "Sun", users: 470, queries: 1260 },
];

export const users = [
  { name: "Aarav Menon", id: "2022BCS0142", role: "Student", dept: "CSE", status: "active" },
  { name: "Diya Krishnan", id: "2022BCS0088", role: "CR", dept: "CSE", status: "active" },
  { name: "Rahul Varma", id: "2023BEC0031", role: "Student", dept: "ECE", status: "suspended" },
  { name: "Dr. Rekha Nair", id: "FAC0021", role: "Faculty", dept: "CSE", status: "active" },
  { name: "Meera Joseph", id: "ADM0004", role: "Admin", dept: "Registrar", status: "active" },
];

export const aiSuggestions = [
  "Summarise my Compiler Design notes for mid-sem",
  "When is Dr. Rekha Nair free today?",
  "What's for lunch at the mess?",
  "How many classes can I skip in CS306?",
];

export const conversations = [
  { title: "Mid-sem revision plan", time: "2h ago", pinned: true },
  { title: "Explain LALR parsing", time: "Yesterday", pinned: true },
  { title: "Hostel leave procedure", time: "2d ago", pinned: false },
  { title: "GSoC proposal review", time: "5d ago", pinned: false },
];
