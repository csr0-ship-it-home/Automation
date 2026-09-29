/**
 * Trade Error Quick Log + Compliance Reminders
 *
 * A 10-second Google Form lets anyone log "I made a trade error on this date".
 * Every entry lands in this spreadsheet with status "Open" until the full
 * compliance form is done. A week before each compliance meeting, everyone
 * with an open entry gets a reminder email, and the compliance team gets a
 * summary of who is still outstanding.
 *
 * Setup: see README.md. In short, edit CONFIG below, then run `setup` once.
 */

// ---------------------------------------------------------------------------
// CONFIG — edit these before running setup()
// ---------------------------------------------------------------------------
const CONFIG = {
  FIRM_NAME: 'Your Firm',

  // Link to the full (15-minute) compliance trade error form.
  COMPLIANCE_FORM_URL: 'https://example.com/your-full-compliance-form',

  // Who receives the pre-meeting summary of outstanding forms.
  COMPLIANCE_TEAM_EMAILS: ['compliance@yourfirm.com'],

  // How many days before each compliance meeting to send reminders.
  REMINDER_DAYS_BEFORE: 7,

  // Hour of day (0-23, script time zone) the daily check runs.
  DAILY_CHECK_HOUR: 8,

  // Send the person a "thanks, here's the full form link" email right after they log.
  SEND_CONFIRMATION_ON_LOG: true,

  // Used to pre-fill the Meetings tab. Example: 2nd Tuesday of each month.
  // nth: 1-4, or -1 for "last". Set to null to enter meeting dates by hand.
  MEETING_RULE: { nth: 2, weekday: 'Tuesday' },
  MEETINGS_TO_PREFILL: 12,
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const TRACKER_SHEET = 'Trade Errors';
const MEETINGS_SHEET = 'Meetings';

const COL = {
  TIMESTAMP: 'Timestamp',
  EMAIL: 'Email Address',
  NAME: 'Your name',
  ERROR_DATE: 'Date of the trade error',
  ACCOUNT: 'Account / ticker (optional)',
  NOTE: 'Quick note (optional)',
  STATUS: 'Status',
  COMPLETED_ON: 'Compliance Form Completed On',
  REMINDERS_SENT: 'Reminders Sent',
  LAST_REMINDER: 'Last Reminder',
};
const TRACKING_COLUMNS = [COL.STATUS, COL.COMPLETED_ON, COL.REMINDERS_SENT, COL.LAST_REMINDER];

const STATUS_OPEN = 'Open';
const STATUS_SUBMITTED = 'Submitted';
const STATUS_WAIVED = 'Waived';
const CLOSED_STATUSES = [STATUS_SUBMITTED, STATUS_WAIVED];

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MS_PER_DAY = 24 * 60 * 60 * 1000;

// ---------------------------------------------------------------------------
// One-time setup
// ---------------------------------------------------------------------------
function setup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const props = PropertiesService.getScriptProperties();
  ss.setSpreadsheetTimeZone(Session.getScriptTimeZone());

  // 1. Quick-log form, linked to this spreadsheet.
  let form;
  const formId = props.getProperty('FORM_ID');
  if (formId) {
    form = FormApp.openById(formId);
  } else {
    form = createQuickLogForm_();
    form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());
    props.setProperty('FORM_ID', form.getId());
    SpreadsheetApp.flush();
  }

  // 2. Tracker sheet (the form's response sheet) + tracking columns.
  const tracker = findTrackerSheet_(ss);
  if (!tracker) {
    throw new Error('Could not find the form response sheet yet. Wait a few seconds and run setup again.');
  }
  tracker.setName(TRACKER_SHEET);
  addTrackingColumns_(tracker);

  // 3. Meetings sheet.
  setupMeetingsSheet_(ss);

  // 4. Triggers (replace any existing ones so setup is safe to re-run).
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('onTradeErrorLogged').forSpreadsheet(ss).onFormSubmit().create();
  ScriptApp.newTrigger('dailyReminderCheck').timeBased().everyDays(1).atHour(CONFIG.DAILY_CHECK_HOUR).create();

  const url = form.getPublishedUrl();
  props.setProperty('FORM_URL', url);
  Logger.log('Quick-log form: ' + url);
  try {
    SpreadsheetApp.getUi().alert(
      'Setup complete',
      'Share this quick-log link with the desk (bookmark it, pin it in Teams/Slack):\n\n' + url +
        '\n\nCheck the Meetings tab to confirm your compliance meeting dates.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
  } catch (e) {
    // No UI when run from the editor without the sheet open; the log has the URL.
  }
}

function createQuickLogForm_() {
  const form = FormApp.create(CONFIG.FIRM_NAME + ' – Trade Error Quick Log');
  form.setDescription(
    'Takes 10 seconds. Log the error now so it isn\'t lost — you can do the full compliance form later.\n' +
      'Full compliance form: ' + CONFIG.COMPLIANCE_FORM_URL
  );
  try {
    form.setEmailCollectionType(FormApp.EmailCollectionType.VERIFIED);
  } catch (e) {
    form.setCollectEmail(true);
  }
  form.setAllowResponseEdits(false);
  form.setConfirmationMessage(
    'Logged — thank you. When you have 15 minutes, please complete the full compliance form: ' +
      CONFIG.COMPLIANCE_FORM_URL
  );

  form.addTextItem().setTitle(COL.NAME).setRequired(true);
  form.addDateItem().setTitle(COL.ERROR_DATE).setRequired(true);
  form.addTextItem().setTitle(COL.ACCOUNT);
  form.addTextItem().setTitle(COL.NOTE);
  return form;
}

function findTrackerSheet_(ss) {
  const byName = ss.getSheetByName(TRACKER_SHEET);
  if (byName) return byName;
  return ss.getSheets().find(s => s.getFormUrl()) || null;
}

function addTrackingColumns_(sheet) {
  const lastCol = Math.max(sheet.getLastColumn(), 1);
  const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  TRACKING_COLUMNS.forEach(name => {
    if (headers.indexOf(name) === -1) {
      headers.push(name);
      sheet.getRange(1, headers.length).setValue(name).setFontWeight('bold').setBackground('#fff2cc');
    }
  });

  const map = headerMap_(sheet);
  const rows = sheet.getMaxRows() - 1;
  const statusRule = SpreadsheetApp.newDataValidation()
    .requireValueInList([STATUS_OPEN, STATUS_SUBMITTED, STATUS_WAIVED], true)
    .build();
  sheet.getRange(2, map[COL.STATUS], rows, 1).setDataValidation(statusRule);
  sheet.getRange(2, map[COL.COMPLETED_ON], rows, 1).setNumberFormat('yyyy-mm-dd');
  sheet.getRange(2, map[COL.LAST_REMINDER], rows, 1).setNumberFormat('yyyy-mm-dd');

  // Highlight open rows so outstanding items stand out.
  const statusLetter = columnLetter_(map[COL.STATUS]);
  const openRule = SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$' + statusLetter + '2="' + STATUS_OPEN + '"')
    .setBackground('#fce8e6')
    .setRanges([sheet.getRange(2, 1, rows, sheet.getLastColumn())])
    .build();
  sheet.setConditionalFormatRules([openRule]);
  sheet.setFrozenRows(1);

  // Back-fill status on any rows that already exist.
  const data = sheet.getDataRange().getValues();
  for (let r = 1; r < data.length; r++) {
    if (data[r][map[COL.TIMESTAMP] - 1] && !data[r][map[COL.STATUS] - 1]) {
      sheet.getRange(r + 1, map[COL.STATUS]).setValue(STATUS_OPEN);
      sheet.getRange(r + 1, map[COL.REMINDERS_SENT]).setValue(0);
    }
  }
}

function setupMeetingsSheet_(ss) {
  let sheet = ss.getSheetByName(MEETINGS_SHEET);
  if (!sheet) {
    sheet = ss.insertSheet(MEETINGS_SHEET);
    sheet.getRange(1, 1, 1, 3)
      .setValues([['Compliance Meeting Date', 'Reminders Sent On', 'People Reminded']])
      .setFontWeight('bold');
    sheet.setFrozenRows(1);
    sheet.getRange('A:B').setNumberFormat('yyyy-mm-dd');
    sheet.setColumnWidths(1, 3, 180);
  }
  if (CONFIG.MEETING_RULE && sheet.getLastRow() < 2) {
    const dates = upcomingMeetingDates_(today_(), CONFIG.MEETING_RULE, CONFIG.MEETINGS_TO_PREFILL);
    sheet.getRange(2, 1, dates.length, 1).setValues(dates.map(d => [d]));
  }
  return sheet;
}

// ---------------------------------------------------------------------------
// Spreadsheet menu
// ---------------------------------------------------------------------------
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Trade Errors')
    .addItem('Mark selected rows as Submitted', 'markSelectedSubmitted')
    .addItem('Send reminders now', 'sendRemindersNow')
    .addSeparator()
    .addItem('Show quick-log form link', 'showFormLink')
    .addItem('Run setup', 'setup')
    .addToUi();
}

function markSelectedSubmitted() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getActiveSheet();
  if (sheet.getName() !== TRACKER_SHEET) {
    SpreadsheetApp.getUi().alert('Select rows on the "' + TRACKER_SHEET + '" tab first.');
    return;
  }
  const map = headerMap_(sheet);
  const now = new Date();
  let count = 0;
  sheet.getActiveRangeList().getRanges().forEach(range => {
    for (let row = range.getRow(); row < range.getRow() + range.getNumRows(); row++) {
      if (row < 2) continue;
      sheet.getRange(row, map[COL.STATUS]).setValue(STATUS_SUBMITTED);
      sheet.getRange(row, map[COL.COMPLETED_ON]).setValue(now);
      count++;
    }
  });
  ss.toast(count + ' row(s) marked as Submitted.');
}

function sendRemindersNow() {
  const ui = SpreadsheetApp.getUi();
  const outstanding = getOutstanding_();
  if (outstanding.length === 0) {
    ui.alert('Nothing outstanding — everyone has submitted their compliance forms.');
    return;
  }
  const people = new Set(outstanding.map(o => o.email)).size;
  const answer = ui.alert(
    'Send reminders?',
    'Email ' + people + ' person(s) about ' + outstanding.length + ' open trade error(s)?',
    ui.ButtonSet.YES_NO
  );
  if (answer !== ui.Button.YES) return;
  const meeting = nextMeeting_();
  const sent = sendReminders_(meeting ? meeting.date : null);
  SpreadsheetApp.getActiveSpreadsheet().toast('Reminders sent to ' + sent + ' person(s).');
}

function showFormLink() {
  const url = PropertiesService.getScriptProperties().getProperty('FORM_URL') || 'Run setup first.';
  SpreadsheetApp.getUi().alert('Trade Error Quick Log', url, SpreadsheetApp.getUi().ButtonSet.OK);
}

// ---------------------------------------------------------------------------
// Triggers
// ---------------------------------------------------------------------------

/** Runs on every quick-log submission. */
function onTradeErrorLogged(e) {
  const sheet = e.range.getSheet();
  const row = e.range.getRow();
  const map = headerMap_(sheet);

  sheet.getRange(row, map[COL.STATUS]).setValue(STATUS_OPEN);
  sheet.getRange(row, map[COL.REMINDERS_SENT]).setValue(0);

  if (!CONFIG.SEND_CONFIRMATION_ON_LOG) return;
  const entry = rowToEntry_(sheet.getRange(row, 1, 1, sheet.getLastColumn()).getValues()[0], map, row);
  if (!entry.email) return;

  MailApp.sendEmail({
    to: entry.email,
    name: CONFIG.FIRM_NAME + ' Compliance',
    subject: 'Trade error logged (' + fmtDate_(entry.errorDate) + ') – full compliance form still needed',
    htmlBody:
      '<p>Hi ' + esc_(entry.name || '') + ',</p>' +
      '<p>Thanks for logging your trade error from <b>' + esc_(fmtDate_(entry.errorDate)) + '</b>. ' +
      'Please complete the full compliance form when you have 15 minutes:</p>' +
      '<p><a href="' + esc_(CONFIG.COMPLIANCE_FORM_URL) + '">Open the compliance form</a></p>' +
      '<p>If it\'s still outstanding, you\'ll get a reminder ' + CONFIG.REMINDER_DAYS_BEFORE +
      ' days before the next compliance meeting.</p>',
  });
}

/** Runs daily. Sends reminders once per meeting, starting REMINDER_DAYS_BEFORE days ahead. */
function dailyReminderCheck() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(MEETINGS_SHEET);
  if (!sheet || sheet.getLastRow() < 2) return;

  const today = today_();
  const rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, 2).getValues();
  const due = rows
    .map((r, i) => ({ date: r[0], sentOn: r[1], row: i + 2 }))
    .filter(m => m.date instanceof Date && !m.sentOn)
    .map(m => Object.assign(m, { daysUntil: daysBetween_(today, m.date) }))
    .filter(m => m.daysUntil >= 0 && m.daysUntil <= CONFIG.REMINDER_DAYS_BEFORE)
    .sort((a, b) => a.date - b.date)[0];
  if (!due) return;

  const sent = sendReminders_(due.date);
  sheet.getRange(due.row, 2, 1, 2).setValues([[new Date(), sent]]);
}

// ---------------------------------------------------------------------------
// Reminders
// ---------------------------------------------------------------------------

/** Emails everyone with an open entry and sends compliance a summary. Returns # people emailed. */
function sendReminders_(meetingDate) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(TRACKER_SHEET);
  const map = headerMap_(sheet);
  const outstanding = getOutstanding_();
  const meetingText = meetingDate ? fmtDate_(meetingDate) : 'the upcoming compliance meeting';

  const byPerson = {};
  outstanding.forEach(o => {
    (byPerson[o.email] = byPerson[o.email] || []).push(o);
  });

  const now = new Date();
  Object.keys(byPerson).forEach(email => {
    const items = byPerson[email];
    const list = items
      .map(o => '<li>' + esc_(fmtDate_(o.errorDate)) + (o.account ? ' — ' + esc_(o.account) : '') +
        (o.note ? ' — ' + esc_(o.note) : '') + '</li>')
      .join('');

    MailApp.sendEmail({
      to: email,
      name: CONFIG.FIRM_NAME + ' Compliance',
      subject: 'Reminder: compliance form due before the ' + meetingText + ' meeting',
      htmlBody:
        '<p>Hi ' + esc_(items[0].name || '') + ',</p>' +
        '<p>Our compliance meeting is on <b>' + esc_(meetingText) + '</b>. ' +
        'You still have ' + (items.length === 1 ? 'a trade error' : items.length + ' trade errors') +
        ' without a completed compliance form:</p><ul>' + list + '</ul>' +
        '<p><a href="' + esc_(CONFIG.COMPLIANCE_FORM_URL) + '">Complete the compliance form</a> (about 15 minutes).</p>' +
        '<p>Already done? Reply to this email and compliance will update the tracker.</p>',
    });

    items.forEach(o => {
      sheet.getRange(o.row, map[COL.REMINDERS_SENT]).setValue((Number(o.remindersSent) || 0) + 1);
      sheet.getRange(o.row, map[COL.LAST_REMINDER]).setValue(now);
    });
  });

  sendComplianceSummary_(outstanding, meetingText, ss.getUrl());
  return Object.keys(byPerson).length;
}

function sendComplianceSummary_(outstanding, meetingText, sheetUrl) {
  if (!CONFIG.COMPLIANCE_TEAM_EMAILS.length) return;
  const today = today_();
  const rows = outstanding
    .sort((a, b) => (a.errorDate || 0) - (b.errorDate || 0))
    .map(o =>
      '<tr><td>' + esc_(o.name) + '</td><td>' + esc_(o.email) + '</td><td>' + esc_(fmtDate_(o.errorDate)) +
      '</td><td>' + esc_(o.account) + '</td><td style="text-align:right">' +
      (o.errorDate instanceof Date ? daysBetween_(o.errorDate, today) : '') + '</td></tr>')
    .join('');

  const body = outstanding.length === 0
    ? '<p>All logged trade errors have completed compliance forms ahead of ' + esc_(meetingText) + '. 🎉</p>'
    : '<p>' + outstanding.length + ' trade error(s) still need a compliance form before ' + esc_(meetingText) +
      '. Reminders have been emailed to each person below.</p>' +
      '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse">' +
      '<tr><th>Name</th><th>Email</th><th>Error date</th><th>Account / ticker</th><th>Days open</th></tr>' +
      rows + '</table>';

  MailApp.sendEmail({
    to: CONFIG.COMPLIANCE_TEAM_EMAILS.join(','),
    name: CONFIG.FIRM_NAME + ' Compliance',
    subject: 'Outstanding trade error forms – ' + outstanding.length + ' open before ' + meetingText,
    htmlBody: body + '<p><a href="' + esc_(sheetUrl) + '">Open the tracker</a></p>',
  });
}

// ---------------------------------------------------------------------------
// Data helpers
// ---------------------------------------------------------------------------
function getOutstanding_() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TRACKER_SHEET);
  if (!sheet || sheet.getLastRow() < 2) return [];
  const map = headerMap_(sheet);
  return sheet.getDataRange().getValues()
    .slice(1)
    .map((values, i) => rowToEntry_(values, map, i + 2))
    .filter(o => o.timestamp && o.email && CLOSED_STATUSES.indexOf(o.status) === -1);
}

function rowToEntry_(values, map, row) {
  const get = name => (map[name] ? values[map[name] - 1] : '');
  return {
    row: row,
    timestamp: get(COL.TIMESTAMP),
    email: String(get(COL.EMAIL) || '').trim().toLowerCase(),
    name: String(get(COL.NAME) || '').trim(),
    errorDate: get(COL.ERROR_DATE),
    account: String(get(COL.ACCOUNT) || '').trim(),
    note: String(get(COL.NOTE) || '').trim(),
    status: String(get(COL.STATUS) || STATUS_OPEN).trim(),
    remindersSent: get(COL.REMINDERS_SENT),
  };
}

/** Header name -> 1-based column index. Looked up by name so column moves don't break anything. */
function headerMap_(sheet) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const map = {};
  headers.forEach((h, i) => { if (h) map[String(h).trim()] = i + 1; });
  return map;
}

function nextMeeting_() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(MEETINGS_SHEET);
  if (!sheet || sheet.getLastRow() < 2) return null;
  const today = today_();
  const dates = sheet.getRange(2, 1, sheet.getLastRow() - 1, 1).getValues()
    .map(r => r[0])
    .filter(d => d instanceof Date && daysBetween_(today, d) >= 0)
    .sort((a, b) => a - b);
  return dates.length ? { date: dates[0] } : null;
}

// ---------------------------------------------------------------------------
// Date helpers (Apps Script's Date uses the script time zone)
// ---------------------------------------------------------------------------
function today_() {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function daysBetween_(from, to) {
  const a = new Date(from.getFullYear(), from.getMonth(), from.getDate());
  const b = new Date(to.getFullYear(), to.getMonth(), to.getDate());
  return Math.round((b - a) / MS_PER_DAY);
}

/** Next `count` meeting dates on or after `from`, e.g. {nth: 2, weekday: 'Tuesday'}. */
function upcomingMeetingDates_(from, rule, count) {
  const weekday = WEEKDAYS.indexOf(rule.weekday);
  if (weekday === -1) throw new Error('MEETING_RULE.weekday must be a full day name, e.g. "Tuesday".');
  const dates = [];
  for (let m = 0; dates.length < count && m < count + 2; m++) {
    const year = from.getFullYear();
    const month = from.getMonth() + m;
    let d;
    if (rule.nth === -1) {
      d = new Date(year, month + 1, 0);
      d.setDate(d.getDate() - ((d.getDay() - weekday + 7) % 7));
    } else {
      d = new Date(year, month, 1);
      d.setDate(1 + ((weekday - d.getDay() + 7) % 7) + (rule.nth - 1) * 7);
    }
    if (d >= from) dates.push(d);
  }
  return dates;
}

function fmtDate_(d) {
  if (!(d instanceof Date)) return String(d || '');
  return Utilities.formatDate(d, Session.getScriptTimeZone(), 'EEE, MMM d, yyyy');
}

function columnLetter_(n) {
  let s = '';
  for (; n > 0; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(65 + ((n - 1) % 26)) + s;
  return s;
}

function esc_(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
