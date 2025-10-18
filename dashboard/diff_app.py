"""Streamlit app to visualize before/after verification differences."""
from pathlib import Path
from typing import Optional

import pandas as pd
import pydeck as pdk
import streamlit as st

DEFAULT_CURRENT = Path("data/processed/verified_poles_multi_source.csv")
HISTORY_DIR = Path("outputs/history")


def load_csv(path: Optional[Path]) -> Optional[pd.DataFrame]:
    if path is None or not path.exists():
        return None
    return pd.read_csv(path)


def list_history() -> list[Path]:
    if not HISTORY_DIR.exists():
        return []
    return sorted(HISTORY_DIR.glob("*.csv"))


def compute_diff(baseline: pd.DataFrame, current: pd.DataFrame) -> pd.DataFrame:
    base = baseline[['pole_id', 'classification']].rename(columns={'classification': 'baseline_classification'})
    curr = current[['pole_id', 'classification', 'lat', 'lon']].rename(columns={'classification': 'current_classification'})
    merged = curr.merge(base, on='pole_id', how='left')
    merged['baseline_classification'] = merged['baseline_classification'].fillna('not_in_baseline')
    merged['changed'] = merged['baseline_classification'] != merged['current_classification']
    return merged


def render_map(diff_df: pd.DataFrame):
    if diff_df.empty:
        st.info("No pole differences to display.")
        return

    color_map = {
        'verified_good': [0, 128, 0, 160],
        'new_detection': [30, 136, 229, 160],
        'ai_only_verified': [30, 136, 229, 160],
        'in_question': [255, 152, 0, 160],
        'new_missing': [126, 87, 194, 160],
        'not_in_baseline': [158, 158, 158, 160]
    }

    diff_df = diff_df.copy()
    diff_df['color'] = diff_df['current_classification'].map(color_map).fillna([0, 0, 0, 120])
    diff_df['radius'] = diff_df['changed'].apply(lambda x: 90 if x else 50)

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=diff_df,
        pickable=True,
        get_position='[lon, lat]',
        get_fill_color='color',
        get_radius='radius'
    )

    view_state = pdk.ViewState(
        latitude=float(diff_df['lat'].mean()),
        longitude=float(diff_df['lon'].mean()),
        zoom=11,
    )

    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip={
        "text": "{pole_id}\nCurrent: {current_classification}\nPrevious: {baseline_classification}"
    }))


def main():
    st.set_page_config(page_title="Pole Verification Diff", layout="wide")
    st.title("Corridor Before/After Diff")

    history_files = list_history()

    current_file = st.sidebar.text_input("Current verification CSV", str(DEFAULT_CURRENT))
    baseline_option = st.sidebar.selectbox(
        "Baseline file",
        options=["(upload)"] + [str(p) for p in history_files],
        index=0
    )

    baseline_df = None
    if baseline_option != "(upload)":
        baseline_df = load_csv(Path(baseline_option))
    else:
        uploaded = st.sidebar.file_uploader("Upload baseline CSV", type="csv")
        if uploaded is not None:
            baseline_df = pd.read_csv(uploaded)

    current_df = load_csv(Path(current_file))

    if current_df is None:
        st.error("Could not load current verification dataset.")
        return

    if baseline_df is None:
        st.warning("Provide a baseline dataset to compute diffs.")
        st.dataframe(current_df.head())
        return

    diff_df = compute_diff(baseline_df, current_df)

    st.subheader("Summary")
    metrics = (
        diff_df['current_classification']
        .value_counts()
        .rename_axis('classification')
        .reset_index(name='count')
    )
    st.table(metrics)

    changed = diff_df[diff_df['changed']]
    st.metric("Poles changed classification", len(changed))

    st.subheader("Map")
    render_map(diff_df)

    st.subheader("Changed Poles")
    st.dataframe(changed[['pole_id', 'baseline_classification', 'current_classification']])


if __name__ == "__main__":
    main()
