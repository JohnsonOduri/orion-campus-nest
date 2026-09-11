import { createFileRoute } from "@tanstack/react-router";

import {
  getNextClass,
  getTodayTimetable,
  getTimetable,
  getWeekTimetable,
} from "@/lib/timetable-api";

/**
 * REST surface for the timetable vertical slice:
 *
 *   GET /api/timetable            full valid timetable for the student context
 *   GET /api/timetable/today      today's entries
 *   GET /api/timetable/week       current week's entries
 *   GET /api/timetable/next       next class (?include_activities=true to opt in)
 *
 * Identity/academic context is resolved server-side (orion_student_context);
 * no client-supplied user ids are honored. When Supabase is not configured
 * the endpoints degrade to a clearly-flagged demo mode.
 */
export const Route = createFileRoute("/api/timetable/$")({
  server: {
    handlers: {
      GET: async ({ request, params }) => {
        const url = new URL(request.url);
        const path = params._splat ?? "";
        try {
          let payload: unknown;
          switch (path) {
            case "": {
              payload = await getTimetable();
              break;
            }
            case "today": {
              payload = await getTodayTimetable();
              break;
            }
            case "week": {
              payload = await getWeekTimetable();
              break;
            }
            case "next": {
              payload = await getNextClass({
                data: {
                  include_activities: url.searchParams.get("include_activities") === "true",
                },
              });
              break;
            }
            default:
              payload = { error: `unknown timetable resource: ${path}` };
              return Response.json(payload, { status: 404 });
          }
          return Response.json(payload);
        } catch (error) {
          console.error("[api/timetable]", error);
          return Response.json({ error: "timetable service unavailable" }, { status: 503 });
        }
      },
    },
  },
});

// keep the imported functions referenced (tree-shaking guard for the route's
// handler closure above); TS complains otherwise in some configs.
void getTimetable;
void getTodayTimetable;
void getWeekTimetable;
void getNextClass;
