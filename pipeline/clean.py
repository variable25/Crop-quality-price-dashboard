'''
Helpers to clean data
Each helper takes one messy value and returns a clean one
Each can be tested on their own cuz they have no knowledge of files and folders

'''

import math
from datetime import date, datetime

class RowRejected(Exception):
    """This is to handle rows which break the hard rule, and are placed in rejected rows"""

def is_missing(value):
    '''True for Nan and None'''
    return value is None or (isinstance(value,float) and math.isnan(value))

def normalize_key(value):
    '''Makes text comparable'''
    if is_missing(value):
        return
    return ' '.join(str(value).split()).lower()

def clean_text(value):
    '''Trim and squeeze spaces, empty text becomes None'''
    if is_missing(value):
        return None
    text = ' '.join(str(value).split())
    return text or None

def clean_id(value):
    '''IDs are trimmed and uppercased'''
    text = clean_text(value)
    return text.upper() if text else None

def lookup(value, mapping):
    '''Translate a name with a synonym table: Peanut -> 'Groundnut. Unknown -> None'''
    return mapping.get(normalize_key(value))

def is_blank_row(record):
    '''True when every data cell is empty'''
    return all(clean_text(v) is None for k,v in record.items() if k not in ('excel_row','raw'))

def is_below_detection(value, markers):
    '''True for lab codes meaning too small to measure, ND, BDL, <LOD'''
    return normalize_key(value) in markers

def parse_number(value, empty_values):
    '''standardizes numbers to its correct values. 10.4% to 10.4 etc'''
    if is_missing(value):
        return None
    if isinstance(value,bool):
        raise ValueError(f"not a number: {value!r}")
    if isinstance(value, (int,float)):
        return float(value)

    text = normalize_key(value)
    if text in empty_values:
        return None
    text = text.replace("%", "").replace(" ", "")
    if "," in text:
        whole, _, decimals = text.rpartition(",")
        if text.count(",") == 1 and len(decimals) != 3:
            text = f"{whole}.{decimals}"      # decimal comma: '11,5' -> '11.5'
        else:
            text = text.replace(",", "")      # thousands: '7,000' -> '7000'
    try:
        number = float(text)
    except ValueError:
        raise ValueError(f"not a number: {value!r}") from None
    if math.isnan(number) or math.isinf(number):   # float() accepts 'nan' and 'inf'; we don't
        raise ValueError(f"not a number: {value!r}")
    return number


def parse_date(value, formats, empty_values):
    """Excel dates pass straight through; text is tried against each format in order."""
    if is_missing(value):
        return None
    if isinstance(value, datetime):           # check datetime first: a datetime is also a date
        return value.date()
    if isinstance(value, date):
        return value
    text = clean_text(value)
    if text is None or text.lower() in empty_values:
        return None
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"not a valid date: {value!r}")


# --- the same helpers, but a problem becomes RowRejected with the column name --------

def number_or_reject(value, column, empty_values):
    try:
        return parse_number(value, empty_values)
    except ValueError as exc:
        raise RowRejected(f"{column}: {exc}") from None


def date_or_reject(value, column, formats, empty_values):
    try:
        return parse_date(value, formats, empty_values)
    except ValueError as exc:
        raise RowRejected(f"{column}: {exc}") from None


def lookup_or_reject(value, column, mapping):
    raw = clean_text(value)
    if raw is None:
        raise RowRejected(f"{column} is missing")
    found = lookup(raw, mapping)
    if found is None:
        raise RowRejected(f"unknown {column} '{raw}' (add it to mappings.yaml)")
    return found


if __name__ == "__main__":
    EMPTY = {"", "na", "n/a", "-"}
    MARKERS = {"nd", "bdl", "<lod"}
    FORMATS = ["%d/%m/%Y", "%d-%b-%y", "%d %b %Y"]

    should_work = [
        ("number with %",    parse_number("10.4%", EMPTY),                    10.4),
        ("decimal comma",    parse_number("11,5", EMPTY),                     11.5),
        ("thousands comma",  parse_number("7,000", EMPTY),                    7000.0),
        ("n/a means empty",  parse_number("n/a", EMPTY),                      None),
        ("day-first date",   parse_date("08/09/2022", FORMATS, EMPTY),        date(2022, 9, 8)),
        ("short month date", parse_date("15-Sep-22", FORMATS, EMPTY),         date(2022, 9, 15)),
        ("Agmarknet date",   parse_date("01 Sep 2022", FORMATS, EMPTY),       date(2022, 9, 1)),
        ("Excel date",       parse_date(datetime(2022, 9, 1), FORMATS, EMPTY), date(2022, 9, 1)),
        ("messy ID",         clean_id("kql-2209-201 "),                       "KQL-2209-201"),
        ("below detection",  is_below_detection(" <LOD", MARKERS),            True),
        ("synonym lookup",   lookup(" Red  Gram", {"red gram": "Tur"}),       "Tur"),
    ]
    should_fail = [
        ("31 September",   lambda: parse_date("31/09/2022", FORMATS, EMPTY)),
        ("text in number", lambda: parse_number("abc", EMPTY)),
    ]

    failures = 0
    for label, got, expected in should_work:
        ok = got == expected
        if not ok:
            failures += 1
        print(f"{'ok  ' if ok else 'FAIL'} {label:<17} got {got!r}")
    for label, call in should_fail:
        try:
            call()
        except ValueError as exc:
            print(f"ok   {label:<17} refused: {exc}")
        else:
            failures += 1
            print(f"FAIL {label:<17} was accepted but should be refused")
    print("\nAll checks passed." if failures == 0 else f"\n{failures} check(s) failed.")