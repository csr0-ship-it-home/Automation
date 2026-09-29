# Trade Error Quick Log + Compliance Reminders

**The problem:** the full compliance form for a trade error takes about 15 minutes, so people put it off, forget, and
the week before the monthly compliance call turns into tracking down who made which error.

**The fix:** split it into two steps.

1. **Quick log (10 seconds):** right after the error, the person opens a bookmarked Google Form and enters their name,
   the date of the error, and optionally an account/ticker and a short note. Their email is captured automatically.
2. **Full compliance form (later):** every quick log stays **Open** in a Google Sheet until compliance marks it
   **Submitted**.
3. **Automatic chase:** 7 days before each compliance meeting, everyone with an Open entry gets a reminder email
   listing their errors and linking to the full form. The compliance team gets one summary email showing who is
   still outstanding and how many days each item has been open.

Nobody has to remember anything, and the tracker already shows who needs to be chased.

## What you get

| Piece | Purpose |
|---|---|
| **Quick-log Google Form** | Created for you by `setup()`. Share the link in Teams/Slack, bookmark it, or add it to the trade blotter. |
| **`Trade Errors` tab** | One row per logged error. Status: `Open` / `Submitted` / `Waived`. Open rows are highlighted red. Also tracks reminder count and the last reminder date. |
| **`Meetings` tab** | Compliance meeting dates. Pre-filled for the next 12 months from a rule (default: 2nd Tuesday). Edit the dates as needed. Shows when reminders went out and to how many people. |
| **Instant confirmation** | After someone logs an error, the form's thank-you screen and a confirmation email both link to the full compliance form, so people who have time can do it immediately. |
| **Daily check (8am)** | Sends reminders once per meeting, as soon as the meeting is ≤ 7 days away. If a day is missed, it catches up on the next run. |
| **`Trade Errors` menu** | *Mark selected rows as Submitted*, *Send reminders now*, *Show quick-log form link*. |

## Setup (about 10 minutes, one time)

1. Create a new Google Sheet in the compliance team's shared drive, e.g. "Trade Error Tracker".
2. Open **Extensions → Apps Script**.
3. Replace the contents of `Code.gs` with [`Code.gs`](./Code.gs) from this folder.
4. Optional: in **Project Settings**, tick *Show "appsscript.json"* and paste in [`appsscript.json`](./appsscript.json).
   Set `timeZone` to your office's time zone. If you skip this step, set the time zone under Project Settings instead.
5. Edit the `CONFIG` block at the top of `Code.gs`:
   - `COMPLIANCE_FORM_URL`: link to your existing full compliance form
   - `COMPLIANCE_TEAM_EMAILS`: who should receive the outstanding summary
   - `MEETING_RULE`: e.g. `{ nth: 2, weekday: 'Tuesday' }`, `{ nth: -1, weekday: 'Friday' }` (last Friday), or `null`
     if you want to type the dates in yourself
   - `REMINDER_DAYS_BEFORE`: defaults to `7`
6. Pick `setup` from the function dropdown and click **Run**. Approve the permissions prompt. The script needs to
   create the form, edit this sheet, and send email as you.
7. Go back to the Sheet. A popup shows the **quick-log form link**. Share that link with the desk.
8. Check the **Meetings** tab and adjust any dates that don't follow the rule (holidays, moved meetings).

`setup` is safe to run again. It reuses the existing form and replaces the triggers instead of duplicating them.

## Day-to-day use

- **Traders / ops:** made an error? Open the bookmark, fill in 3 fields, done. Do the full form when you have time.
- **Compliance:** when a full form comes in, select the matching row(s) and choose
  **Trade Errors → Mark selected rows as Submitted**. You can also change the Status dropdown directly. Use `Waived`
  for entries that don't need a form (duplicates, logged by mistake).
- **Before the meeting:** nothing to do. The reminder emails and your summary go out automatically 7 days before.
  To send a second nudge, use **Trade Errors → Send reminders now**.

## Notes

- Emails are sent from the account that ran `setup`. Use a compliance team account or shared mailbox owner if you
  can. Google Workspace allows about 1,500 emails per day, far more than this needs.
- The form collects **verified** email addresses, so people must be signed in to Google. On Google Workspace you
  can also limit the form to your domain under the form's *Settings → Responses*.
- Columns are looked up by header name. You can reorder or add columns to the `Trade Errors` tab, but keep the
  existing header names.
- **On Microsoft 365 instead of Google?** See [`../trade-error-tracker-excel`](../trade-error-tracker-excel) for the Excel + Power Automate version.
