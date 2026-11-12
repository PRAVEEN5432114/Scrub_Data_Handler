import io
import re
from typing import Dict, Any, Optional, Tuple
import pandas as pd


def parse_delimited_file(
    file_content: str,
    delimiter_mode: str = "smart_mixed",
    custom_regex: str = r"\|{1,2}",
    has_header: bool = True
) -> pd.DataFrame:
    """
    Parses raw text data that contains mixed '|' and '||' delimiters.

    Modes:
      - 'smart_mixed': Splits on single '|' and double '||' interchangeably via regex r'\|{1,2}'.
      - 'pipe_with_empty': Standard pipe '|' delimiter (meaning '||' represents an empty/null field).
      - 'double_pipe': Delimited strictly by '||', keeping single '|' as regular text inside fields.
      - 'custom_regex': Custom regular expression supplied by user.
    """
    lines = [line.strip() for line in file_content.splitlines() if line.strip()]
    if not lines:
        return pd.DataFrame()

    if delimiter_mode == "smart_mixed":
        # Split on one or two consecutive pipes
        pattern = re.compile(r"\|{1,2}")
        parsed_rows = [pattern.split(line) for line in lines]
        # Strip whitespace from each cell
        parsed_rows = [[cell.strip() for cell in row] for row in parsed_rows]

        # Normalize row lengths to the maximum number of columns found
        max_cols = max(len(row) for row in parsed_rows)
        normalized_rows = [row + [""] * (max_cols - len(row)) for row in parsed_rows]

        if has_header and len(normalized_rows) > 0:
            headers = [h if h else f"Column_{i+1}" for i, h in enumerate(normalized_rows[0])]
            # Handle duplicate headers if any
            unique_headers = []
            seen = {}
            for h in headers:
                if h in seen:
                    seen[h] += 1
                    unique_headers.append(f"{h}_{seen[h]}")
                else:
                    seen[h] = 0
                    unique_headers.append(h)
            df = pd.DataFrame(normalized_rows[1:], columns=unique_headers)
        else:
            headers = [f"Column_{i+1}" for i in range(max_cols)]
            df = pd.DataFrame(normalized_rows, columns=headers)
        return df

    elif delimiter_mode == "pipe_with_empty":
        # Standard pipe CSV where || means an empty value
        return pd.read_csv(io.StringIO(file_content), sep="|", header=0 if has_header else None, dtype=str)

    elif delimiter_mode == "double_pipe":
        # Multi-character delimiter '||'
        return pd.read_csv(io.StringIO(file_content), sep=r"\|\|", engine="python", header=0 if has_header else None, dtype=str)

    elif delimiter_mode == "custom_regex":
        return pd.read_csv(io.StringIO(file_content), sep=custom_regex, engine="python", header=0 if has_header else None, dtype=str)

    else:
        # Default fallback
        return pd.read_csv(io.StringIO(file_content), sep=r"\|{1,2}", engine="python", header=0 if has_header else None, dtype=str)


def format_dataframe(
    df: pd.DataFrame,
    column_rules: Optional[Dict[str, Dict[str, Any]]] = None,
    clean_column_names: bool = True
) -> pd.DataFrame:
    """
    Applies column-specific formatting rules to the DataFrame.

    column_rules structure:
    {
        "Column_Name": {
            "type": "text" | "date" | "number" | "currency" | "phone" | "id",
            "date_format": "%Y-%m-%d" | "%d/%m/%Y" | etc.,
            "case": "upper" | "lower" | "title" | "none",
            "decimals": 2,
            "currency_symbol": "$",
            "id_pad_zeros": 6,
            "strip_spaces": True,
            "new_name": "New_Column_Name"
        }
    }
    """
    cleaned_df = df.copy()

    # Step 1: Optional Column Name Cleaning
    if clean_column_names:
        cleaned_df.columns = [
            re.sub(r"\s+", "_", str(col).strip())
            for col in cleaned_df.columns
        ]

    if not column_rules:
        # Default auto-cleanup if no explicit rules: strip all strings and clean empty values
        for col in cleaned_df.columns:
            cleaned_df[col] = cleaned_df[col].astype(str).str.strip()
            cleaned_df[col] = cleaned_df[col].replace(["nan", "None", ""], pd.NA)
        return cleaned_df

    # Step 2: Apply per-column transformations
    rename_mapping = {}

    for col in cleaned_df.columns:
        rule = column_rules.get(col, {})
        col_type = rule.get("type", "text")

        # Strip spaces
        if rule.get("strip_spaces", True):
            cleaned_df[col] = cleaned_df[col].astype(str).str.strip()

        # Handle 'nan', 'None'
        cleaned_df[col] = cleaned_df[col].replace(["nan", "None", ""], pd.NA)

        if col_type == "date":
            target_fmt = rule.get("date_format", "%Y-%m-%d")
            # Parse date flexibly then format
            parsed_dates = pd.to_datetime(cleaned_df[col], errors="coerce")
            cleaned_df[col] = parsed_dates.dt.strftime(target_fmt)

        elif col_type in ("number", "currency"):
            # Clean symbols like $, commas, etc.
            raw_nums = cleaned_df[col].astype(str).str.replace(r"[^\d.-]", "", regex=True)
            numeric_vals = pd.to_numeric(raw_nums, errors="coerce")
            decimals = rule.get("decimals", 2)
            prefix = rule.get("currency_symbol", "") if col_type == "currency" else ""

            if decimals == 0:
                cleaned_df[col] = numeric_vals.apply(
                    lambda x: f"{prefix}{int(x):,}" if pd.notnull(x) else ""
                )
            else:
                fmt_str = f"{prefix}{{Comp:,.{decimals}f}}".replace("Comp:", "")
                cleaned_df[col] = numeric_vals.apply(
                    lambda x: f"{prefix}{x:,.{decimals}f}" if pd.notnull(x) else ""
                )

        elif col_type == "id":
            pad = rule.get("id_pad_zeros", 0)
            cleaned_df[col] = cleaned_df[col].astype(str).str.replace(r"\D", "", regex=True)
            if pad > 0:
                cleaned_df[col] = cleaned_df[col].apply(
                    lambda x: str(x).zfill(pad) if x and x != "nan" else ""
                )

        elif col_type == "text":
            case = rule.get("case", "none")
            if case == "upper":
                cleaned_df[col] = cleaned_df[col].astype(str).str.upper()
            elif case == "lower":
                cleaned_df[col] = cleaned_df[col].astype(str).str.lower()
            elif case == "title":
                cleaned_df[col] = cleaned_df[col].astype(str).str.title()

        # Rename column if specified
        new_name = rule.get("new_name")
        if new_name and new_name.strip():
            rename_mapping[col] = new_name.strip()

    if rename_mapping:
        cleaned_df = cleaned_df.rename(columns=rename_mapping)

    return cleaned_df

