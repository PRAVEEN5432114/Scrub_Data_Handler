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


def sanitize_raw_text(raw_text: str, strip_borders: bool = True) -> List[str]:
    """
    Cleans raw file text:
    - Strips UTF-8 BOM (\ufeff)
    - Normalizes non-breaking spaces (\u00a0)
    - Optionally strips leading and trailing border pipes (|col1|col2| -> col1|col2)
    """
    # Remove BOM and normalize line breaks
    text = raw_text.lstrip("\ufeff")
    lines = [line.strip().replace("\u00a0", " ") for line in text.splitlines()]
    lines = [line for line in lines if line]

    if not lines or not strip_borders:
        return lines

    # Check if lines consistently start and end with a single pipe (table border format)
    starts_pipe = all(line.startswith("|") and not line.startswith("||") for line in lines[:20])
    ends_pipe = all(line.endswith("|") and not line.endswith("||") for line in lines[:20])

    if starts_pipe and ends_pipe:
        cleaned_lines = []
        for line in lines:
            if line.startswith("|") and line.endswith("|"):
                line = line[1:-1].strip()
            cleaned_lines.append(line)
        return cleaned_lines

    return lines


def parse_delimited_file(
    file_content: str,
    delimiter_mode: str = "smart_pipe_empty",
    custom_regex: str = r"\|{1,2}",
    has_header: bool = True,
    handle_space_pipes: bool = True,
    strip_borders: bool = True,
    null_strings: Optional[Set[str]] = None
) -> pd.DataFrame:
    """
    Parses files with single (|), double (||), and space-separated (|   |) pipe delimiters.

    Modes:
      - 'smart_pipe_empty': Standard pipe '|' delimiter.
                            Both '||' and '|   |' are correctly treated as EMPTY / NULL cells.
      - 'mixed_delimiters_with_empty': Double pipe '||' is a column delimiter,
                                      BUT '|   |' (pipes with 1+ spaces) is treated as an empty cell.
      - 'strict_double_pipe': '||' is the only delimiter. '|| ||' or '||||' are empty cells.
      - 'custom_regex': Custom regex pattern.
    """
    lines = sanitize_raw_text(file_content, strip_borders=strip_borders)
    if not lines:
        return pd.DataFrame()

    null_set = DEFAULT_NULL_STRINGS if null_strings is None else DEFAULT_NULL_STRINGS.union(null_strings)
    parsed_rows: List[List[Any]] = []

    if delimiter_mode == "smart_pipe_empty":
        # Split on single pipe '|'. Handles quotes like "value with | inside"
        for line in lines:
            try:
                reader = csv.reader([line], delimiter="|", quotechar='"', skipinitialspace=False)
                row = next(reader)
            except Exception:
                row = line.split("|")
            parsed_rows.append(row)

    elif delimiter_mode == "mixed_delimiters_with_empty":
        # If '|   |' exists, mark it as an explicit empty token before splitting
        for line in lines:
            if handle_space_pipes:
                # Replace '|   |' (1 or more spaces between pipes) with an empty field marker
                line = re.sub(r"\|[ \t]+\|", "||__EMPTY_FIELD__||", line)
            
            # Split by double pipe '||' or single pipe '|'
            tokens = re.split(r"\|\||\|", line)
            cleaned_tokens = [
                "" if t == "__EMPTY_FIELD__" else t
                for t in tokens
            ]
            parsed_rows.append(cleaned_tokens)

    elif delimiter_mode == "strict_double_pipe":
        # Multi-char double pipe '||'
        for line in lines:
            try:
                reader = csv.reader([line], delimiter="|", quotechar='"')
                # Fallback to python split on '||'
                row = line.split("||")
            except Exception:
                row = line.split("||")
            parsed_rows.append(row)

    elif delimiter_mode == "custom_regex":
        pattern = re.compile(custom_regex)
        for line in lines:
            parsed_rows.append(pattern.split(line))

    else:
        # Default fallback
        for line in lines:
            parsed_rows.append(line.split("|"))

    if not parsed_rows:
        return pd.DataFrame()

    # Step 2: Clean each cell (strip whitespace, detect |   | and null strings)
    cleaned_rows = []
    for row in parsed_rows:
        cleaned_row = []
        for cell in row:
            if cell is None:
                cleaned_row.append(pd.NA)
                continue
            c_str = str(cell).strip()
            # If the cell is empty or matches null representations (NULL, N/A, -, etc.)
            if c_str.lower() in null_set:
                cleaned_row.append(pd.NA)
            else:
                cleaned_row.append(c_str)
        cleaned_rows.append(cleaned_row)

    # Step 3: Normalize row lengths (handle ragged/inconsistent rows)
    max_cols = max(len(row) for row in cleaned_rows)
    normalized_rows = [row + [pd.NA] * (max_cols - len(row)) for row in cleaned_rows]

    # Step 4: Extract headers
    if has_header and len(normalized_rows) > 0:
        raw_headers = normalized_rows[0]
        headers = []
        seen = {}
        for i, h in enumerate(raw_headers):
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
    Applies column formatting and replaces NA/Null with desired export representation.
    """
    cleaned_df = df.copy()

    # Clean column headers
    if clean_column_names:
        cleaned_df.columns = [
            re.sub(r"\s+", "_", re.sub(r"[^\w\s]", "", str(col))).strip()
            for col in cleaned_df.columns
        ]

    rename_mapping = {}

    for col in cleaned_df.columns:
        rule = column_rules.get(col, {}) if column_rules else {}
        col_type = rule.get("type", "text")

        # Strip spaces and standardize nulls
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
                cleaned_df[col] = numeric_vals.apply(
                    lambda x: f"{prefix}{int(x):,}" if pd.notnull(x) else pd.NA
                )
            else:
                cleaned_df[col] = numeric_vals.apply(
                    lambda x: f"{prefix}{x:,.{decimals}f}" if pd.notnull(x) else pd.NA
                )

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

        # Rename column
        new_name = rule.get("new_name")
        if new_name and new_name.strip():
            rename_mapping[col] = new_name.strip()

    if rename_mapping:
        cleaned_df = cleaned_df.rename(columns=rename_mapping)

    # Final replacement for pd.NA based on export choice
    cleaned_df = cleaned_df.fillna(null_fill_value)

    return cleaned_df
