/**
 * Office Script: Setup Trade Error Tracker
 *
 * Run once from Excel on the web (Automate tab). Creates three tabs:
 *   - Settings:     form link, compliance team emails, days-before-meeting
 *   - Trade Errors: the TradeErrors table (one row per logged error)
 *   - Meetings:     compliance meeting dates, pre-filled from the rule below
 * Safe to re-run: anything that already exists is left alone.
 */

// Pre-fill rule for the Meetings tab. Example: 2nd Tuesday of every month.
// MEETING_NTH: 1-4, or -1 for "last". Set MEETINGS_TO_PREFILL to 0 to type dates by hand.
const MEETING_NTH = 2;
const MEETING_WEEKDAY = "Tuesday";
const MEETINGS_TO_PREFILL = 12;

const TRACKER_HEADERS = [
  "Logged At", "Email", "Name", "Error Date", "Account / Ticker", "Note",
  "Status", "Completed On", "Reminders Sent", "Last Reminder",
];
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const EXCEL_EPOCH = Date.UTC(1899, 11, 30);
const MS_PER_DAY = 86400000;

function main(workbook: ExcelScript.Workbook) {
  setupSettings(workbook);
  setupTracker(workbook);
  setupMeetings(workbook);
  getOrAddSheet(workbook, "Trade Errors").activate();
  console.log("Setup complete. Fill in the Settings tab and check the dates on the Meetings tab.");
}

function setupSettings(workbook: ExcelScript.Workbook) {
  if (workbook.getTable("Settings")) return;
  const sheet = getOrAddSheet(workbook, "Settings");
  const rows: (string | number)[][] = [
    ["Setting", "Value"],
    ["Firm name", "Your Firm"],
    ["Compliance form URL", "https://example.com/your-full-compliance-form"],
    ["Compliance team emails", "compliance@yourfirm.com"],
    ["Reminder days before meeting", 7],
  ];
  const range = sheet.getRange("A1:B5");
  range.setValues(rows);
  workbook.addTable(range, true).setName("Settings");
  sheet.getRange("A:A").getFormat().setColumnWidth(200);
  sheet.getRange("B:B").getFormat().setColumnWidth(420);
  sheet.getRange("D1").setValue("Separate multiple compliance emails with a semicolon ( ; )");
}

function setupTracker(workbook: ExcelScript.Workbook) {
  if (workbook.getTable("TradeErrors")) return;
  const sheet = getOrAddSheet(workbook, "Trade Errors");
  const header = sheet.getRange("A1:J1");
  header.setValues([TRACKER_HEADERS]);
  workbook.addTable(header, true).setName("TradeErrors");

  // Status dropdown (column G) and red highlight for Open rows.
  sheet.getRange("G2:G10000").getDataValidation().setRule({
    list: { inCellDropDown: true, source: "Open,Submitted,Waived" },
  });
  const highlight = sheet.getRange("A2:J10000").addConditionalFormat(ExcelScript.ConditionalFormatType.custom);
  highlight.getCustom().getRule().setFormula('=$G2="Open"');
  highlight.getCustom().getFormat().getFill().setColor("#FCE8E6");

  sheet.getRange("A:A").setNumberFormat("yyyy-mm-dd hh:mm");
  sheet.getRange("D:D").setNumberFormat("yyyy-mm-dd");
  sheet.getRange("H:H").setNumberFormat("yyyy-mm-dd");
  sheet.getRange("J:J").setNumberFormat("yyyy-mm-dd");
  sheet.getRange("A:J").getFormat().setColumnWidth(130);
  sheet.getRange("F:F").getFormat().setColumnWidth(260);
  sheet.getFreezePanes().freezeRows(1);
}

function setupMeetings(workbook: ExcelScript.Workbook) {
  if (workbook.getTable("Meetings")) return;
  const sheet = getOrAddSheet(workbook, "Meetings");
  const now = new Date();
  const today = toSerial(now.getFullYear(), now.getMonth() + 1, now.getDate());
  const dates = MEETINGS_TO_PREFILL > 0 ? upcomingMeetings(today, MEETING_NTH, MEETING_WEEKDAY, MEETINGS_TO_PREFILL) : [];

  const rows: (string | number)[][] = [["Meeting Date", "Reminders Sent On", "People Reminded"]];
  dates.forEach(d => rows.push([d, "", ""]));
  if (rows.length === 1) rows.push(["", "", ""]);

  const range = sheet.getRange("A1:C" + rows.length);
  range.setValues(rows);
  workbook.addTable(range, true).setName("Meetings");
  sheet.getRange("A:B").setNumberFormat("ddd yyyy-mm-dd");
  sheet.getRange("A:C").getFormat().setColumnWidth(160);
  sheet.getFreezePanes().freezeRows(1);
}

function getOrAddSheet(workbook: ExcelScript.Workbook, name: string): ExcelScript.Worksheet {
  const existing = workbook.getWorksheet(name);
  if (existing) return existing;
  // Reuse the default blank "Sheet1" for the first tab we create.
  const blank = workbook.getWorksheet("Sheet1");
  const used = blank ? blank.getUsedRange(true) : undefined;
  if (blank && (!used || (used.getCellCount() === 1 && used.getValue() === ""))) {
    blank.setName(name);
    return blank;
  }
  return workbook.addWorksheet(name);
}

/** Next `count` meeting dates (Excel serials) on or after `fromSerial`. */
function upcomingMeetings(fromSerial: number, nth: number, weekdayName: string, count: number): number[] {
  const weekday = WEEKDAYS.indexOf(weekdayName);
  if (weekday === -1) throw new Error('MEETING_WEEKDAY must be a full day name, e.g. "Tuesday".');
  const from = new Date(EXCEL_EPOCH + fromSerial * MS_PER_DAY);
  const dates: number[] = [];
  for (let m = 0; dates.length < count && m < count + 2; m++) {
    const year = from.getUTCFullYear();
    const month = from.getUTCMonth() + m;
    let d: Date;
    if (nth === -1) {
      d = new Date(Date.UTC(year, month + 1, 0));
      d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() - weekday + 7) % 7));
    } else {
      d = new Date(Date.UTC(year, month, 1));
      d.setUTCDate(1 + ((weekday - d.getUTCDay() + 7) % 7) + (nth - 1) * 7);
    }
    const serial = (d.getTime() - EXCEL_EPOCH) / MS_PER_DAY;
    if (serial >= fromSerial) dates.push(serial);
  }
  return dates;
}

function toSerial(y: number, m: number, d: number): number {
  return (Date.UTC(y, m - 1, d) - EXCEL_EPOCH) / MS_PER_DAY;
}
