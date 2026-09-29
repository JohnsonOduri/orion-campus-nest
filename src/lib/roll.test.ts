import { describe, expect, it } from "vitest";
import { parseRoll, rollContradictsEmail, rollFromEmail } from "./roll";

// These are the institute's rules as stated by the Academic Office, and the
// same ones orion_parse_roll() enforces server-side. If a rule changes, both
// have to change together.
describe("parseRoll", () => {
  it("maps each branch code to its department", () => {
    expect(parseRoll("2024BCS0086")?.shortDepartment).toBe("CSE");
    expect(parseRoll("2024BCD0054")?.shortDepartment).toBe("AI & Data Science");
    expect(parseRoll("2024BCY0022")?.shortDepartment).toBe("Cyber Security");
    expect(parseRoll("2024BEC0014")?.shortDepartment).toBe("ECE");
  });

  it("derives the batch from serial % 4, counting from 1", () => {
    // remainder 0 -> batch 1, 1 -> 2, 2 -> 3, 3 -> 4
    expect(parseRoll("2024BCS0088")?.batchNo).toBe(1); // 88 % 4 = 0
    expect(parseRoll("2024BCS0089")?.batchNo).toBe(2); // 89 % 4 = 1
    expect(parseRoll("2024BCS0086")?.batchNo).toBe(3); // 86 % 4 = 2
    expect(parseRoll("2024BCS0087")?.batchNo).toBe(4); // 87 % 4 = 3
  });

  it("writes the section the way the timetable does (roman)", () => {
    expect(parseRoll("2024BCS0088")?.section).toBe("I");
    expect(parseRoll("2024BCS0089")?.section).toBe("II");
    expect(parseRoll("2024BCS0086")?.section).toBe("III");
    expect(parseRoll("2024BCS0087")?.section).toBe("IV");
  });

  it("reads the admission year from the prefix", () => {
    expect(parseRoll("2024BCS0086")?.admissionYear).toBe(2024);
    expect(parseRoll("2026BEC0001")?.admissionYear).toBe(2026);
  });

  it("accepts lowercase and surrounding whitespace", () => {
    expect(parseRoll("  2024bcd0054 ")?.shortDepartment).toBe("AI & Data Science");
  });

  it("returns null for anything it cannot read, so the form falls back to asking", () => {
    expect(parseRoll("")).toBeNull();
    expect(parseRoll(null)).toBeNull();
    expect(parseRoll("NOTAROLL")).toBeNull();
    expect(parseRoll("2024BXX0001")).toBeNull(); // unknown branch code
    expect(parseRoll("1999BCS0001")).toBeNull(); // not a 20xx year
  });
});

describe("rollFromEmail", () => {
  it("reads the roll number out of an institute address", () => {
    // the serial isn't zero-padded in the address
    expect(rollFromEmail("asharani24bcs86@iiitkottayam.ac.in")?.branchCode).toBe("BCS");
    expect(rollFromEmail("asharani24bcs86@iiitkottayam.ac.in")?.serial).toBe(86);
    expect(rollFromEmail("ravikumar24bcs0142@iiitkottayam.ac.in")?.serial).toBe(142);
    expect(rollFromEmail("nehasingh24bcd17@iiitkottayam.ac.in")?.shortDepartment).toBe(
      "AI & Data Science",
    );
  });

  it("gives up on addresses that don't carry one", () => {
    expect(rollFromEmail("orion-test-student-a@iiitkottayam.ac.in")).toBeNull();
    expect(rollFromEmail("campus.admin@gmail.com")).toBeNull();
    expect(rollFromEmail(null)).toBeNull();
  });
});

describe("rollContradictsEmail", () => {
  it("catches a mistyped branch code", () => {
    // real case: typed BCD (AI&DS) while the address says BCS (CSE)
    expect(rollContradictsEmail("2024BCD0054", "asharani24bcs86@iiitkottayam.ac.in")).toBe(
      true,
    );
  });

  it("is quiet when they agree, padding differences included", () => {
    expect(rollContradictsEmail("2024BCS0086", "asharani24bcs86@iiitkottayam.ac.in")).toBe(
      false,
    );
    expect(rollContradictsEmail("2024BCS0142", "ravikumar24bcs0142@iiitkottayam.ac.in")).toBe(
      false,
    );
  });

  it("never complains when either side is unreadable", () => {
    expect(rollContradictsEmail("2024BCS0086", "orion-test-student-a@iiitkottayam.ac.in")).toBe(
      false,
    );
    expect(rollContradictsEmail("NOTAROLL", "asharani24bcs86@iiitkottayam.ac.in")).toBe(false);
    expect(rollContradictsEmail(null, null)).toBe(false);
  });
});

// Faculty and admins share the institute domain but their addresses are
// name-based (checked against the live directory: 0 of 125 faculty addresses
// look like a roll number), and some students' addresses were renamed and no
// longer carry one either. None of them may be blocked, warned at, or have
// anything inferred about them — "can't tell" must always mean "stay quiet".
describe("identities that carry no roll number", () => {
  const NON_STUDENT_EMAILS = [
    "amenon@iiitkottayam.ac.in", // faculty
    "rkrishnan@iiitkottayam.ac.in", // faculty
    "sdesai@iiitkottayam.ac.in", // faculty
    "campus.admin@gmail.com", // admin, not even the institute domain
    "orion-test-admin@iiitkottayam.ac.in", // admin on the institute domain
    "orion-test-student-a@iiitkottayam.ac.in", // student, renamed address
    "john.doe@iiitkottayam.ac.in", // student, renamed address
  ];

  it("reads no roll number out of them", () => {
    for (const email of NON_STUDENT_EMAILS) {
      expect(rollFromEmail(email), email).toBeNull();
    }
  });

  it("raises no mismatch warning for them, whatever roll is typed", () => {
    for (const email of NON_STUDENT_EMAILS) {
      expect(rollContradictsEmail("2024BCS0086", email), email).toBe(false);
      expect(rollContradictsEmail("2024BCD0054", email), email).toBe(false);
      expect(rollContradictsEmail("MT24CS001", email), email).toBe(false);
      expect(rollContradictsEmail("", email), email).toBe(false);
    }
  });

  it("leaves a non-standard roll number to the dropdowns instead of guessing", () => {
    // M.Tech/PhD and legacy formats don't follow the B.Tech pattern; the form
    // falls back to asking, and complete_registration keeps what was picked.
    expect(parseRoll("MT24CS001")).toBeNull();
    expect(parseRoll("PHD2024001")).toBeNull();
    expect(parseRoll("24BCS0086")).toBeNull(); // no 20xx prefix
  });
});

// The server re-derives everything with orion_parse_roll(), so if these two
// ever disagree the student is shown one class and registered into another.
// Expectations below were captured from the live SQL function, not written by
// hand — regenerate them from the database if the rule changes.
describe("parity with orion_parse_roll() in SQL", () => {
  const FROM_SQL: Record<
    string,
    { dept: string; batch: number; sec: string; year: number } | null
  > = {
    "2024BCS0086": { dept: "COMPUTER SCIENCE AND ENGINEERING", batch: 3, sec: "III", year: 2024 },
    "2024BCD0054": {
      dept: "CSE WITH SPECIALISATION IN AI AND DATA SCIENCE",
      batch: 3,
      sec: "III",
      year: 2024,
    },
    "2024BCY0022": {
      dept: "CSE WITH SPECIALISATION IN CYBER SECURITY",
      batch: 3,
      sec: "III",
      year: 2024,
    },
    "2024BEC0014": {
      dept: "ELECTRONICS AND COMMUNICATION ENGINEERING",
      batch: 3,
      sec: "III",
      year: 2024,
    },
    "2024BCS0088": { dept: "COMPUTER SCIENCE AND ENGINEERING", batch: 1, sec: "I", year: 2024 },
    "2024BCS0089": { dept: "COMPUTER SCIENCE AND ENGINEERING", batch: 2, sec: "II", year: 2024 },
    "2024BCS0087": { dept: "COMPUTER SCIENCE AND ENGINEERING", batch: 4, sec: "IV", year: 2024 },
    "2024BCS86": { dept: "COMPUTER SCIENCE AND ENGINEERING", batch: 3, sec: "III", year: 2024 },
    "2026BEC0001": {
      dept: "ELECTRONICS AND COMMUNICATION ENGINEERING",
      batch: 2,
      sec: "II",
      year: 2026,
    },
    "  2024bcd0054 ": {
      dept: "CSE WITH SPECIALISATION IN AI AND DATA SCIENCE",
      batch: 3,
      sec: "III",
      year: 2024,
    },
    "2024BXX0001": null,
    MT24CS001: null,
    "24BCS0086": null,
    "1999BCS0001": null,
    "": null,
  };

  it("agrees with the database on every case", () => {
    for (const [roll, expected] of Object.entries(FROM_SQL)) {
      const got = parseRoll(roll);
      if (expected === null) {
        expect(got, roll).toBeNull();
      } else {
        expect(
          {
            dept: got?.department,
            batch: got?.batchNo,
            sec: got?.section,
            year: got?.admissionYear,
          },
          roll,
        ).toEqual(expected);
      }
    }
  });
});
