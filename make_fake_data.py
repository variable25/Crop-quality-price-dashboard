"""
make_fake_data.py
-----------------
Creates realistic, deliberately MESSY Excel files for the Croplab ETL pipeline.

Why fake data?  Real lab and market files are never clean. We plant the exact
problems the pipeline must handle, and record every one of them in
data/answer_key.csv. Later we can check: did the pipeline catch all of them?

Files created in data/inbox/:
  Lab results (from a partner testing lab)
    1. lab_results_2022-09-wk1.xlsx        -> title lines above header, typo, duplicate
    2. KQL_results_week2.xlsx              -> different column names, text numbers, bad date
    3. Lab Report Sep Wk3 FINAL.xlsx       -> merged title, UPPERCASE headers, messy names
  Market prices
    4. agmarknet_prices_2022-09-01_to_2022-09-15.xlsx      -> Agmarknet-style export
    5. agmarknet_prices_2022-09-01_to_2022-09-15 (1).xlsx  -> same file downloaded twice
    6. trader_rates_sep_16-30.xlsx         -> prices per kg, different market names
    7. prices_upload_broken.xlsx           -> not a real Excel file at all

Run:  python make_fake_data.py
"""

import os
import csv
import random
import shutil
from datetime import date, datetime, timedelta

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

random.seed(42)  # fixed seed -> the same "random" data on every run (reproducible)

# more failproof so that this can be run anywhere and the files reach the right path
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) 
# you take the base dir, and attach /data/inbox so that anything that triggers this variable, lands in this file
INBOX = os.path.join(BASE_DIR, "data", "inbox") 
# makes an answer_key.csv file to store the answers I think.
ANSWER_KEY = os.path.join(BASE_DIR, "data", "answer_key.csv")

FONT = Font(name="Arial", size=10)
BOLD = Font(name="Arial", size=10, bold=True)

answer_key = []  # every planted problem gets one entry here


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

# A helper function to handle values and issue, takes in the tuple(all the other things other than what's values and puts it into a tuple)
# Returns a dictionary with list of issues and values.
# values is a list and issues is a tuple
def row(values, *issues):
    """One spreadsheet row. values=None means a blank row.
    issues = (column, what is wrong, what the pipeline should do)."""
    return {"values": values, "issues": list(issues)}

# plant returns a dictionary entry to the answer_key.csv file generated
# file name is the name of the file generated
# excel rows takes int or string, int when problem is identified at a specific row number, string when file-wide problems are referred to
# column takes column name i.e the header value
# issue takes plain string value of an issue
# expected also takes string value
def plant(file_name, excel_row, column, issue, expected):
    answer_key.append({
        "file": file_name,
        "excel_row": excel_row,
        "column": column,
        "issue": issue,
        "expected_handling": expected,
    })

# writes the values to the excel file or rather used to make an excel sheet
# file name is a string containing the actual name of the excel file
# title_lines is a list that contains the title of the sheet, occupy maybe 1 or 2 lines on the top
# headers is a list that contain column names
# rows is a list of dictionaries, contains the data in each row
def write_sheet(file_name, title_lines, headers, rows, merge_title=False):
    """Write one messy sheet and record the real Excel row number of each issue."""
    # A workbook has several sheets, we select sheet one and are on row 1
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    r = 1

    # report titles above the table
    # goes thru every item in title_lines list, and then if merging is needed, merges the cells or sets their font size to bold
    for line in title_lines:                       
        ws.cell(row=r, column=1, value=line).font = BOLD
        if merge_title:
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(headers))
        r += 1
    if title_lines:
        r += 1                                     # empty spacer line under the title

    # enumerate method uses the key value style printing for lists
    # a = [1,2,3] enumerate(a) -> 0 1, 1 2, 2 3 is the answer
    # this loop goes thru the headers list, basically column headers, takes the index(col no),
    # the actual header and the row number as r(the variable on top) to set the header fonts as bold
    for c, h in enumerate(headers, start=1):       # the real header row
        ws.cell(row=r, column=c, value=h).font = BOLD
    r += 1

    # since row is a list of dictionaries, it accesses each dictionary item per iteration
    # in that one dictionary list item, the issues and values are taken in sub loops, and updated in the excel sheet
    # or in the answer_key.csv file according to the relevant use case
    for item in rows:
        for column, issue, expected in item["issues"]:
            plant(file_name, r, column, issue, expected)
        if item["values"] is not None:
            for c, v in enumerate(item["values"], start=1):
                cell = ws.cell(row=r, column=c, value=v)
                cell.font = FONT
                if isinstance(v, (date, datetime)):
                    cell.number_format = "dd-mm-yyyy"
        r += 1

    for c in range(1, len(headers) + 1):           # readable column widths
        ws.column_dimensions[get_column_letter(c)].width = 22

    wb.save(os.path.join(INBOX, file_name))


# ---------------------------------------------------------------------------
# Lab results
# ---------------------------------------------------------------------------

# canonical name: (moisture %, oil %, foreign matter %, aflatoxin ppb)
# None for oil  = not measured for this commodity (normal, not an error)
# None for afla = usually "not detected" by the instrument
LAB_PROFILES = {
    "Tur":       ((9.0, 12.0), None,         (0.3, 1.5), None),
    "Groundnut": ((5.0, 8.0),  (45.0, 50.0), (0.5, 2.0), (2.0, 25.0)),
    "Chana":     ((9.0, 12.0), None,         (0.3, 1.5), None),
    "Turmeric":  ((8.0, 11.0), None,         (0.5, 2.0), (1.0, 10.0)),
}

#
def make_lab_samples(start_day, n, id_start):
    samples = []
    names = list(LAB_PROFILES)
    for i in range(n):
        commodity = names[i % 4]
        moist, oil, fm, afla = LAB_PROFILES[commodity]
        samples.append({
            "sample_id": f"KQL-2209-{id_start + i:03d}",
            "commodity": commodity,
            "batch": f"B{random.randint(100, 999)}",
            "test_date": start_day + timedelta(days=i % 7),
            # here star unpacks, but in arguments, they pack the extra values
            "moisture": round(random.uniform(*moist), 1), # translates to -> round(random.uniform(9.0, 12.0),1 decimal place)
            "oil": round(random.uniform(*oil), 1) if oil else None,
            "fm": round(random.uniform(*fm), 2),
            # 20% of groundnut/turmeric samples are also below detection
            "afla": round(random.uniform(*afla), 1) if afla and random.random() > 0.2 else None,
            "remarks": "",
        })
    return samples

# prepares the first excel sheet with data with the help of the helper functions above
def lab_file_1():
    """Clean-looking report, but with title lines, a decimal typo, a negative
    value, a blank row and an exact duplicate."""
    name = "lab_results_2022-09-wk1.xlsx"
    headers = ["Sample ID", "Commodity", "Batch No", "Test Date", "Moisture (%)",
               "Oil Content (%)", "Foreign Matter (%)", "Aflatoxin (ppb)", "Remarks"]
    s = make_lab_samples(datetime(2022, 9, 1), 16, 1)

    s[4]["moisture"] = 115.0      # Tur sample: 11.5 typed without the decimal point
    s[9]["afla"] = -3.2           # Groundnut: impossible negative reading
    s[3]["remarks"] = "Retest requested by client"

    def vals(x):
        return [x["sample_id"], x["commodity"], x["batch"], x["test_date"], x["moisture"],
                x["oil"], x["fm"], "ND" if x["afla"] is None else x["afla"], x["remarks"]]

    rows = []
    for i, x in enumerate(s):
        issues = []
        if i == 4:
            issues.append(("Moisture (%)", "115 is impossible for a percentage (decimal missed, likely 11.5)",
                           "Reject to rejected_rows: moisture outside 0-100"))
        if i == 9:
            issues.append(("Aflatoxin (ppb)", "Negative aflatoxin value -3.2",
                           "Reject to rejected_rows: aflatoxin cannot be negative"))
        rows.append(row(vals(x), *issues))
        if i == 7:
            rows.append(row(None, ("(all)", "Blank row in the middle of the table", "Drop silently")))
        if i == 12:
            rows.append(row(vals(x), ("(all)", "Exact duplicate of the row above",
                                      "Drop duplicate, load once")))

    plant(name, "3 title lines", "-", "Report title lines above the real header (header is on row 5)",
          "Detect the header row automatically")
    plant(name, "many", "Aflatoxin (ppb)", "'ND' = not detected (below the instrument's limit)",
          "Store NULL + below_detection = TRUE, never 0")
    write_sheet(name, ["Krishi Quality Labs, Bengaluru",
                       "Quality test report: 01-07 Sep 2022",
                       "Prepared by: Lab QA desk"], headers, rows)


def lab_file_2():
    """Different export: new column names, commodity synonyms, dates as text,
    percentages as text, an impossible date, a missing commodity and a retest."""
    name = "KQL_results_week2.xlsx"
    headers = ["sample_id", "commodity name", "batch", "date of test", "moisture",
               "oil %", "FM %", "aflatoxin ppb", "remarks"]
    synonyms = {"Tur": "Arhar", "Groundnut": "Peanut", "Chana": "Bengal Gram", "Turmeric": "Haldi"}
    s = make_lab_samples(datetime(2022, 9, 8), 16, 101)

    def vals(x, date_text=None, commodity=None):
        return [x["sample_id"],
                synonyms[x["commodity"]] if commodity is None else commodity,
                x["batch"],
                date_text or x["test_date"].strftime("%d/%m/%Y"),   # text, day first
                f"{x['moisture']}%",                                  # number stored as text
                x["oil"], x["fm"],
                "BDL" if x["afla"] is None else x["afla"],            # BDL = below detection limit
                x["remarks"]]

    rows = []
    for i, x in enumerate(s):
        if i == 3:
            rows.append(row(vals(x, date_text="31/09/2022"),
                            ("date of test", "31 September does not exist",
                             "Reject to rejected_rows: invalid date")))
        elif i == 6:
            rows.append(row(vals(x, commodity=""),
                            ("commodity name", "Commodity is empty",
                             "Reject to rejected_rows: required field missing")))
        else:
            rows.append(row(vals(x)))

    retest = dict(s[2])                                   # same sample tested again next day
    retest["moisture"] = round(retest["moisture"] + 0.6, 1)
    retest["test_date"] = retest["test_date"] + timedelta(days=1)
    retest["remarks"] = "Retest"
    rows.append(row(vals(retest), ("sample_id", f"{retest['sample_id']} appears twice with different values (retest)",
                                   "Keep the latest test date, log that an older value was replaced")))

    plant(name, "-", "(headers)", "Column names differ from week 1 (sample_id, FM %, ...)",
          "Map to standard names via config")
    plant(name, "-", "commodity name", "Synonyms: Arhar=Tur, Peanut=Groundnut, Bengal Gram=Chana, Haldi=Turmeric",
          "Map to one standard name via config")
    plant(name, "-", "date of test", "Dates are text in dd/mm/yyyy (08/09/2022 = 8 Sep, not 9 Aug)",
          "Parse with dayfirst=True")
    plant(name, "-", "moisture", "Numbers stored as text with a % sign ('10.4%')",
          "Strip % and convert to number")
    plant(name, "many", "aflatoxin ppb", "'BDL' = below detection limit (same meaning as 'ND')",
          "Store NULL + below_detection = TRUE")
    write_sheet(name, [], headers, rows)


def lab_file_3():
    """'FINAL' report typed by hand: merged title, UPPERCASE headers, messy
    names and IDs, decimal comma, future date, unrealistic value, text in a number column."""
    name = "Lab Report Sep Wk3 FINAL.xlsx"
    headers = ["SAMPLE ID", "COMMODITY", "BATCH NO.", "TEST DATE", "MOISTURE %",
               "OIL CONTENT %", "FOREIGN MATTER %", "AFLATOXIN (PPB)", "REMARKS"]
    messy_names = {"Tur": [" tur", "TUR", "Red Gram"], "Groundnut": ["GROUNDNUT", "groundnut "],
                   "Chana": ["chana", "Chana "], "Turmeric": ["TURMERIC", "turmeric"]}
    s = make_lab_samples(datetime(2022, 9, 15), 16, 201)

    rows = []
    for i, x in enumerate(s):
        sid = x["sample_id"]
        commodity = random.choice(messy_names[x["commodity"]])
        test_date = x["test_date"].strftime("%d-%b-%y")            # '15-Sep-22'
        moisture, oil, fm = x["moisture"], x["oil"], x["fm"]
        issues = []

        if i in (0, 1):
            sid = sid.lower() + " "
            issues.append(("SAMPLE ID", "Lowercase ID with a trailing space",
                           "Strip spaces and uppercase before loading"))
        if i == 2:
            moisture = str(moisture).replace(".", ",")
            issues.append(("MOISTURE %", f"Decimal comma '{moisture}'", "Replace comma with dot, convert to number"))
        if i == 5:
            test_date = "18-Sep-32"
            issues.append(("TEST DATE", "Year typed as 32 -> 2032, a date in the future",
                           "Reject to rejected_rows: test date in the future"))
        if i == 8:
            fm = 12.5
            issues.append(("FOREIGN MATTER %", "12.5% is inside 0-100 but unrealistic (normal is under 3%)",
                           "Soft rule: flag for review, not a hard reject"))
        if i == 11:
            oil = "n/a"
            issues.append(("OIL CONTENT %", "Text 'n/a' in a number column", "Convert to NULL"))

        rows.append(row([sid, commodity, x["batch"], test_date, moisture, oil, fm,
                         "<LOD" if x["afla"] is None else x["afla"], x["remarks"]], *issues))

    plant(name, "1", "-", "Merged title cell across the full width", "Detect the header row automatically")
    plant(name, "-", "COMMODITY", "Case and spacing differ (' tur', 'TUR', 'Red Gram')",
          "Strip, lowercase, then map via config")
    plant(name, "-", "TEST DATE", "Dates as text '15-Sep-22'", "Parse to a real date")
    plant(name, "many", "AFLATOXIN (PPB)", "'<LOD' = below limit of detection (same as ND/BDL)",
          "Store NULL + below_detection = TRUE")
    write_sheet(name, ["KRISHI QUALITY LABS - SEP WEEK 3 RESULTS (FINAL)"], headers, rows, merge_title=True)


# ---------------------------------------------------------------------------
# Market prices
# ---------------------------------------------------------------------------

# (district, market, canonical commodity, Agmarknet commodity name, variety, starting modal price Rs/quintal)
MARKETS = [
    ("Kalaburagi",     "Kalaburagi",     "Tur",       "Arhar (Tur/Red Gram)(Whole)", "Local",  7000),
    ("Bidar",          "Bidar",          "Tur",       "Arhar (Tur/Red Gram)(Whole)", "Local",  6900),
    ("Chitradurga",    "Chitradurga",    "Groundnut", "Groundnut",                   "Bold",   6100),
    ("Chitradurga",    "Challakere",     "Groundnut", "Groundnut",                   "Local",  5950),
    ("Gadag",          "Gadag",          "Chana",     "Bengal Gram(Gram)(Whole)",    "Desi",   4650),
    ("Dharwad",        "Hubballi",       "Chana",     "Bengal Gram(Gram)(Whole)",    "Desi",   4700),
    ("Chamarajanagar", "Chamarajanagar", "Turmeric",  "Turmeric",                    "Finger", 7200),
]


def r10(x):
    return int(round(x / 10.0) * 10)   # mandi prices are quoted in round tens


def make_price_series():
    """Daily prices for Sep 2022, markets closed on Sundays (gaps are normal)."""
    series = {m[1]: [] for m in MARKETS}
    for district, market, canon, agname, variety, start in MARKETS:
        modal = float(start)
        d = date(2022, 9, 1)
        while d <= date(2022, 9, 30):
            if d.weekday() != 6:                                  # skip Sundays
                modal *= 1 + random.uniform(-0.015, 0.015)       # small daily moves
                if market == "Chamarajanagar" and 12 <= d.day <= 15:
                    modal *= 1.05                                 # REAL rally: +5% a day
                series[market].append({
                    "date": d,
                    "min": r10(modal * random.uniform(0.90, 0.95)),
                    "max": r10(modal * random.uniform(1.03, 1.08)),
                    "modal": r10(modal),
                })
            d += timedelta(days=1)
    return series


def price_file_agmarknet(series):
    name = "agmarknet_prices_2022-09-01_to_2022-09-15.xlsx"
    headers = ["Sl no.", "District Name", "Market Name", "Commodity", "Variety", "Grade",
               "Min Price (Rs./Quintal)", "Max Price (Rs./Quintal)", "Modal Price (Rs./Quintal)", "Price Date"]
    rows, sl = [], 1

    days = sorted({p["date"] for s in series.values() for p in s if p["date"].day <= 15})
    for d in days:
        for district, market, canon, agname, variety, _ in MARKETS:
            p = next((p for p in series[market] if p["date"] == d), None)
            if p is None:
                continue
            mn, mx, md, mk = p["min"], p["max"], p["modal"], market
            issues = []

            if market == "Kalaburagi" and d.day == 7:
                md = p["modal"] * 10                                       # extra zero typed
                issues.append(("Modal Price (Rs./Quintal)", f"Extra zero: {md} instead of {p['modal']}",
                               "Outlier vs rolling median -> rejected_rows for review"))
            if market == "Challakere" and d.day == 9:
                mn, mx = mx, mn
                issues.append(("Min/Max Price", "Min and max swapped (min > max)",
                               "Reject: min <= modal <= max rule fails"))
            if market == "Gadag" and d.day == 13:
                md = None
                issues.append(("Modal Price (Rs./Quintal)", "Modal price missing",
                               "Reject: required field missing"))
            if market == "Kalaburagi" and d.day == 12:
                mk = "Gulbarga"
                issues.append(("Market Name", "Old name 'Gulbarga' used for Kalaburagi",
                               "Map to 'Kalaburagi' via config"))
            if market == "Chamarajanagar" and d.day in (12, 13, 14, 15):
                issues.append(("Modal Price (Rs./Quintal)", "Real price rally, about +5% per day",
                               "Must NOT be flagged: gradual move, within rolling-median limits"))

            values = [sl, district, mk, agname, variety, "FAQ", mn, mx, md, d.strftime("%d %b %Y")]
            rows.append(row(values, *issues))
            sl += 1

            if market == "Bidar" and d.day == 5:                  # same data, next serial number
                rows.append(row([sl] + values[1:], ("(all)",
                                "Duplicate of the row above except 'Sl no.'",
                                "Dedupe on market + commodity + date; Sl no. is not data")))
                sl += 1

    plant(name, "2 title lines", "-", "Title lines above the header", "Detect the header row automatically")
    plant(name, "-", "Commodity", "Long Agmarknet names, e.g. 'Arhar (Tur/Red Gram)(Whole)'",
          "Map to standard names via config")
    plant(name, "-", "Price Date", "Dates as text '01 Sep 2022'", "Parse to a real date")
    plant(name, "-", "Price Date", "No rows on Sundays (markets closed)", "Normal gap, not an error")
    write_sheet(name, ["Karnataka: daily market prices, 01-Sep-2022 to 15-Sep-2022",
                       "Agmarknet-style export (training data)"], headers, rows)
    return name


def price_file_trader(series):
    name = "trader_rates_sep_16-30.xlsx"
    headers = ["Date", "Mandi", "Crop", "Rate/kg (min)", "Rate/kg (max)", "Rate/kg (avg)"]
    trader_markets = {"Kalaburagi": ("Kalburgi", "Tur"), "Chitradurga": ("Chitradurga", "Groundnut"),
                      "Hubballi": ("Hubli", "Chana"), "Chamarajanagar": ("Chamarajanagar", "Turmeric")}
    rows = []
    days = sorted({p["date"] for s in series.values() for p in s if p["date"].day >= 16})
    for d in days:
        for market, (mandi, crop) in trader_markets.items():
            p = next((p for p in series[market] if p["date"] == d), None)
            if p is None:
                continue
            mn, mx, avg = round(p["min"] / 100, 2), round(p["max"] / 100, 2), round(p["modal"] / 100, 2)
            issues = []
            if market == "Chitradurga" and d.day == 21:
                avg = p["modal"]
                issues.append(("Rate/kg (avg)", f"Quintal price {avg} typed into a per-kg column",
                               "After x100 it is 100 times too high -> outlier, rejected_rows"))
            if market == "Hubballi" and d.day == 27:
                mx = "NA"
                issues.append(("Rate/kg (max)", "Text 'NA' in a number column", "Convert to NULL, then reject: max missing"))
            rows.append(row([d, mandi, crop, mn, mx, avg], *issues))

    plant(name, "-", "(all prices)", "Prices per kg, the other files use per quintal (1 quintal = 100 kg)",
          "Multiply by 100 before loading")
    plant(name, "-", "Mandi", "Name variants: 'Kalburgi' = Kalaburagi, 'Hubli' = Hubballi",
          "Map to standard market names via config")
    plant(name, "-", "Rate/kg (avg)", "Trader 'avg' is not exactly Agmarknet 'modal' price",
          "Load as modal, write this assumption in the docs")
    plant(name, "-", "(no district/variety)", "District, variety, grade columns missing",
          "Fill from a market lookup table or leave NULL")
    write_sheet(name, [], headers, rows)


def duplicate_and_broken_files(agmarknet_name):
    dup = "agmarknet_prices_2022-09-01_to_2022-09-15 (1).xlsx"
    shutil.copyfile(os.path.join(INBOX, agmarknet_name), os.path.join(INBOX, dup))
    plant(dup, "-", "(file)", "Same file downloaded twice under a new name",
          "Same hash as the original -> skip, load nothing")

    broken = "prices_upload_broken.xlsx"
    with open(os.path.join(INBOX, broken), "w") as f:
        f.write("This is not a real Excel file. The upload was cut off.\n")
    plant(broken, "-", "(file)", "Has a .xlsx name but is not an Excel file",
          "Move to data/failed/, log the error, continue with the other files")


# ---------------------------------------------------------------------------

def main():
    if os.path.isdir(INBOX):
        shutil.rmtree(INBOX)                       # start fresh every time
    os.makedirs(INBOX)
    for folder in ("processed", "failed"):
        os.makedirs(os.path.join(BASE_DIR, "data", folder), exist_ok=True)

    lab_file_1()
    lab_file_2()
    lab_file_3()
    series = make_price_series()
    ag = price_file_agmarknet(series)
    price_file_trader(series)
    duplicate_and_broken_files(ag)

    with open(ANSWER_KEY, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "excel_row", "column", "issue", "expected_handling"])
        writer.writeheader()
        writer.writerows(answer_key)

    print(f"Created {len(os.listdir(INBOX))} files in {INBOX}")
    print(f"Planted {len(answer_key)} issues -> {ANSWER_KEY}")


if __name__ == "__main__":
    main()
