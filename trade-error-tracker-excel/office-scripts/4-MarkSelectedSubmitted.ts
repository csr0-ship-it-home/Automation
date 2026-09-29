/**
 * Office Script: Mark Selected Submitted
 *
 * Select one or more rows on the Trade Errors tab, then run this (or click its button).
 * Sets Status = Submitted and Completed On = today for each selected row.
 */

const EXCEL_EPOCH = Date.UTC(1899, 11, 30);
const MS_PER_DAY = 86400000;

function main(workbook: ExcelScript.Workbook) {
  const table = workbook.getTable("TradeErrors");
  if (!table) throw new Error("TradeErrors table not found. Run the Setup script first.");
  const body = table.getRangeBetweenHeaderAndTotal();
  const selected = workbook.getSelectedRange();
  if (selected.getWorksheet().getName() !== body.getWorksheet().getName()) {
    console.log("Select rows on the Trade Errors tab first.");
    return;
  }

  const headers = table.getHeaderRowRange().getValues()[0].map(h => String(h).trim());
  const statusCol = headers.indexOf("Status");
  const completedCol = headers.indexOf("Completed On");
  const now = new Date();
  const today = (Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) - EXCEL_EPOCH) / MS_PER_DAY;

  const first = body.getRowIndex();
  const from = Math.max(first, selected.getRowIndex());
  const to = Math.min(first + body.getRowCount(), selected.getRowIndex() + selected.getRowCount()) - 1;
  let count = 0;
  for (let row = from; row <= to; row++) {
    body.getCell(row - first, statusCol).setValue("Submitted");
    body.getCell(row - first, completedCol).setValue(today);
    count++;
  }
  console.log(count + " row(s) marked as Submitted.");
}
