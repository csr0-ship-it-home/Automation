# Trade Error Quick Log + Compliance Reminders (Microsoft 365 / Excel)

This is the Microsoft 365 version of [`../trade-error-tracker`](../trade-error-tracker). It works like this:

- **Microsoft Form (10 seconds):** the person logs the error right away with their name, the error date, the
  custodian, and optionally an account/ticker and a note.
- **Excel workbook on SharePoint/OneDrive:** each log becomes a row with Status **Open** until compliance marks it
  **Submitted**.
- **Power Automate, every morning:** when a compliance meeting is 7 days away, everyone with an Open row gets a
  reminder email and compliance gets a summary of who is outstanding.

All the logic is in four **Office Scripts** (the `.ts` files in [`office-scripts/`](./office-scripts)) that you paste
into Excel. The two Power Automate flows only call those scripts and send the emails they return.

**Requirements:** a Microsoft 365 business account with Excel on the web, Microsoft Forms and Power Automate. The
connectors used (Forms, Excel Online (Business), Outlook) are all *standard*, so no premium license is needed. If
you don't see an **Automate** tab in Excel on the web, ask IT to enable Office Scripts
(*Microsoft 365 admin center → Settings → Org settings → Office Scripts*).

> Build everything (workbook, scripts, flows) under the **same account**, ideally a compliance team account.
> Power Automate can only run Office Scripts owned by the flow's account, and emails are sent from that account.

---

## Step 1: Create the workbook (2 min)

1. In SharePoint (the compliance team site) or OneDrive for Business, click **New → Excel workbook**.
   Name it `Trade Error Tracker`.
2. It opens in Excel on the web. Keep it open.

## Step 2: Add the four scripts (5 min)

For each file below, in Excel on the web:
**Automate → New Script**, delete the sample code, paste in the whole file, click the script name at the top to
rename it, then click **Save script**.

| # | Paste this file | Name the script |
|---|---|---|
| 1 | [`office-scripts/1-Setup.ts`](./office-scripts/1-Setup.ts) | `Setup Trade Error Tracker` |
| 2 | [`office-scripts/2-LogTradeError.ts`](./office-scripts/2-LogTradeError.ts) | `Log Trade Error` |
| 3 | [`office-scripts/3-GetReminders.ts`](./office-scripts/3-GetReminders.ts) | `Get Reminders` |
| 4 | [`office-scripts/4-MarkSelectedSubmitted.ts`](./office-scripts/4-MarkSelectedSubmitted.ts) | `Mark Selected Submitted` |

Before saving **Setup**, set your meeting pattern at the top:

```ts
const MEETING_NTH = 2;             // 2nd ... (use -1 for "last")
const MEETING_WEEKDAY = "Tuesday"; // ... Tuesday of each month
```

## Step 3: Run Setup and fill in Settings (3 min)

1. Open **Setup Trade Error Tracker** and click **Run**. It creates three tabs:
   **Settings**, **Trade Errors** and **Meetings** (with the next 12 meeting dates filled in).
2. On the **Settings** tab, fill in:

   | Setting | Example |
   |---|---|
   | Firm name | `Acme Capital` |
   | Compliance form URL | link to your full 15-minute compliance form |
   | Compliance team emails | `jane@acme.com; compliance@acme.com` |
   | Reminder days before meeting | `7` |

3. On the **Meetings** tab, fix any dates that don't follow the pattern (holidays, moved meetings) and add or
   delete rows as needed.
4. Optional: open **Mark Selected Submitted** and choose **… → Add in workbook** to get a button for it.

## Step 4: Create the Microsoft Form (3 min)

1. Go to [forms.office.com](https://forms.office.com) → **New Form**. Title: `Trade Error Quick Log`.
2. Add these questions:

   | Question | Type | Required |
   |---|---|---|
   | Your name | Text | Yes |
   | Date of the trade error | Date | Yes |
   | Custodian | Choice: Schwab, Fidelity, Other | Yes |
   | Account / ticker | Text | No |
   | Quick note | Text | No |

3. **… → Settings:** choose *Only people in my organization can respond* and tick **Record name**. This is how the
   person's email address gets captured.
4. Still in Settings, tick **Customize thank you message** and enter:
   `Logged, thank you. When you have 15 minutes, please complete the full compliance form: <your form link>`
5. Click **Collect responses** and copy the link. Share it later, in Step 7.

## Step 5: Flow 1, "Trade Error – Quick Log" (5 min)

This flow runs on every form submission. It adds the row and sends the person a confirmation email.

Go to [make.powerautomate.com](https://make.powerautomate.com) → **Create → Automated cloud flow**. Name it
`Trade Error – Quick Log` and pick the trigger **When a new response is submitted** (Microsoft Forms).

| Step | Action | Settings |
|---|---|---|
| 1 | **When a new response is submitted** (Microsoft Forms) | Form Id: `Trade Error Quick Log` |
| 2 | **Get response details** (Microsoft Forms) | Form Id: `Trade Error Quick Log`<br>Response Id: *Response Id* (dynamic content) |
| 3 | **Run script** (Excel Online (Business)) | Location / Document Library / File: your `Trade Error Tracker` workbook<br>Script: `Log Trade Error`<br>**email:** *Responders' Email*<br>**name:** *Your name*<br>**errorDate:** *Date of the trade error*<br>**loggedAt:** expression below<br>**account:** *Account / ticker*<br>**note:** *Quick note*<br>**custodian:** *Custodian* |
| 4 | **Send an email (V2)** (Office 365 Outlook) | To: *to* (from Run script)<br>Subject: *subject*<br>Body: *body* |

Expression for **loggedAt**: click in the field, choose the **fx / Expression** tab, and paste:

```
convertFromUtc(utcNow(), 'Eastern Standard Time', 'yyyy-MM-dd HH:mm')
```

Replace `Eastern Standard Time` with your time zone if needed, e.g. `Central Standard Time` or
`Pacific Standard Time`. Windows time zone names apply, and they handle daylight saving automatically.

Click **Save**. Test it by submitting the form once. A row should appear on **Trade Errors** and a confirmation
email should arrive. Leave step 4 out if you don't want confirmation emails.

## Step 6: Flow 2, "Trade Error – Compliance Reminders" (5 min)

This flow runs every morning. On most days the script returns no emails and nothing happens. When a meeting is
7 days away, it returns the reminder emails and the compliance summary.

**Create → Scheduled cloud flow**. Name it `Trade Error – Compliance Reminders`, set it to repeat every **1 Day**,
then **Create**.

| Step | Action | Settings |
|---|---|---|
| 1 | **Recurrence** | Interval `1`, Frequency `Day`. Under *Advanced parameters*: Time zone = your office, At these hours = `8` |
| 2 | **Run script** (Excel Online (Business)) | Same workbook as before<br>Script: `Get Reminders`<br>**today:** expression below<br>**sendNow:** `No` |
| 3 | **Send an email (V2)** (Office 365 Outlook) | To: *to*, Subject: *subject*, Body: *body*, all from Run script → *emails*. Power Automate wraps this step in **Apply to each** automatically. That's expected. |

Expression for **today**:

```
convertFromUtc(utcNow(), 'Eastern Standard Time', 'yyyy-MM-dd')
```

Click **Save**.

**To test now:** temporarily add a meeting 3 days from today on the **Meetings** tab, then in the flow click
**Test → Manually → Run flow**. Everyone with an Open row and the compliance team should get an email, and the
Meetings row should show *Reminders Sent On*. Afterwards, delete the test meeting row.

**Optional "send reminders now" button:** create an **Instant cloud flow** with the *Manually trigger a flow*
trigger. Add the same steps 2–3, but set **sendNow = Yes**. That flow sends reminders immediately about the next
meeting, without marking the meeting as done.

## Step 7: Roll it out

- Pin the form link in Teams/Slack, add it to browser bookmarks, and put it in the trade error procedure:
  *"Log it in the quick form right away. Do the full compliance form within X days."*
- Compliance: when a full form comes in, select the row(s) on **Trade Errors** and run **Mark Selected Submitted**,
  or change the Status dropdown directly. Use **Waived** for duplicates or rows logged by mistake.
- Each year, add the next year's meeting dates on the **Meetings** tab.

---

## How it behaves

- **Once per meeting:** reminders go out on the first daily run within 7 days of a meeting. The Meetings row is
  then stamped, so later runs don't send again. If the flow misses a day, it catches up the next day.
- **One email per person**, listing all of their open errors.
- **Compliance summary:** lists name, email, error date, account and days open. If nothing is open you get an
  "all clear" email instead.
- **Tracking:** *Reminders Sent* and *Last Reminder* on each row show how often someone has been chased.
- **Columns** are found by header name. You can reorder them or add your own, but don't rename the existing ones.
- **Troubleshooting:** if a flow fails, open its run history. The error message from the script shows on the
  **Run script** step, e.g. "TradeErrors table not found. Run the Setup script first." If *Run script* doesn't list
  your scripts, the flow was created under a different account than the one that saved the scripts.
