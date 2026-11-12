import io
import re
import csv
from typing import Dict, Any, Optional, List, Set
import pandas as pd

# Comprehensive set of string representations for missing / null data
DEFAULT_NULL_STRINGS: Set[str] = {
    "",
    " ",
    "null",
    "none",
    "na",
    "n/a",
    "nan",
    "<na>",
    "<null>",
    "\\n",
    "-",
    "--",
    "?",
    "nil"
}


def decode_file_bytes(raw_bytes: bytes) -> str:
    """
    Robust multi-encoding decoder for .txt, .csv, and .dat files.
    Tries standard and Windows/legacy encodings automatically.
    """
    encodings_to_try = [
        "utf-8",
        "utf-8-sig",
        "utf-16",
        "utf-16-le",
        "cp1252",
        "latin-1",
        "iso-8859-1"
    ]
    for enc in encodings_to_try:
        try:
            return raw_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_bytes.decode("latin-1", errors="replace")


def is_table_divider_line(line: str) -> bool:
    """
    Detects ASCII or Markdown table divider lines often found in .txt files, e.g.:
      |---|---|---|
      |:---|:---:|---:|
      +---+---+---+
      ====================
      --------------------
    """
    s = line.strip()
    if not s:
        return False
    # If the line consists only of dashes, pluses, equals, colons, pipes, and whitespace
    if re.fullmatch(r"^[|\+\=\:\-\s]+$", s):
        # Must contain at least two divider symbols to avoid false positive on single pipe
        if s.count("-") >= 2 or s.count("=") >= 2 or s.count("+") >= 2:
            return True
    return False


def sanitize_raw_text(
    raw_text: str,
    strip_borders: bool = True,
    skip_table_dividers: bool = True,
    skip_comments: bool = True
) -> List[str]:
    """
    Cleans raw text from .txt and .csv files:
    - Normalizes linebreaks and non-breaking spaces
    - Drops ASCII / Markdown table dividers (|---|---|)
    - Skips comment lines (# or //)
    - Strips leading and trailing boundary pipes (|col1|col2| -> col1|col2)
    """
    text = raw_text.lstrip("\ufeff")
    raw_lines = [line.strip().replace("\u00a0", " ") for line in text.splitlines()]

    cleaned_lines = []
    for line in raw_lines:
        if not line:
            continue
        # Skip comment lines in .txt files
        if skip_comments and (line.startswith("#") or line.startswith("//")):
            continue
        # Skip markdown / ASCII dividers (|---|---| or +---+---+)
        if skip_table_dividers and is_table_divider_line(line):
            continue
        cleaned_lines.append(line)

    if not cleaned_lines or not strip_borders:
        return cleaned_lines

    # Check if lines consistently start and end with boundary pipes
    sample = cleaned_lines[:20]
    starts_pipe = all(l.startswith("|") and not l.startswith("||") for l in sample)
    ends_pipe = all(l.endswith("|") and not l.endswith("||") for l in sample)

    if starts_pipe and ends_pipe:
        result = []
        for l in cleaned_lines:
            if l.startswith("|") and l.endswith("|"):
                l = l[1:-1].strip()
            result.append(l)
        return result

    return cleaned_lines


def parse_delimited_file(
    file_content: str,
    delimiter_mode: str = "smart_pipe_empty",
    custom_regex: str = r"\|{1,2}",
    has_header: bool = True,
    handle_space_pipes: bool = True,
    strip_borders: bool = True,
    skip_table_dividers: bool = True,
    null_strings: Optional[Set[str]] = None
) -> pd.DataFrame:
    """
    Parses .txt, .csv, and other delimited text files.
    """
    lines = sanitize_raw_text(
        file_content,
        strip_borders=strip_borders,
        skip_table_dividers=skip_table_dividers
    )
    if not lines:
        return pd.DataFrame()

    null_set = DEFAULT_NULL_STRINGS if null_strings is None else DEFAULT_NULL_STRINGS.union(null_strings)
    parsed_rows: List[List[Any]] = []

    if delimiter_mode == "smart_pipe_empty":
        for line in lines:
            try:
                reader = csv.reader([line], delimiter="|", quotechar='"', skipinitialspace=False)
                row = next(reader)
            except Exception:
                row = line.split("|")
            parsed_rows.append(row)

    elif delimiter_mode == "mixed_delimiters_with_empty":
        for line in lines:
            if handle_space_pipes:
                # Replace '|   |' with explicit empty marker
                line = re.sub(r"\|[ \t]+\|", "||__EMPTY_FIELD__||", line)
            
            tokens = re.split(r"\|\||\|", line)
            cleaned_tokens = ["" if t == "__EMPTY_FIELD__" else t for t in tokens]
            parsed_rows.append(cleaned_tokens)

    elif delimiter_mode == "strict_double_pipe":
        for line in lines:
            parsed_rows.append(line.split("||"))

    elif delimiter_mode == "custom_regex":
        pattern = re.compile(custom_regex)
        for line in lines:
            parsed_rows.append(pattern.split(line))

    # Clean each cell
    cleaned_rows = []
    for row in parsed_rows:
        cleaned_row = []
        for cell in row:
            if cell is None:
                cleaned_row.append(pd.NA)
                continue
            c_str = str(cell).strip()
            if c_str.lower() in null_set:
                cleaned_row.append(pd.NA)
            else:
                cleaned_row.append(c_str)
        cleaned_rows.append(cleaned_row)

    # Normalize row lengths
    max_cols = max(len(row) for row in cleaned_rows)
    normalized_rows = [row + [pd.NA] * (max_cols - len(row)) for row in cleaned_rows]

    # Handle headers
    if has_header and len(normalized_rows) > 0:
        headers = []
        seen = {}
        for i, h in enumerate(normalized_rows[0]):
            h_clean = str(h).strip() if pd.notna(h) and str(h).strip() else f"Column_{i+1}"
            if h_clean in seen:
                seen[h_clean] += 1
                headers.append(f"{h_clean}_{seen[h_clean]}")
            else:
                seen[h_clean] = 0
                headers.append(h_clean)
        df = pd.DataFrame(normalized_rows[1:], columns=headers)
    else:
        headers = [f"Column_{i+1}" for i in range(max_cols)]
        df = pd.DataFrame(normalized_rows, columns=headers)

    return df


def format_dataframe(
    df: pd.DataFrame,
    column_rules: Optional[Dict[str, Dict[str, Any]]] = None,
    clean_column_names: bool = True,
    null_fill_value: str = ""
) -> pd.DataFrame:
    """
    Applies column formatting and fills missing/null values based on user choice.
    """
    cleaned_df = df.copy()

    if clean_column_names:
        cleaned_df.columns = [
            re.sub(r"\s+", "_", re.sub(r"[^\w\s]", "", str(col))).strip()
            for col in cleaned_df.columns
        ]

    rename_mapping = {}

    for col in cleaned_df.columns:
        rule = column_rules.get(col, {}) if column_rules else {}
        col_type = rule.get("type", "text")

        cleaned_df[col] = cleaned_df[col].apply(
            lambda x: pd.NA if (pd.isna(x) or str(x).strip().lower() in DEFAULT_NULL_STRINGS) else str(x).strip()
        )

        if col_type == "date":
            target_fmt = rule.get("date_format", "%Y-%m-%d")
            parsed_dates = pd.to_datetime(cleaned_df[col], errors="coerce")
            cleaned_df[col] = parsed_dates.dt.strftime(target_fmt)

        elif col_type in ("number", "currency"):
            raw_nums = cleaned_df[col].astype(str).str.replace(r"[^\d.-]", "", regex=True)
            numeric_vals = pd.to_numeric(raw_nums, errors="coerce")
            decimals = rule.get("decimals", 2)
            prefix = rule.get("currency_symbol", "") if col_type == "currency" else ""

            if decimals == 0:
                cleaned_df[col] = numeric_vals.apply(lambda x: f"{prefix}{int(x):,}" if pd.notnull(x) else pd.NA)
            else:
                cleaned_df[col] = numeric_vals.apply(lambda x: f"{prefix}{x:,.{decimals}f}" if pd.notnull(x) else pd.NA)

        elif col_type == "id":
            pad = rule.get("id_pad_zeros", 0)
            cleaned_df[col] = cleaned_df[col].astype(str).str.replace(r"\D", "", regex=True)
            if pad > 0:
                cleaned_df[col] = cleaned_df[col].apply(
                    lambda x: str(x).zfill(pad) if (x and x != "nan" and x != "<NA>") else pd.NA
                )

        elif col_type == "text":
            case = rule.get("case", "none")
            if case == "upper":
                cleaned_df[col] = cleaned_df[col].apply(lambda x: str(x).upper() if pd.notna(x) else pd.NA)
            elif case == "lower":
                cleaned_df[col] = cleaned_df[col].apply(lambda x: str(x).lower() if pd.notna(x) else pd.NA)
            elif case == "title":
                cleaned_df[col] = cleaned_df[col].apply(lambda x: str(x).title() if pd.notna(x) else pd.NA)

        new_name = rule.get("new_name")
        if new_name and new_name.strip():
            rename_mapping[col] = new_name.strip()

    if rename_mapping:
        cleaned_df = cleaned_df.rename(columns=rename_mapping)

    cleaned_df = cleaned_df.fillna(null_fill_value)

    return cleaned_df
