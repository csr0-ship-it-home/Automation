/**
 * Office Script: Get Reminders
 *
 * Called daily by the "Trade Error - Compliance Reminders" Power Automate flow.
 * If a compliance meeting is within "Reminder days before meeting" days and hasn't had
 * reminders yet, it returns one email per person with Open trade errors plus a summary
 * email for the compliance team, and records that the reminders went out.
 * On any other day it returns an empty list, so the flow sends nothing.
 *
 * Set sendNow = true (from a manual flow) to send reminders immediately regardless of date.
 */

interface Email {
  to: string;
  subject: string;
  body: string;
}

interface ReminderRun {
  meetingDate: string;
  peopleReminded: number;
  emails: Email[];
}

interface OpenError {
  rowIndex: number;
  email: string;
  name: string;
  errorDate: number | string;
  account: string;
  note: string;
  remindersSent: number;
  status: string;
}

const CLOSED_STATUSES = ["submitted", "waived"];
const EXCEL_EPOCH = Date.UTC(1899, 11, 30);
const MS_PER_DAY = 86400000;

function main(workbook: ExcelScript.Workbook, today: string, sendNow?: boolean): ReminderRun {
  const todaySerial = Math.floor(parseDate(today));
  if (isNaN(todaySerial)) throw new Error('"today" must look like 2026-09-29, got: ' + today);

  const tracker = workbook.getTable("TradeErrors");
  const meetings = workbook.getTable("Meetings");
  if (!tracker || !meetings) throw new Error("TradeErrors / Meetings table not found. Run the Setup script first.");

  const firm = getSetting(workbook, "Firm name");
  const formUrl = getSetting(workbook, "Compliance form URL");
  const complianceTo = getSetting(workbook, "Compliance team emails");
  const daysBefore = Number(getSetting(workbook, "Reminder days before meeting")) || 7;

  // 1. Which meeting are we reminding for?
  const meetingBody = meetings.getRangeBetweenHeaderAndTotal();
  const meetingRows = meetingBody.getValues()
    .map((r, i) => ({ index: i, date: toSerial(r[0]), sentOn: r[1] }))
    .filter(m => !isNaN(m.date) && m.date >= todaySerial)
    .sort((a, b) => a.date - b.date);

  const due = sendNow
    ? meetingRows[0]
    : meetingRows.find(m => m.sentOn === "" && m.date - todaySerial <= daysBefore);
  if (!due && !sendNow) return { meetingDate: "", peopleReminded: 0, emails: [] };
  const meetingText = due ? serialToText(due.date) : "the upcoming compliance meeting";

  // 2. Who still owes a compliance form?
  const trackerBody = tracker.getRangeBetweenHeaderAndTotal();
  const headers = tracker.getHeaderRowRange().getValues()[0].map(h => String(h).trim());
  const col = (name: string) => headers.indexOf(name);
  const open: OpenError[] = trackerBody.getValues()
    .map((r, i) => ({
      rowIndex: i,
      email: String(r[col("Email")]).trim().toLowerCase(),
      name: String(r[col("Name")]).trim(),
      errorDate: r[col("Error Date")] as number | string,
      account: String(r[col("Account / Ticker")]).trim(),
      note: String(r[col("Note")]).trim(),
      remindersSent: Number(r[col("Reminders Sent")]) || 0,
      status: String(r[col("Status")]).trim().toLowerCase(),
    }))
    .filter(e => e.email !== "" && CLOSED_STATUSES.indexOf(e.status) === -1);

  const byPerson: { [email: string]: OpenError[] } = {};
  open.forEach(e => {
    if (!byPerson[e.email]) byPerson[e.email] = [];
    byPerson[e.email].push(e);
  });

  // 3. Build the emails and record that reminders went out.
  const emails: Email[] = [];
  Object.keys(byPerson).forEach(email => {
    const items = byPerson[email];
    const list = items.map(e =>
      "<li>" + esc(dateText(e.errorDate)) + (e.account ? " - " + esc(e.account) : "") +
      (e.note ? " - " + esc(e.note) : "") + "</li>").join("");
    emails.push({
      to: email,
      subject: "Reminder: compliance form due before the " + meetingText + " compliance meeting",
      body:
        "<p>Hi " + esc(items[0].name) + ",</p>" +
        "<p>Our compliance meeting is on <b>" + esc(meetingText) + "</b>. You still have " +
        (items.length === 1 ? "a trade error" : items.length + " trade errors") +
        " without a completed compliance form:</p><ul>" + list + "</ul>" +
        '<p><a href="' + esc(formUrl) + '">Complete the compliance form</a> (about 15 minutes).</p>' +
        "<p>Already done? Reply to this email and compliance will update the tracker.</p>" +
        "<p>- " + esc(firm) + " Compliance</p>",
    });
    items.forEach(e => {
      trackerBody.getCell(e.rowIndex, col("Reminders Sent")).setValue(e.remindersSent + 1);
      trackerBody.getCell(e.rowIndex, col("Last Reminder")).setValue(todaySerial);
    });
  });

  if (complianceTo) emails.push(summaryEmail(open, meetingText, todaySerial, complianceTo));

  if (due && !sendNow) {
    meetingBody.getCell(due.index, 1).setValue(todaySerial);
    meetingBody.getCell(due.index, 2).setValue(Object.keys(byPerson).length);
  }

  return { meetingDate: meetingText, peopleReminded: Object.keys(byPerson).length, emails: emails };
}

function summaryEmail(open: OpenError[], meetingText: string, todaySerial: number, to: string): Email {
  if (open.length === 0) {
    return {
      to: to,
      subject: "Trade error forms: all clear before " + meetingText,
      body: "<p>Every logged trade error has a completed compliance form ahead of " + esc(meetingText) + ".</p>",
    };
  }
  const rows = open
    .slice()
    .sort((a, b) => toSerial(a.errorDate) - toSerial(b.errorDate))
    .map(e => {
      const d = toSerial(e.errorDate);
      return "<tr><td>" + esc(e.name) + "</td><td>" + esc(e.email) + "</td><td>" + esc(dateText(e.errorDate)) +
        "</td><td>" + esc(e.account) + '</td><td style="text-align:right">' +
        (isNaN(d) ? "" : String(todaySerial - Math.floor(d))) + "</td></tr>";
    })
    .join("");
  return {
    to: to,
    subject: "Outstanding trade error forms: " + open.length + " open before " + meetingText,
    body:
      "<p>" + open.length + " trade error(s) still need a compliance form before " + esc(meetingText) +
      ". Each person below has been emailed a reminder.</p>" +
      '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse">' +
      "<tr><th>Name</th><th>Email</th><th>Error date</th><th>Account / ticker</th><th>Days open</th></tr>" +
      rows + "</table>",
  };
}

function getSetting(workbook: ExcelScript.Workbook, name: string): string {
  const table = workbook.getTable("Settings");
  if (!table) return "";
  const row = table.getRangeBetweenHeaderAndTotal().getValues().find(r => String(r[0]).trim() === name);
  return row ? String(row[1]).trim() : "";
}

/** Cell value (Excel serial number or date text) -> serial, NaN if blank/unrecognised. */
function toSerial(value: string | number | boolean): number {
  if (typeof value === "number") return value;
  return parseDate(String(value));
}

/** "2026-09-29", "2026-09-29T14:05:00Z" or "9/29/2026" -> Excel serial (NaN if unrecognised). */
function parseDate(text: string): number {
  const s = String(text || "").trim();
  let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return (Date.UTC(+m[1], +m[2] - 1, +m[3]) - EXCEL_EPOCH) / MS_PER_DAY;
  m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (m) return (Date.UTC(+m[3], +m[1] - 1, +m[2]) - EXCEL_EPOCH) / MS_PER_DAY;
  return NaN;
}

function dateText(value: number | string): string {
  const serial = toSerial(value);
  return isNaN(serial) ? String(value) : serialToText(serial);
}

function serialToText(serial: number): string {
  const d = new Date(EXCEL_EPOCH + Math.floor(serial) * MS_PER_DAY);
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return days[d.getUTCDay()] + ", " + months[d.getUTCMonth()] + " " + d.getUTCDate() + ", " + d.getUTCFullYear();
}

function esc(s: string): string {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
