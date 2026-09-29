
import requests
import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
from datetime import datetime, timedelta
import streamlit as st

# =============================================================================
# MUTUAL FUND MULTI-FUND COMPARISON - STREAMLIT
# =============================================================================

st.set_page_config(
    page_title="Mutual Fund Comparison",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =============================================================================
# API CONFIGURATION
# =============================================================================

BASE_URL = "https://finapi.upvaly.com/api/mf"


def get_api_key():
    """Read API key from Streamlit Secrets."""
    try:
        return st.secrets["Finapi"]
    except Exception:
        return None


API_KEY = get_api_key()


def get_headers():
    return {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }


# =============================================================================
# SEARCH SCHEMES
# =============================================================================

def search_fund(scheme_name):
    try:
        url = f"{BASE_URL}/search"
        params = {"schemeName": scheme_name}

        response = requests.get(
            url,
            headers=get_headers(),
            params=params,
            timeout=20,
        )

        if response.status_code != 200:
            return []

        data = response.json()

        if data.get("statusCode") == 200:
            return data.get("data", [])

        return []

    except Exception as e:
        st.error(f"Search error: {e}")
        return []


# =============================================================================
# NAV HISTORY
# =============================================================================

def get_nav_history(scheme_code, start_date, end_date):
    try:
        url = f"{BASE_URL}/nav-history/scheme-code/{scheme_code}"
        params = {
            "startDate": start_date,
            "endDate": end_date,
        }

        response = requests.get(
            url,
            headers=get_headers(),
            params=params,
            timeout=30,
        )

        if response.status_code != 200:
            return None

        data = response.json()

        if data.get("statusCode") == 200:
            return data.get("data")

        return None

    except Exception as e:
        st.error(f"NAV error: {e}")
        return None


# =============================================================================
# EXTRACT NAV DATA
# =============================================================================

def extract_nav_dataframe(nav_response):
    if nav_response is None:
        return None

    records = None

    if isinstance(nav_response, list):
        records = nav_response

    elif isinstance(nav_response, dict):
        possible_keys = [
            "navHistory",
            "navData",
            "history",
            "records",
            "items",
            "results",
            "data",
        ]

        for key in possible_keys:
            value = nav_response.get(key)

            if isinstance(value, list):
                records = value
                break

        if records is None:
            if any(
                key in nav_response
                for key in [
                    "nav",
                    "NAV",
                    "date",
                    "navDate",
                    "navValue",
                ]
            ):
                records = [nav_response]

    if not records:
        return None

    rows = []

    for record in records:
        if not isinstance(record, dict):
            continue

        # DATE
        date_value = None

        for key in [
            "date",
            "navDate",
            "Date",
            "NAVDate",
            "nav_date",
            "asOnDate",
            "valuationDate",
        ]:
            if key in record:
                value = record.get(key)

                if value not in [None, ""]:
                    date_value = value
                    break

        # NAV
        nav_value = None

        for key in [
            "nav",
            "NAV",
            "navValue",
            "Nav",
            "nav_value",
            "value",
        ]:
            if key in record:
                value = record.get(key)

                if value not in [None, ""]:
                    nav_value = value
                    break

        if date_value is None or nav_value is None:
            continue

        try:
            nav_value = float(
                str(nav_value)
                .replace(",", "")
                .replace("₹", "")
                .strip()
            )
        except Exception:
            continue

        if nav_value <= 0:
            continue

        rows.append({
            "Date": date_value,
            "NAV": nav_value,
        })

    if not rows:
        return None

    df = pd.DataFrame(rows)

    df["Date"] = pd.to_datetime(
        df["Date"],
        errors="coerce",
    )

    df = df.dropna(subset=["Date"])
    df = df.sort_values("Date")
    df = df.drop_duplicates(
        subset=["Date"],
        keep="last",
    )
    df = df.reset_index(drop=True)

    return df


# =============================================================================
# CALCULATE INVESTMENT GROWTH
# =============================================================================

def calculate_growth(nav_df, investment_amount=10000):
    if nav_df is None or len(nav_df) < 2:
        return None

    df = nav_df.copy()

    beginning_nav = df.iloc[0]["NAV"]

    units = investment_amount / beginning_nav

    df["Investment Value"] = units * df["NAV"]

    df["Daily Return %"] = (
        df["NAV"].pct_change().fillna(0) * 100
    )

    df["Total Return %"] = (
        (df["Investment Value"] / investment_amount) - 1
    ) * 100

    beginning_date = df.iloc[0]["Date"]
    ending_date = df.iloc[-1]["Date"]

    days = (ending_date - beginning_date).days
    years = days / 365.25

    beginning_value = df.iloc[0]["Investment Value"]
    ending_value = df.iloc[-1]["Investment Value"]

    if (
        years > 0
        and beginning_value > 0
        and ending_value > 0
    ):
        cagr = (
            (ending_value / beginning_value) ** (1 / years) - 1
        ) * 100
    else:
        cagr = 0

    df["CAGR %"] = cagr
    df["Investment Years"] = years

    return df


# =============================================================================
# CLEAN FUND NAME
# =============================================================================

def clean_fund_name(name):
    if not name:
        return ""

    name = str(name)

    remove_words = [
        " - Regular Plan",
        " - Direct Plan",
        " - Growth Option",
        " - Growth",
        " - IDCW Option",
        " - IDCW",
        " - Dividend Option",
        " - Dividend",
    ]

    for word in remove_words:
        name = name.replace(word, "")

    return " ".join(name.split()).strip()


# =============================================================================
# FUND NAME WRAPPING
# =============================================================================

def wrap_fund_name(name, max_chars=25):
    name = clean_fund_name(name)

    if len(name) <= max_chars:
        return name

    words = name.split()

    line1 = ""
    line2 = ""

    for word in words:
        test = word if not line1 else line1 + " " + word

        if len(test) <= max_chars:
            line1 = test
        else:
            break

    used_words = line1.split()
    remaining_words = words[len(used_words):]

    line2 = " ".join(remaining_words)

    if not line1:
        midpoint = max(1, len(words) // 2)

        line1 = " ".join(words[:midpoint])
        line2 = " ".join(words[midpoint:])

    if line2:
        return line1 + "\n" + line2

    return line1


# =============================================================================
# BENCHMARK / NIFTY TRI DATA
# =============================================================================

NIFTY_TRI_URL = "https://www.niftyindices.com/Backpage.aspx/getTotalReturnIndexString"

BENCHMARKS = {
    "Broad Market Index": [
        "NIFTY 50",
        "NIFTY NEXT 50",
        "NIFTY 100",
        "NIFTY 200",
        "NIFTY 500",
        "NIFTY MIDCAP 150",
        "NIFTY SMALLCAP 250",
        "NIFTY TOTAL MARKET",
    ],
    "Strategy Index": [
        "NIFTY200 MOMENTUM 30",
        "NIFTY100 LOW VOLATILITY 30",
        "NIFTY200 QUALITY 30",
        "NIFTY ALPHA 50",
        "NIFTY ALPHA LOW-VOLATILITY 30",
        "NIFTY50 VALUE 20",
        "NIFTY100 QUALITY 30",
        "NIFTY50 EQUAL WEIGHT",
        "NIFTY100 EQUAL WEIGHT",
        "NIFTY500 MOMENTUM 50",
        "NIFTY500 QUALITY 50",
        "NIFTY500 LOW VOLATILITY 50",
    ],
}


@st.cache_data(ttl=3600, show_spinner=False)
def get_nifty_tri_history(index_name, start_date, end_date):
    """Fetch official Nifty Total Return Index history."""
    start_display = pd.Timestamp(start_date).strftime("%d-%b-%Y")
    end_display = pd.Timestamp(end_date).strftime("%d-%b-%Y")

    cinfo = (
        "{'name':'"
        + index_name
        + "','startDate':'"
        + start_display
        + "','endDate':'"
        + end_display
        + "','indexName':'"
        + index_name
        + "'}"
    )

    payload = {"cinfo": cinfo}

    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/json; charset=UTF-8",
        "Origin": "https://www.niftyindices.com",
        "Referer": "https://www.niftyindices.com/reports/historical-data",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154.0.0.0 Safari/537.36",
    }

    response = requests.post(
        NIFTY_TRI_URL,
        headers=headers,
        json=payload,
        timeout=60,
    )
    response.raise_for_status()

    outer = response.json()
    raw = outer.get("d", "[]")

    if isinstance(raw, str):
        if raw.lower() == "false":
            return None
        records = json.loads(raw) if raw else []
    else:
        records = raw

    if not records:
        return None

    rows = []

    for record in records:
        if not isinstance(record, dict):
            continue

        date_value = None
        tri_value = None

        for key in [
            "HistoricalDate", "Date", "date", "IndexDate", "indexDate"
        ]:
            if key in record and record[key] not in [None, ""]:
                date_value = record[key]
                break

        # Nifty's response has used slightly different field names over time.
        for key in [
            "Total Returns Index",
            "TotalReturnsIndex",
            "TotalReturnIndex",
            "TRI",
            "tri",
            "Total Returns",
            "TRIValue",
            "TRIndex",
            "TRI_VALUE",
        ]:
            if key in record and record[key] not in [None, ""]:
                tri_value = record[key]
                break

        if tri_value is None:
            # Fallback: identify a field containing TR but not NTR.
            for key, value in record.items():
                key_upper = str(key).upper().replace(" ", "")
                if "TRI" in key_upper and "NTR" not in key_upper:
                    tri_value = value
                    break

        if date_value is None or tri_value is None:
            continue

        try:
            tri_value = float(
                str(tri_value).replace(",", "").replace("₹", "").strip()
            )
        except Exception:
            continue

        if tri_value <= 0:
            continue

        rows.append({"Date": date_value, "TRI": tri_value})

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["TRI"] = pd.to_numeric(df["TRI"], errors="coerce")
    df = df.dropna(subset=["Date", "TRI"])
    df = df.sort_values("Date")
    df = df.drop_duplicates("Date", keep="last")
    df = df.reset_index(drop=True)

    return df


def calculate_benchmark_growth(tri_df, investment_amount):
    if tri_df is None or len(tri_df) < 2:
        return None

    df = tri_df.copy()
    beginning_tri = float(df.iloc[0]["TRI"])
    df["Investment Value"] = (
        investment_amount * df["TRI"] / beginning_tri
    )
    df["Total Return %"] = (
        (df["Investment Value"] / investment_amount) - 1
    ) * 100

    years = (
        (df.iloc[-1]["Date"] - df.iloc[0]["Date"]).days
        / 365.25
    )

    if years > 0:
        cagr = (
            (df.iloc[-1]["Investment Value"] / investment_amount)
            ** (1 / years)
            - 1
        ) * 100
    else:
        cagr = 0.0

    df["CAGR %"] = cagr
    df["Investment Years"] = years
    return df


# =============================================================================
# MAIN CHART
# =============================================================================

def plot_multi_fund_growth(comparison_data, investment_amount, benchmark_data=None, benchmark_name=None):
    if not comparison_data:
        return None

    colors = [
        "#1479FF",
        "#E91E63",
        "#16A085",
        "#F39C12",
        "#7B2CBF",
        "#00A6A6",
        "#8E44AD",
        "#D35400",
    ]

    fig = plt.figure(
        figsize=(19, 8.4),
        dpi=120,
        facecolor="white",
    )

    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[6.7, 2.35],
        wspace=0.045,
    )

    ax = fig.add_subplot(gs[0, 0])
    performance_ax = fig.add_subplot(gs[0, 1])

    all_dates = []
    all_values = []

    for item in comparison_data:
        df = item["data"]

        if df.empty:
            continue

        all_dates.extend(df["Date"].tolist())
        all_values.extend(df["Investment Value"].tolist())

    if benchmark_data is not None and not benchmark_data.empty:
        all_dates.extend(benchmark_data["Date"].tolist())
        all_values.extend(benchmark_data["Investment Value"].tolist())

    if not all_dates:
        plt.close(fig)
        return None

    min_date = min(all_dates)
    max_date = max(all_dates)

    min_value = min(all_values)
    max_value = max(all_values)

    value_range = max_value - min_value

    if value_range <= 0:
        value_range = investment_amount * 0.10

    y_padding = value_range * 0.08

    y_min = (
        min(min_value, investment_amount) - y_padding
    )

    y_max = (
        max(max_value, investment_amount) + y_padding
    )

    ax.set_ylim(y_min, y_max)

    date_range = max_date - min_date

    if date_range.total_seconds() <= 0:
        date_range = timedelta(days=30)

    ax.set_xlim(
        min_date - date_range * 0.015,
        max_date + date_range * 0.008,
    )

    performance_rows = []

    for index, item in enumerate(comparison_data):
        df = item["data"]

        if df.empty:
            continue

        color = colors[index % len(colors)]

        ax.fill_between(
            df["Date"].values,
            investment_amount,
            df["Investment Value"].values,
            facecolor=color,
            edgecolor="none",
            alpha=0.10,
            linewidth=0,
            antialiased=True,
            interpolate=True,
            zorder=1,
        )

        ax.plot(
            df["Date"],
            df["Investment Value"],
            color=color,
            linewidth=2.8,
            linestyle="-",
            solid_capstyle="round",
            solid_joinstyle="round",
            antialiased=True,
            zorder=5,
        )

        final_value = float(df.iloc[-1]["Investment Value"])
        final_cagr = float(df.iloc[-1]["CAGR %"])

        ax.scatter(
            [df.iloc[-1]["Date"]],
            [final_value],
            s=72,
            color=color,
            edgecolor="white",
            linewidth=2,
            zorder=10,
        )

        performance_rows.append({
            "display_name": item["display_name"],
            "wrapped_name": wrap_fund_name(
                item["display_name"],
                max_chars=25,
            ),
            "value": final_value,
            "cagr": final_cagr,
            "color": color,
        })

    # Benchmark: solid black line, no shading.
    if benchmark_data is not None and not benchmark_data.empty:
        ax.plot(
            benchmark_data["Date"],
            benchmark_data["Investment Value"],
            color="#111111",
            linewidth=3.4,
            linestyle="-",
            solid_capstyle="round",
            zorder=7,
        )

        ax.scatter(
            [benchmark_data.iloc[-1]["Date"]],
            [float(benchmark_data.iloc[-1]["Investment Value"])],
            s=78,
            color="#111111",
            edgecolor="white",
            linewidth=2,
            zorder=11,
        )

    ax.axhline(
        y=investment_amount,
        color="#7B8794",
        linestyle="--",
        linewidth=1.2,
        alpha=0.85,
        zorder=2,
    )

    ax.set_ylabel(
        "Investment Value (₹)",
        fontsize=16,
        fontweight="bold",
        color="#40566F",
        labelpad=12,
    )

    ax.yaxis.set_major_formatter(
        FuncFormatter(lambda x, pos: f"₹{x:,.0f}")
    )

    total_months = (
        (max_date.year - min_date.year) * 12
        + (max_date.month - min_date.month)
    )

    if total_months >= 60:
        interval = 6
    elif total_months >= 36:
        interval = 4
    elif total_months >= 24:
        interval = 3
    elif total_months >= 12:
        interval = 2
    else:
        interval = 1

    ax.xaxis.set_major_locator(
        mdates.MonthLocator(interval=interval)
    )

    ax.xaxis.set_major_formatter(
        mdates.DateFormatter("%b %Y")
    )

    ax.grid(
        True,
        which="major",
        axis="both",
        linestyle="--",
        linewidth=0.95,
        color="#B8C4D0",
        alpha=0.85,
        zorder=0,
    )

    ax.set_axisbelow(True)

    ax.tick_params(
        axis="x",
        labelsize=10,
        colors="#52627A",
        length=0,
        pad=8,
    )

    ax.tick_params(
        axis="y",
        labelsize=12,
        colors="#52627A",
        length=0,
        pad=8,
    )

    for label in ax.get_xticklabels():
        label.set_fontweight("bold")

    for label in ax.get_yticklabels():
        label.set_fontweight("bold")

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.spines["left"].set_color("#AAB7C4")
    ax.spines["bottom"].set_color("#AAB7C4")

    ax.spines["left"].set_linewidth(1.2)
    ax.spines["bottom"].set_linewidth(1.2)

    performance_ax.axis("off")

    performance_ax.plot(
        [0.02, 0.02],
        [0.02, 0.97],
        transform=performance_ax.transAxes,
        color="#D1D9E2",
        linewidth=1.3,
    )

    performance_ax.text(
        0.09,
        0.94,
        "Final Performance",
        transform=performance_ax.transAxes,
        fontsize=21,
        fontweight="bold",
        color="#142B52",
        ha="left",
        va="top",
    )

    performance_ax.text(
        0.09,
        0.895,
        f"₹{investment_amount:,.0f} initial investment",
        transform=performance_ax.transAxes,
        fontsize=13,
        fontweight="bold",
        color="#667B96",
        ha="left",
        va="top",
    )

    if benchmark_data is not None and not benchmark_data.empty:
        benchmark_final = float(benchmark_data.iloc[-1]["Investment Value"])
        benchmark_cagr = float(benchmark_data.iloc[-1]["CAGR %"])
        performance_ax.plot(
            [0.09, 0.15], [0.845, 0.845],
            transform=performance_ax.transAxes,
            color="#111111", linewidth=3.4, solid_capstyle="round"
        )
        performance_ax.text(
            0.175, 0.845,
            "Benchmark: " + (benchmark_name or "TRI"),
            transform=performance_ax.transAxes,
            fontsize=11.5, fontweight="bold", color="#263F62",
            ha="left", va="center"
        )
        performance_ax.text(
            0.885, 0.845 + 0.025,
            f"₹{benchmark_final:,.0f}",
            transform=performance_ax.transAxes,
            fontsize=13, fontweight="bold", color="#111111",
            ha="center", va="center"
        )
        performance_ax.text(
            0.885, 0.845 - 0.033,
            f"CAGR {benchmark_cagr:+.2f}%",
            transform=performance_ax.transAxes,
            fontsize=11, fontweight="bold", color="#111111",
            ha="center", va="center"
        )

    row_count = len(performance_rows)

    if row_count <= 3:
        start_y = 0.775
        row_gap = 0.215
    elif row_count == 4:
        start_y = 0.785
        row_gap = 0.185
    elif row_count == 5:
        start_y = 0.795
        row_gap = 0.155
    else:
        start_y = 0.805
        row_gap = 0.125

    for index, row in enumerate(performance_rows):
        y = start_y - index * row_gap

        performance_ax.scatter(
            0.105,
            y,
            s=230,
            color=row["color"],
            edgecolor="none",
            transform=performance_ax.transAxes,
            zorder=20,
        )

        performance_ax.text(
            0.175,
            y,
            row["wrapped_name"],
            transform=performance_ax.transAxes,
            fontsize=12.8,
            fontweight="bold",
            color="#263F62",
            ha="left",
            va="center",
            linespacing=1.10,
        )

        performance_ax.text(
            0.885,
            y + 0.025,
            f"₹{row['value']:,.0f}",
            transform=performance_ax.transAxes,
            fontsize=14,
            fontweight="bold",
            color=row["color"],
            ha="center",
            va="center",
        )

        performance_ax.text(
            0.885,
            y - 0.033,
            f"CAGR {row['cagr']:+.2f}%",
            transform=performance_ax.transAxes,
            fontsize=11.8,
            fontweight="bold",
            color=row["color"],
            ha="center",
            va="center",
        )

        if index < row_count - 1:
            separator_y = y - row_gap * 0.55

            performance_ax.plot(
                [0.075, 0.965],
                [separator_y, separator_y],
                transform=performance_ax.transAxes,
                color="#DCE3EA",
                linewidth=1.0,
            )

    plt.subplots_adjust(
        left=0.065,
        right=0.985,
        top=0.965,
        bottom=0.095,
    )

    return fig


# =============================================================================
# STREAMLIT UI
# =============================================================================

st.markdown(
    """
    <style>
    .main-title {
        text-align: center;
        color: #2c3e50;
        margin-bottom: 25px;
    }

    .section-title {
        color: #34495e;
        margin-top: 20px;
        margin-bottom: 10px;
    }

    .selected-box {
        border: 1px solid #bdc3c7;
        border-radius: 6px;
        padding: 12px;
        background: #ffffff;
    }

    div.stButton > button {
        border-radius: 6px;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<h1 class="main-title">Mutual Fund Comparison</h1>',
    unsafe_allow_html=True,
)

if not API_KEY:
    st.error(
        "FinAPI Key Not Found. Add your API key to Streamlit Secrets "
        "using the secret name `Finapi`."
    )
    st.stop()

# Session state
if "searched_schemes" not in st.session_state:
    st.session_state.searched_schemes = []

if "selected_comparison" not in st.session_state:
    st.session_state.selected_comparison = []

# =============================================================================
# STEP 1 - SEARCH
# =============================================================================

st.markdown(
    '<h3 class="section-title">STEP 1: Search Fund</h3>',
    unsafe_allow_html=True,
)

col1, col2 = st.columns([4, 1])

with col1:
    search_term = st.text_input(
        "Fund Name",
        placeholder="Enter Scheme Name",
        label_visibility="visible",
    )

with col2:
    st.write("")
    st.write("")
    search_clicked = st.button(
        "Search Schemes",
        type="primary",
        use_container_width=True,
    )

if search_clicked:
    if not search_term.strip():
        st.warning("Please enter a fund name.")
    else:
        with st.spinner("Searching schemes..."):
            results = search_fund(search_term.strip())

        st.session_state.searched_schemes = results

        if not results:
            st.warning(
                f"No schemes found for '{search_term.strip()}'."
            )
        else:
            st.success(
                f"Found {len(results)} available variant(s)."
            )

# =============================================================================
# STEP 2 - SELECT VARIANTS
# =============================================================================

st.markdown(
    '<h3 class="section-title">STEP 2: Select Scheme / Variant(s)</h3>',
    unsafe_allow_html=True,
)

scheme_options = []

used_names = set()

for index, scheme in enumerate(
    st.session_state.searched_schemes
):
    scheme_name = scheme.get(
        "schemeName",
        "Unknown Scheme",
    )

    plan_name = scheme.get("planName", "")
    option_name = scheme.get("optionName", "")
    scheme_code = scheme.get("schemeCode", "")

    parts = []

    if plan_name:
        parts.append(str(plan_name).strip())

    if option_name:
        parts.append(str(option_name).strip())

    if parts:
        display_name = (
            f"{scheme_name} - {' - '.join(parts)}"
        )
    else:
        display_name = scheme_name

    unique_name = display_name

    if unique_name in used_names:
        if scheme_code:
            unique_name = (
                f"{display_name} [{scheme_code}]"
            )
        else:
            unique_name = (
                f"{display_name} [{index + 1}]"
            )

    counter = 2
    base_name = unique_name

    while unique_name in used_names:
        unique_name = f"{base_name} [{counter}]"
        counter += 1

    used_names.add(unique_name)

    scheme_options.append(
        {
            "label": unique_name,
            "scheme": scheme,
        }
    )

if scheme_options:
    selected_labels = st.multiselect(
        "Variants",
        options=[
            x["label"] for x in scheme_options
        ],
        default=[],
        help="Select one or more fund variants.",
    )

    col_add, col_clear = st.columns([1, 1])

    with col_add:
        add_clicked = st.button(
            "Add Selected to Comparison",
            type="primary",
            use_container_width=True,
        )

    with col_clear:
        clear_search_clicked = st.button(
            "Clear Search Results",
            use_container_width=True,
        )

    if clear_search_clicked:
        st.session_state.searched_schemes = []
        st.rerun()

    if add_clicked:
        added_count = 0

        selected_map = {
            x["label"]: x["scheme"]
            for x in scheme_options
        }

        for label in selected_labels:
            scheme = selected_map[label]

            scheme_code = scheme.get(
                "schemeCode",
                "",
            )

            scheme_name = scheme.get(
                "schemeName",
                "Unknown Scheme",
            )

            plan_name = scheme.get(
                "planName",
                "",
            )

            option_name = scheme.get(
                "optionName",
                "",
            )

            name_parts = [
                str(scheme_name).strip(),
                str(plan_name).strip(),
                str(option_name).strip(),
            ]

            name_parts = [
                x for x in name_parts if x
            ]

            display_name = " - ".join(name_parts)

            already_exists = any(
                str(item.get("schemeCode", ""))
                == str(scheme_code)
                for item in st.session_state.selected_comparison
            )

            if already_exists:
                continue

            st.session_state.selected_comparison.append(
                {
                    "schemeCode": scheme_code,
                    "schemeName": scheme_name,
                    "planName": plan_name,
                    "optionName": option_name,
                    "display_name": display_name,
                    "scheme": scheme,
                }
            )

            added_count += 1

        if added_count:
            st.success(
                f"{added_count} variant(s) added successfully."
            )
        else:
            st.info(
                "No new variants were added. "
                "They may already be in the comparison."
            )

# =============================================================================
# SELECTED FUNDS
# =============================================================================

st.markdown(
    '<h3 class="section-title">Selected Funds</h3>',
    unsafe_allow_html=True,
)

if not st.session_state.selected_comparison:
    st.info("No funds selected yet.")
else:
    selected_names = [
        item["display_name"]
        for item in st.session_state.selected_comparison
    ]

    st.markdown(
        '<div class="selected-box">',
        unsafe_allow_html=True,
    )

    st.write(
        f"**{len(selected_names)} fund(s) selected:**"
    )

    for index, name in enumerate(
        selected_names,
        1,
    ):
        st.write(f"{index}. {name}")

    st.markdown("</div>", unsafe_allow_html=True)

    if st.button(
        "Clear All Selected Funds",
        type="secondary",
    ):
        st.session_state.selected_comparison = []
        st.rerun()

# =============================================================================
# INVESTMENT PERIOD
# =============================================================================

st.markdown(
    '<h3 class="section-title">Investment Period</h3>',
    unsafe_allow_html=True,
)

today = datetime.now().date()
one_year_ago = today - timedelta(days=365)

date_col1, date_col2 = st.columns(2)

with date_col1:
    start_date_value = st.date_input(
        "Start Date",
        value=one_year_ago,
    )

with date_col2:
    end_date_value = st.date_input(
        "End Date",
        value=today,
    )

# =============================================================================
# INVESTMENT AMOUNT
# =============================================================================

st.markdown(
    '<h3 class="section-title">Investment Amount</h3>',
    unsafe_allow_html=True,
)

investment_amount = st.number_input(
    "Amount (₹)",
    min_value=1.0,
    value=10000.0,
    step=1000.0,
    format="%.0f",
)

# =============================================================================
# BENCHMARK SELECTION
# =============================================================================

st.markdown(
    '<h3 class="section-title">Benchmark Comparison</h3>',
    unsafe_allow_html=True,
)

benchmark_type_col, benchmark_index_col = st.columns(2)

with benchmark_type_col:
    benchmark_type = st.selectbox(
        "Benchmark Type",
        ["Broad Market Index", "Strategy Index"],
        index=0,
    )

with benchmark_index_col:
    benchmark_index = st.selectbox(
        "Benchmark Index (TRI)",
        BENCHMARKS[benchmark_type],
        index=0,
        help="Benchmark uses the official Nifty Total Return Index (TRI), which includes reinvested dividends.",
    )

# =============================================================================
# CALCULATE
# =============================================================================

st.markdown("---")

calculate_clicked = st.button(
    "Calculate & Plot",
    type="primary",
    use_container_width=True,
)

if calculate_clicked:
    if not st.session_state.selected_comparison:
        st.error(
            "Please add at least one fund to the comparison."
        )
        st.stop()

    if start_date_value >= end_date_value:
        st.error(
            "End date must be after start date."
        )
        st.stop()

    if investment_amount <= 0:
        st.error(
            "Investment amount must be greater than zero."
        )
        st.stop()

    start_date = start_date_value.strftime("%Y-%m-%d")
    end_date = end_date_value.strftime("%Y-%m-%d")

    comparison_data = []
    errors = []

    progress = st.progress(0)
    status_text = st.empty()

    total_funds = len(
        st.session_state.selected_comparison
    )

    for index, item in enumerate(
        st.session_state.selected_comparison
    ):
        scheme_code = item.get(
            "schemeCode",
            "",
        )

        display_name = item.get(
            "display_name",
            "Unknown",
        )

        status_text.write(
            f"Processing {index + 1}/{total_funds}: "
            f"{display_name}"
        )

        if not scheme_code:
            errors.append(
                f"{display_name}: Scheme code unavailable."
            )
            continue

        try:
            nav_response = get_nav_history(
                scheme_code,
                start_date,
                end_date,
            )

            if not nav_response:
                errors.append(
                    f"{display_name}: NAV unavailable."
                )
                continue

            nav_df = extract_nav_dataframe(
                nav_response
            )

            if nav_df is None:
                errors.append(
                    f"{display_name}: Could not read NAV data."
                )
                continue

            if len(nav_df) < 2:
                errors.append(
                    f"{display_name}: Insufficient NAV data."
                )
                continue

            growth_df = calculate_growth(
                nav_df,
                investment_amount,
            )

            if growth_df is None:
                errors.append(
                    f"{display_name}: Could not calculate growth."
                )
                continue

            comparison_data.append(
                {
                    "display_name": display_name,
                    "schemeCode": scheme_code,
                    "data": growth_df,
                }
            )

        except Exception as e:
            errors.append(
                f"{display_name}: {e}"
            )

        progress.progress(
            (index + 1) / total_funds
        )

    status_text.empty()
    progress.empty()

    # Fetch benchmark TRI for the same investment period.
    benchmark_growth = None
    benchmark_error = None
    try:
        benchmark_tri = get_nifty_tri_history(
            benchmark_index,
            start_date,
            end_date,
        )
        benchmark_growth = calculate_benchmark_growth(
            benchmark_tri,
            investment_amount,
        )
        if benchmark_growth is None:
            benchmark_error = f"{benchmark_index}: TRI data unavailable or insufficient for the selected period."
    except Exception as e:
        benchmark_error = f"{benchmark_index}: {e}"

    if benchmark_error:
        errors.append(benchmark_error)

    if errors:
        with st.expander("Processing Messages"):
            for error in errors:
                st.warning(error)

    if not comparison_data:
        st.error(
            "No selected fund could be processed."
        )
        st.stop()

    # Summary metrics
    st.markdown(
        "### Comparison Results"
    )

    metric_cols = st.columns(
        min(len(comparison_data), 4)
    )

    for index, item in enumerate(comparison_data):
        df = item["data"]

        final_value = float(
            df.iloc[-1]["Investment Value"]
        )

        cagr = float(
            df.iloc[-1]["CAGR %"]
        )

        with metric_cols[index % len(metric_cols)]:
            st.metric(
                label=clean_fund_name(
                    item["display_name"]
                ),
                value=f"₹{final_value:,.0f}",
                delta=f"CAGR {cagr:+.2f}%",
            )

    # Chart
    fig = plot_multi_fund_growth(
        comparison_data,
        investment_amount,
        benchmark_data=benchmark_growth,
        benchmark_name=benchmark_index,
    )

    if fig is not None:
        st.pyplot(
            fig,
            use_container_width=True,
        )
        plt.close(fig)

    # Detailed table
    st.markdown("### Final Performance")

    performance_table = []

    for item in comparison_data:
        df = item["data"]

        final_value = float(
            df.iloc[-1]["Investment Value"]
        )

        cagr = float(
            df.iloc[-1]["CAGR %"]
        )

        total_return = float(
            df.iloc[-1]["Total Return %"]
        )

        performance_table.append(
            {
                "Fund": clean_fund_name(
                    item["display_name"]
                ),
                "Initial Investment": investment_amount,
                "Final Value": final_value,
                "Total Return": total_return,
                "CAGR": cagr,
            }
        )

    if benchmark_growth is not None:
        performance_table.append(
            {
                "Fund": f"Benchmark - {benchmark_index} TRI",
                "Initial Investment": investment_amount,
                "Final Value": float(benchmark_growth.iloc[-1]["Investment Value"]),
                "Total Return": float(benchmark_growth.iloc[-1]["Total Return %"]),
                "CAGR": float(benchmark_growth.iloc[-1]["CAGR %"]),
            }
        )

    performance_df = pd.DataFrame(
        performance_table
    )

    st.dataframe(
        performance_df.style.format(
            {
                "Initial Investment": "₹{:,.0f}",
                "Final Value": "₹{:,.0f}",
                "Total Return": "{:+.2f}%",
                "CAGR": "{:+.2f}%",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
