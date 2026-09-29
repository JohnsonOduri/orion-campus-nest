// Institute roll numbers encode the branch and the batch:
//
//     2024 BCS 0086
//     ^^^^ ^^^ ^^^^
//     year  |  serial -> batch = serial % 4 + 1  (86 % 4 = 2 -> batch 3)
//           branch
//
// This mirrors orion_parse_roll() in
// supabase/migrations/20260929100000_department_matching_and_roll_derivation.sql.
// The SQL is authoritative — complete_registration re-derives everything
// server-side and ignores whatever the form posts, because a roll number is
// the institute's own record and a dropdown is just a guess. This copy exists
// only so the student can SEE which class they're about to be registered
// into before they submit. Keep the two in step.

export const BRANCHES = {
  BCS: { key: "cse", department: "COMPUTER SCIENCE AND ENGINEERING", short: "CSE" },
  BCD: {
    key: "aids",
    department: "CSE WITH SPECIALISATION IN AI AND DATA SCIENCE",
    short: "AI & Data Science",
  },
  BCY: {
    key: "cyber",
    department: "CSE WITH SPECIALISATION IN CYBER SECURITY",
    short: "Cyber Security",
  },
  BEC: { key: "ece", department: "ELECTRONICS AND COMMUNICATION ENGINEERING", short: "ECE" },
} as const;

export type BranchCode = keyof typeof BRANCHES;

const ROMAN = ["I", "II", "III", "IV", "V"];

export type ParsedRoll = {
  admissionYear: number;
  branchCode: BranchCode;
  serial: number;
  department: string;
  shortDepartment: string;
  batchNo: number;
  /** Roman label, matching how the timetable writes its sections. */
  section: string;
};

// Institute addresses carry the same roll number the card does —
// "asharani24bcs86@iiitkottayam.ac.in" is 2024BCS0086. The serial isn't
// zero-padded there ("86", "0142"), so compare it as a number. Returns null
// for anything off-pattern, including the orion-test-* accounts, so callers
// must treat "can't tell" as "don't complain".
export function rollFromEmail(email: string | null | undefined): ParsedRoll | null {
  const m = /^[a-z.]+?(\d{2})(b[a-z]{2})(\d{1,4})@iiitkottayam\.ac\.in$/i.exec(
    (email ?? "").trim().toLowerCase(),
  );
  const [, yy, branch, serial] = m ?? [];
  if (!yy || !branch || !serial) return null;
  return parseRoll(`20${yy}${branch.toUpperCase()}${serial.padStart(4, "0")}`);
}

/** True only when both are readable AND they disagree — never on a maybe. */
export function rollContradictsEmail(
  roll: string | null | undefined,
  email: string | null | undefined,
): boolean {
  const typed = parseRoll(roll);
  const fromEmail = rollFromEmail(email);
  if (!typed || !fromEmail) return false;
  return typed.branchCode !== fromEmail.branchCode || typed.serial !== fromEmail.serial;
}

export function parseRoll(roll: string | null | undefined): ParsedRoll | null {
  const m = /^(20\d{2})(B[A-Z]{2})(\d{1,4})$/.exec((roll ?? "").trim().toUpperCase());
  if (!m) return null;
  const branch = BRANCHES[m[2] as BranchCode];
  if (!branch) return null;

  const serial = Number(m[3]);
  const batchNo = (serial % 4) + 1;
  return {
    admissionYear: Number(m[1]),
    branchCode: m[2] as BranchCode,
    serial,
    department: branch.department,
    shortDepartment: branch.short,
    batchNo,
    section: ROMAN[batchNo - 1] ?? String(batchNo),
  };
}
