/**
 * Office Script: Log Trade Error
 *
 * Called by the "Trade Error - Quick Log" Power Automate flow for each Microsoft Forms response.
 * Adds a row to the TradeErrors table with Status = Open, and returns the confirmation
 * email (to / subject / body) for the flow's "Send an email" step.
 */

interface Email {
  to: string;
  subject: string;
  body: string;
}

const EXCEL_EPOCH = Date.UTC(1899, 11, 30);
const MS_PER_DAY = 86400000;

function main(
  workbook: ExcelScript.Workbook,
  email: string,
  name: string,
  errorDate: string,
  loggedAt: string,
  account?: string,
  note?: string,
  custodian?: string
): Email {
  const table = workbook.getTable("TradeErrors");
  if (!table) throw new Error("TradeErrors table not found. Run the Setup script first.");

  const errorSerial = parseDate(errorDate);
  const loggedSerial = parseDate(loggedAt);
  const fields: { [header: string]: string | number } = {
    "Logged At": isNaN(loggedSerial) ? loggedAt || "" : loggedSerial,
    "Email": (email || "").trim().toLowerCase(),
    "Name": (name || "").trim(),
    "Error Date": isNaN(errorSerial) ? errorDate || "" : errorSerial,
    "Account / Ticker": (account || "").trim(),
    "Note": (note || "").trim(),
    "Custodian": (custodian || "").trim(),
    "Status": "Open",
    "Reminders Sent": 0,
  };
  const headers = table.getHeaderRowRange().getValues()[0].map(h => String(h));
  appendRow(table, headers.map(h => (h in fields ? fields[h] : "")));

  const firm = getSetting(workbook, "Firm name");
  const formUrl = getSetting(workbook, "Compliance form URL");
  const daysBefore = Number(getSetting(workbook, "Reminder days before meeting")) || 7;
  const dateText = isNaN(errorSerial) ? errorDate : serialToText(errorSerial);

  return {
    to: fields["Email"] as string,
    subject: firm + ": trade error logged (" + dateText + "), full compliance form still needed",
    body:
      "<p>Hi " + esc(fields["Name"] as string) + ",</p>" +
      "<p>Thanks for logging your trade error from <b>" + esc(dateText) + "</b>. " +
      "Please complete the full compliance form when you have 15 minutes:</p>" +
      '<p><a href="' + esc(formUrl) + '">Open the compliance form</a></p>' +
      "<p>If it's still outstanding, you'll get a reminder " + daysBefore +
      " days before the next compliance meeting.</p>",
  };
}

/** Writes into the table's single blank starter row if present, otherwise adds a row. */
function appendRow(table: ExcelScript.Table, row: (string | number)[]) {
  const body = table.getRangeBetweenHeaderAndTotal();
  const values = body.getValues();
  if (values.length === 1 && values[0].every(v => v === "")) {
    body.setValues([row]);
  } else {
    table.addRow(-1, row);
  }
}

function getSetting(workbook: ExcelScript.Workbook, name: string): string {
  const table = workbook.getTable("Settings");
  if (!table) return "";
  const row = table.getRangeBetweenHeaderAndTotal().getValues().find(r => String(r[0]).trim() === name);
  return row ? String(row[1]).trim() : "";
}

/** "2026-09-29", "2026-09-29 14:05", "2026-09-29T14:05:00Z" or "9/29/2026" -> Excel serial (NaN if unrecognised). */
function parseDate(text: string): number {
  const s = String(text || "").trim();
  let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}):(\d{2}))?/);
  if (m) {
    const day = (Date.UTC(+m[1], +m[2] - 1, +m[3]) - EXCEL_EPOCH) / MS_PER_DAY;
    return m[4] ? day + (+m[4] * 60 + +m[5]) / 1440 : day;
  }
  m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (m) return (Date.UTC(+m[3], +m[1] - 1, +m[2]) - EXCEL_EPOCH) / MS_PER_DAY;
  return NaN;
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
