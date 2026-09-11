/**
 * Demo student fixture — LOCAL DEVELOPMENT ONLY.
 *
 * Mirrors the row shape returned by the orion_* SQL functions so the API can
 * operate without Supabase configured. Always flagged with demo: true in API
 * responses. In production the identity comes from auth.uid() via
 * orion_student_context(); this fixture is never mixed with real rows.
 */
export const DEMO_STUDENT = {
  user_id: "00000000-0000-0000-0000-0000000000d3",
  display_name: "Demo Student (dev seed)",
  semester: 3,
  programme: "B.Tech",
  branch: "COMPUTER SCIENCE AND ENGINEERING",
  batch: "I",
  section: "I",
  entries: [
    {
      course_code: "ICS 211",
      course_name: "DESIGN AND ANALYSIS OF ALGORITHMS",
      faculty_names: ["Dr. Priyadarshini"],
      room: null,
      day_of_week: 1,
      slot_index: 1,
      start_time: "09:00",
      end_time: "09:55",
      entry_type: "class",
    },
    {
      course_code: "IMA 211",
      course_name: "PROBABILITY, STATISTICS AND RANDOM PROCESSES",
      faculty_names: ["Dr. Anandhu Mohan"],
      room: null,
      day_of_week: 2,
      slot_index: 2,
      start_time: "10:00",
      end_time: "10:55",
      entry_type: "class",
    },
    {
      course_code: "ICS 212",
      course_name: "THEORY OF COMPUTATION",
      faculty_names: ["Dr. Divya Sindhu Lekha", "Dr. Sushitha Susan Joseph"],
      room: null,
      day_of_week: 3,
      slot_index: 3,
      start_time: "11:05",
      end_time: "12:00",
      entry_type: "class",
    },
    {
      course_code: "ICS 214",
      course_name: "IT WORKSHOP III",
      faculty_names: ["Dr. Deepak Jose"],
      room: null,
      day_of_week: 4,
      slot_index: 6,
      start_time: "15:00",
      end_time: "15:55",
      entry_type: "lab",
    },
    {
      course_code: null,
      course_name: "CODING CLUB ACTIVITIES",
      faculty_names: [],
      room: null,
      day_of_week: 5,
      slot_index: 8,
      start_time: "17:00",
      end_time: "19:00",
      entry_type: "club_activity",
    },
  ],
} as const;
