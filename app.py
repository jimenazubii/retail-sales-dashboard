"""
Retail Sales Dashboard (Streamlit).

Sales KPIs for a grocery retail chain (54 stores, 33 product families,
2013-2017), built for the CEO and the Head of Sales.

Run locally:
    streamlit run app.py
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

DATA_DIR = Path(__file__).resolve().parent / "data"
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PRIMARY = "#FF4B4B"
SECONDARY = "#1F77B4"
LABELS = {
    "sales": "Sales", "promo_sales": "Sales on promotion", "avg_sales": "Average sales",
    "transactions": "Transactions", "week": "Week of the year", "family": "Product family",
    "avg_daily_sales": "Average daily sales per store", "store_type": "Store type",
    "store": "Store", "year": "Year",
}
PLOT_LAYOUT = dict(margin=dict(l=10, r=10, t=40, b=10), height=380, template="plotly_white")


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Retail Sales Dashboard", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")


@st.cache_data
def load_data():
    """
    Load the pre-aggregated tables produced by scripts/prepare_data.py.

    - monthly: sales per store x product family x month
    - daily:   sales and transactions per store x day
    Each table keeps the number of underlying raw rows (`rows`), so averages
    are computed exactly as in the raw data (average sales per store, family and day).
    """
    monthly = pd.read_parquet(DATA_DIR / "sales_monthly.parquet")
    daily = pd.read_parquet(DATA_DIR / "store_daily.parquet")
    daily["year"] = daily["date"].dt.year
    daily["weekday"] = pd.Categorical(daily["date"].dt.day_name(), WEEKDAYS, ordered=True)
    daily["week"] = daily["date"].dt.isocalendar().week.astype(int)
    return monthly, daily


def fmt(value):
    """Format large numbers as 1.2M / 345.6K."""
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(value) >= size:
            return f"{value / size:,.1f}{unit}"
    return f"{value:,.0f}"


def weighted_mean(df, by):
    """Average sales per store, family and day, grouped by `by`."""
    g = df.groupby(by, observed=True)[["sales", "rows"]].sum()
    return (g["sales"] / g["rows"]).rename("avg_sales").reset_index()


def bar(df, x, y, title, horizontal=False, color=PRIMARY, **kwargs):
    """Bar chart with the dashboard's common style."""
    fig = px.bar(df, x=y if horizontal else x, y=x if horizontal else y, title=title,
                 orientation="h" if horizontal else "v", labels=LABELS, **kwargs)
    fig.update_traces(marker_color=color)
    fig.update_layout(**PLOT_LAYOUT)
    if horizontal:
        fig.update_yaxes(categoryorder="total ascending", title=None)
    return fig


monthly, daily = load_data()

st.title("📊 Retail Sales Dashboard")
st.markdown(
    "Year-end review of a grocery retail chain in Ecuador: sales by product, store and state, "
    "seasonality and the effect of promotions and holidays."
)

# ---------------------------------------------------------------------------
# Sidebar: global filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    all_years = sorted(daily["year"].unique())
    years = st.multiselect("Years", all_years, default=all_years)
    all_states = sorted(daily["state"].unique())
    if st.checkbox("All states", value=True):
        states = all_states
    else:
        states = st.multiselect("States", all_states, default=["Pichincha", "Guayas"])
    st.caption("Data from 1 Jan 2013 to 15 Aug 2017; 2017 covers only 7.5 months.")

m = monthly[monthly["year"].isin(years) & monthly["state"].isin(states)]
d = daily[daily["year"].isin(years) & daily["state"].isin(states)]

if m.empty:
    st.warning("No data for the selected filters. Try selecting other years or states.")
    st.stop()

tab1, tab2, tab3, tab4 = st.tabs(["🌍 Overview", "🏬 By store", "🗺️ By state", "💡 Insights"])

# ---------------------------------------------------------------------------
# Tab 1: overview
# ---------------------------------------------------------------------------
with tab1:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Stores", m["store_nbr"].nunique())
    c2.metric("Product families", m["family"].nunique())
    c3.metric("States", m["state"].nunique())
    c4.metric("Months of data", m[["year", "month"]].drop_duplicates().shape[0])
    c5.metric("Total sales", fmt(m["sales"].sum()))
    st.caption("The dataset has no individual product ID; *family* is used as the product.")

    st.subheader("Products and stores")
    col1, col2 = st.columns(2)
    with col1:
        top_products = m.groupby("family", observed=True)["sales"].sum().nlargest(10).reset_index()
        st.plotly_chart(bar(top_products, "family", "sales", "Top 10 product families by sales",
                            horizontal=True), width="stretch")
    with col2:
        by_store = m.groupby("store_nbr")["sales"].sum().sort_values(ascending=False).reset_index()
        by_store["store"] = "Store " + by_store["store_nbr"].astype(str)
        fig = bar(by_store, "store", "sales", "Sales distribution across stores (sorted)")
        fig.update_xaxes(showticklabels=False, title="Stores (sorted by sales)")
        st.plotly_chart(fig, width="stretch")

    top_promo = m.groupby("store_nbr")["promo_sales"].sum().nlargest(10).reset_index()
    top_promo["store"] = "Store " + top_promo["store_nbr"].astype(str)
    st.plotly_chart(bar(top_promo, "store", "promo_sales",
                        "Top 10 stores by sales of products on promotion",
                        horizontal=True, color=SECONDARY), width="stretch")

    st.subheader("Seasonality")
    st.caption("Average sales per store, product family and day.")
    col1, col2 = st.columns(2)
    with col1:
        by_day = weighted_mean(d, "weekday")
        best = by_day.loc[by_day["avg_sales"].idxmax(), "weekday"]
        colors = [PRIMARY if w == best else "#F4A6A6" for w in by_day["weekday"]]
        fig = px.bar(by_day, x="weekday", y="avg_sales", labels=LABELS, title="Average sales by day of the week")
        fig.update_traces(marker_color=colors)
        fig.update_layout(**PLOT_LAYOUT, xaxis_title=None)
        st.plotly_chart(fig, width="stretch")
        st.info(f"**{best}** is the day with the highest average sales.")
    with col2:
        by_week = weighted_mean(d, "week")
        fig = px.line(by_week, x="week", y="avg_sales", markers=True, labels=LABELS,
                      title="Average sales by week of the year (all years)")
        fig.update_traces(line_color=PRIMARY)
        fig.update_layout(**PLOT_LAYOUT)
        st.plotly_chart(fig, width="stretch")

    by_month = weighted_mean(m, "month")
    by_month["month_name"] = by_month["month"].map(lambda x: MONTHS[x - 1])
    fig = px.line(by_month, x="month_name", y="avg_sales", markers=True, labels=LABELS,
                  title="Average sales by month (all years)")
    fig.update_traces(line_color=PRIMARY)
    fig.update_layout(**PLOT_LAYOUT, xaxis_title=None)
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------
# Tab 2: by store
# ---------------------------------------------------------------------------
with tab2:
    stores = sorted(m["store_nbr"].unique())
    store = st.selectbox("Select a store", stores, format_func=lambda s: f"Store {s}")
    ms = m[m["store_nbr"] == store]
    info = daily.loc[daily["store_nbr"] == store, ["city", "state", "store_type"]].iloc[0]
    st.markdown(f"**Store {store}** · {info['city']}, {info['state']} · type {info['store_type']}")

    c1, c2, c3 = st.columns(3)
    total, promo = ms["sales"].sum(), ms["promo_sales"].sum()
    c1.metric("Products sold", fmt(total))
    c2.metric("Sold on promotion", fmt(promo))
    c3.metric("Share on promotion", f"{promo / total:.1%}" if total else "–")

    yearly = ms.groupby("year")[["sales", "promo_sales"]].sum().reset_index().sort_values("year")
    yearly["year"] = yearly["year"].astype(str)
    fig = go.Figure([
        go.Bar(x=yearly["year"], y=yearly["sales"] - yearly["promo_sales"], name="Not on promotion",
               marker_color="#F4A6A6"),
        go.Bar(x=yearly["year"], y=yearly["promo_sales"], name="On promotion", marker_color=PRIMARY),
    ])
    fig.update_layout(**PLOT_LAYOUT, barmode="stack", title="Sales per year (oldest to newest)",
                      legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"))
    st.plotly_chart(fig, width="stretch")
    st.caption("2017 only includes data up to 15 August.")

# ---------------------------------------------------------------------------
# Tab 3: by state
# ---------------------------------------------------------------------------
with tab3:
    state = st.selectbox("Select a state", sorted(m["state"].unique()))
    mst, dst = m[m["state"] == state], d[d["state"] == state]

    col1, col2 = st.columns(2)
    with col1:
        trans = dst.groupby("year")["transactions"].sum().reset_index()
        trans["year"] = trans["year"].astype(str)
        st.plotly_chart(bar(trans, "year", "transactions", f"Transactions per year in {state}",
                            color=SECONDARY), width="stretch")
    with col2:
        ranking = mst.groupby("store_nbr")["sales"].sum().sort_values(ascending=False).reset_index()
        ranking["store"] = "Store " + ranking["store_nbr"].astype(str)
        st.plotly_chart(bar(ranking, "store", "sales", f"Stores ranked by sales in {state}",
                            horizontal=True), width="stretch")

    leader = int(ranking.iloc[0]["store_nbr"])
    top_family = (mst[mst["store_nbr"] == leader].groupby("family", observed=True)["sales"]
                  .sum().nlargest(10).reset_index())
    st.success(f"Best-selling product in the leading store (**Store {leader}**): "
               f"**{top_family.iloc[0]['family']}**")
    st.plotly_chart(bar(top_family, "family", "sales", f"Top 10 product families in Store {leader}",
                        horizontal=True), width="stretch")

# ---------------------------------------------------------------------------
# Tab 4: insights
# ---------------------------------------------------------------------------
with tab4:
    st.subheader("Sales trend")
    trend = m.groupby(["year", "month"])["sales"].sum().reset_index()
    trend["date"] = pd.to_datetime(trend[["year", "month"]].assign(day=1))
    # August 2017 only has 15 days of data: drop it so it does not look like a sales drop
    days_per_month = daily.groupby(daily["date"].dt.to_period("M"))["date"].nunique()
    complete = days_per_month[days_per_month >= days_per_month.index.days_in_month - 1].index
    trend = trend[trend["date"].dt.to_period("M").isin(complete)]
    fig = px.line(trend, x="date", y="sales", labels=LABELS, title="Monthly sales")
    fig.update_traces(line_color=PRIMARY)
    fig.update_layout(**PLOT_LAYOUT, xaxis_title=None)
    st.plotly_chart(fig, width="stretch")
    st.caption("Only complete months are shown (August 2017 is excluded).")

    col1, col2 = st.columns(2)
    with col1:
        hol = d.groupby("is_holiday")[["sales", "rows"]].sum()
        hol = (hol["sales"] / hol["rows"]).rename("avg_sales").reset_index()
        hol["day_type"] = hol["is_holiday"].map({True: "Holiday / event", False: "Regular day"})
        fig = bar(hol, "day_type", "avg_sales", "Average sales: holidays vs regular days")
        fig.update_layout(xaxis_title=None)
        st.plotly_chart(fig, width="stretch")
        if len(hol) == 2:
            uplift = hol.set_index("is_holiday")["avg_sales"]
            st.info(f"Sales are **{uplift[True] / uplift[False] - 1:+.1%}** on holidays. "
                    "Each holiday is only applied to the stores where it is celebrated.")
    with col2:
        weekly = (d.groupby(pd.Grouper(key="date", freq="W"))
                  .agg(sales=("sales", "sum"), items_on_promo=("items_on_promo", "sum"),
                       days=("date", "nunique"))
                  .reset_index())
        weekly = weekly[weekly["days"] >= 6]  # drop the incomplete first and last weeks
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=weekly["date"], y=weekly["sales"], name="Sales",
                                 line_color=PRIMARY), secondary_y=False)
        fig.add_trace(go.Scatter(x=weekly["date"], y=weekly["items_on_promo"],
                                 name="Items on promotion", line_color=SECONDARY), secondary_y=True)
        fig.update_layout(**PLOT_LAYOUT, title="Weekly sales vs items on promotion",
                          legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"))
        fig.update_yaxes(title_text="Sales", secondary_y=False)
        fig.update_yaxes(title_text="Items on promotion", secondary_y=True)
        st.plotly_chart(fig, width="stretch")
        corr = weekly["sales"].corr(weekly["items_on_promo"])
        st.info(f"Weekly correlation between sales and promotions: **{corr:.2f}** "
                "(association, not causation: promotions grew over time together with sales).")

    st.subheader("Store types")
    # Each row of the daily table is one store-day
    by_type = (d.groupby("store_type", observed=True)["sales"].mean()
               .rename("avg_daily_sales").reset_index())
    st.plotly_chart(bar(by_type, "store_type", "avg_daily_sales",
                        "Average daily sales per store, by store type", color=SECONDARY),
                    width="stretch")
