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

export const courses = [
  { code: "CS304", title: "Machine Learning", credits: 4, faculty: "Dr. Rekha Nair", attendance: 91, assignments: 2, progress: 68 },
  { code: "CS312", title: "Computer Networks", credits: 3, faculty: "Dr. Vivek Sharma", attendance: 84, assignments: 1, progress: 72 },
  { code: "CS306", title: "Compiler Design", credits: 4, faculty: "Dr. Anita George", attendance: 78, assignments: 3, progress: 55 },
  { code: "MA301", title: "Probability & Statistics", credits: 3, faculty: "Dr. P. Ramesh", attendance: 93, assignments: 0, progress: 80 },
  { code: "HS210", title: "Engineering Economics", credits: 2, faculty: "Prof. S. Kurian", attendance: 88, assignments: 1, progress: 61 },
  { code: "CS318", title: "Machine Learning Lab", credits: 2, faculty: "Dr. Rekha Nair", attendance: 96, assignments: 1, progress: 74 },
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
