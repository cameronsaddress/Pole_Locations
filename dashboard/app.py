"""
Streamlit Dashboard for Verizon Pole Verification System
"""
import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import json
import sys

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / 'src'))
from config import (
    DASHBOARD_TITLE, PROCESSED_DATA_DIR, EXPORTS_OUTPUT_DIR,
    VERIFIED_CONFIDENCE_THRESHOLD
)
from mapillary_labeler import render_mapillary_labeler

# Page configuration
st.set_page_config(
    page_title=DASHBOARD_TITLE,
    page_icon="📍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #CC0000;
        margin-bottom: 0.5rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #CC0000;
    }
    .status-verified {
        color: #00AA00;
        font-weight: 600;
    }
    .status-question {
        color: #FFAA00;
        font-weight: 600;
    }
    .status-missing {
        color: #CC0000;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_processed_poles():
    """Load processed pole data"""
    pole_file = PROCESSED_DATA_DIR / 'poles_processed.geojson'
    if pole_file.exists():
        return gpd.read_file(pole_file)
    return None


@st.cache_data
def load_classification_results():
    """Load classification results if available"""
    results = {}
    for category in ['verified_good', 'in_question', 'new_missing']:
        filepath = EXPORTS_OUTPUT_DIR / f'{category}.csv'
        if filepath.exists():
            results[category] = pd.read_csv(filepath)
    return results if results else None


@st.cache_data
def load_summary_metrics():
    """Load summary metrics"""
    summary_file = EXPORTS_OUTPUT_DIR / 'summary_metrics.json'
    if summary_file.exists():
        with open(summary_file, 'r') as f:
            return json.load(f)
    return None


def create_map(poles_gdf, center_lat=40.0, center_lon=-75.0):
    """Create Folium map with pole locations"""
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=7,
        tiles='OpenStreetMap'
    )

    # Add poles as markers (sample for performance)
    sample_size = min(1000, len(poles_gdf))
    sample_poles = poles_gdf.sample(n=sample_size) if len(poles_gdf) > sample_size else poles_gdf

    for idx, pole in sample_poles.iterrows():
        # Color by status
        color_map = {
            'verified': 'green',
            'needs_repair': 'orange',
            'damaged': 'red',
            'replaced': 'blue'
        }
        color = color_map.get(pole.get('status', 'unknown'), 'gray')

        folium.CircleMarker(
            location=[pole.geometry.y, pole.geometry.x],
            radius=4,
            popup=f"""
                <b>Pole ID:</b> {pole.get('pole_id', 'N/A')}<br>
                <b>Status:</b> {pole.get('status', 'N/A')}<br>
                <b>Inspection:</b> {pole.get('inspection_date', 'N/A')}<br>
                <b>Location:</b> {pole.geometry.y:.4f}, {pole.geometry.x:.4f}
            """,
            color=color,
            fill=True,
            fillColor=color,
            fillOpacity=0.7
        ).add_to(m)

    return m


def main():
    """Main dashboard application"""

    # Header
if "polevision_mode" not in st.session_state:
    st.session_state["polevision_mode"] = "dashboard"

header_cols = st.columns([0.75, 0.25])
with header_cols[0]:
    st.markdown(f'<div class="main-header">{DASHBOARD_TITLE}</div>', unsafe_allow_html=True)
    if st.session_state["polevision_mode"] == "labeler":
        st.markdown("**Mapillary Label Review**")
    else:
        st.markdown("**AI-Powered Automation for East Coast Pole Verification**")

with header_cols[1]:
    if st.session_state["polevision_mode"] == "labeler":
        if st.button("← Back to Dashboard", use_container_width=True):
            st.session_state["polevision_mode"] = "dashboard"
            st.experimental_rerun()
    else:
        if st.button("Mapillary Labeler", use_container_width=True):
            st.session_state["polevision_mode"] = "labeler"
            st.experimental_rerun()

st.markdown("---")

if st.session_state["polevision_mode"] == "labeler":
    render_mapillary_labeler(include_title=False)
    st.stop()

    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Select View",
        ["Overview", "Data Explorer", "Review Queue", "Analytics", "Export"]
    )

    # Load data
    poles_gdf = load_processed_poles()
    classifications = load_classification_results()
    summary = load_summary_metrics()

    if page == "Overview":
        st.header("System Overview")

        # Metrics row
        col1, col2, col3, col4 = st.columns(4)

        if poles_gdf is not None:
            with col1:
                st.metric("Total Poles", f"{len(poles_gdf):,}")

            if summary:
                with col2:
                    st.metric(
                        "Automated Verification",
                        f"{summary['automation_rate']:.1f}%",
                        delta=f"{summary['verified_good']:,} poles"
                    )
                with col3:
                    st.metric(
                        "Review Queue",
                        f"{summary['review_queue_rate']:.1f}%",
                        delta=f"{summary['in_question']:,} poles"
                    )
                with col4:
                    cost_saved = summary['verified_good'] * 5  # $5 per manual inspection
                    st.metric(
                        "Cost Savings",
                        f"${cost_saved:,}",
                        delta="vs. manual inspection"
                    )
            else:
                with col2:
                    st.info("Run classification pipeline to see automation metrics")
                with col3:
                    st.info("Review queue will appear after classification")
                with col4:
                    st.info("Cost savings calculated post-classification")

        # Map
        st.subheader("Geographic Distribution")

        if poles_gdf is not None and len(poles_gdf) > 0:
            # Calculate center
            center_lat = poles_gdf.geometry.y.mean()
            center_lon = poles_gdf.geometry.x.mean()

            map_obj = create_map(poles_gdf, center_lat, center_lon)
            st_folium(map_obj, width=1200, height=600)

            st.caption(f"Showing sample of {min(1000, len(poles_gdf)):,} poles for performance")
        else:
            st.warning("No pole data loaded. Run data ingestion pipeline first.")

        # Status distribution
        if poles_gdf is not None:
            st.subheader("Pole Status Distribution")

            col1, col2 = st.columns(2)

            with col1:
                status_counts = poles_gdf['status'].value_counts()
                fig = px.pie(
                    values=status_counts.values,
                    names=status_counts.index,
                    title="Historical Status",
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                state_counts = poles_gdf['state'].value_counts()
                fig = px.bar(
                    x=state_counts.index,
                    y=state_counts.values,
                    title="Poles by State",
                    labels={'x': 'State', 'y': 'Count'},
                    color=state_counts.values,
                    color_continuous_scale='Reds'
                )
                st.plotly_chart(fig, use_container_width=True)

    elif page == "Data Explorer":
        st.header("Pole Data Explorer")

        if poles_gdf is not None:
            # Filters
            col1, col2, col3 = st.columns(3)

            with col1:
                state_filter = st.multiselect(
                    "Filter by State",
                    options=sorted(poles_gdf['state'].unique()),
                    default=None
                )

            with col2:
                status_filter = st.multiselect(
                    "Filter by Status",
                    options=sorted(poles_gdf['status'].dropna().unique()),
                    default=None
                )

            with col3:
                date_range = st.date_input(
                    "Inspection Date Range",
                    value=None
                )

            # Apply filters
            filtered_gdf = poles_gdf.copy()

            if state_filter:
                filtered_gdf = filtered_gdf[filtered_gdf['state'].isin(state_filter)]

            if status_filter:
                filtered_gdf = filtered_gdf[filtered_gdf['status'].isin(status_filter)]

            st.info(f"Showing {len(filtered_gdf):,} of {len(poles_gdf):,} poles")

            # Data table
            st.dataframe(
                filtered_gdf.drop(columns=['geometry']).head(1000),
                use_container_width=True,
                height=400
            )

            # Download button
            csv = filtered_gdf.drop(columns=['geometry']).to_csv(index=False)
            st.download_button(
                label="Download Filtered Data (CSV)",
                data=csv,
                file_name="filtered_poles.csv",
                mime="text/csv"
            )

        else:
            st.warning("No pole data loaded.")

    elif page == "Review Queue":
        st.header("Pole Review Queue")

        if classifications and 'in_question' in classifications:
            in_question = classifications['in_question']

            st.info(f"**{len(in_question)} poles require human review**")

            # Priority filter
            priority_filter = st.slider(
                "Minimum Priority Score",
                min_value=0.0,
                max_value=1.0,
                value=0.3,
                step=0.1,
                help="Higher scores indicate more urgent review"
            )

            filtered_queue = in_question[in_question['review_priority'] >= priority_filter]

            st.write(f"**{len(filtered_queue)} high-priority poles**")

            # Review interface
            for idx, pole in filtered_queue.head(10).iterrows():
                with st.expander(f"🔍 {pole['pole_id']} - Priority: {pole['review_priority']:.2f}"):
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.write("**Detection Info**")
                        st.write(f"Confidence: {pole['detection_confidence']:.2f}")
                        st.write(f"Location: {pole['detection_lat']:.4f}, {pole['detection_lon']:.4f}")

                    with col2:
                        st.write("**Historical Record**")
                        st.write(f"Status: {pole['historical_status']}")
                        st.write(f"Inspection: {pole['inspection_date']}")
                        st.write(f"Match Distance: {pole['match_distance_m']:.1f}m")

                    with col3:
                        st.write("**Combined Score**")
                        st.write(f"Overall: {pole['combined_confidence']:.2f}")
                        st.write(f"Recency: {pole['recency_weight']:.2f}")

                    # Review actions
                    action_col1, action_col2, action_col3 = st.columns(3)

                    with action_col1:
                        if st.button("✅ Approve", key=f"approve_{idx}"):
                            st.success(f"Pole {pole['pole_id']} approved!")

                    with action_col2:
                        if st.button("❌ Reject", key=f"reject_{idx}"):
                            st.error(f"Pole {pole['pole_id']} flagged for field inspection")

                    with action_col3:
                        if st.button("⏭️ Skip", key=f"skip_{idx}"):
                            st.info("Moved to next pole")

        else:
            st.warning("No review queue data. Run the classification pipeline first.")

    elif page == "Analytics":
        st.header("Performance Analytics")

        if summary and classifications:
            # Performance metrics
            col1, col2 = st.columns(2)

            with col1:
                # Automation funnel
                funnel_data = {
                    'Stage': ['Total Poles', 'Verified Good', 'Review Queue', 'New/Missing'],
                    'Count': [
                        summary['total_poles'],
                        summary['verified_good'],
                        summary['in_question'],
                        summary['new_missing']
                    ]
                }

                fig = go.Figure(go.Funnel(
                    y=funnel_data['Stage'],
                    x=funnel_data['Count'],
                    textinfo="value+percent initial"
                ))
                fig.update_layout(title="Automation Funnel")
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                # Confidence distribution
                if 'verified_good' in classifications:
                    verified = classifications['verified_good']
                    fig = px.histogram(
                        verified,
                        x='combined_confidence',
                        nbins=20,
                        title="Confidence Score Distribution (Verified)",
                        labels={'combined_confidence': 'Combined Confidence'}
                    )
                    st.plotly_chart(fig, use_container_width=True)

            # ROI Calculator
            st.subheader("Cost Savings Calculator")

            col1, col2, col3 = st.columns(3)

            with col1:
                manual_cost = st.number_input("Cost per Manual Inspection ($)", value=5, step=1)

            with col2:
                ai_cost = st.number_input("Cost per AI Verification ($)", value=0.03, step=0.01)

            with col3:
                total_savings = (summary['verified_good'] * manual_cost) - (summary['total_poles'] * ai_cost)
                st.metric("Total Savings", f"${total_savings:,.2f}")

        else:
            st.warning("Run classification pipeline to see analytics.")

    elif page == "Export":
        st.header("Data Export")

        st.write("Download processed data and reports for integration with Verizon systems.")

        if classifications:
            col1, col2, col3 = st.columns(3)

            with col1:
                st.subheader("Verified Good Poles")
                if 'verified_good' in classifications:
                    verified = classifications['verified_good']
                    st.metric("Count", f"{len(verified):,}")

                    csv = verified.to_csv(index=False)
                    st.download_button(
                        "Download CSV",
                        data=csv,
                        file_name="verified_good_poles.csv",
                        mime="text/csv"
                    )

            with col2:
                st.subheader("Review Queue")
                if 'in_question' in classifications:
                    in_question = classifications['in_question']
                    st.metric("Count", f"{len(in_question):,}")

                    csv = in_question.to_csv(index=False)
                    st.download_button(
                        "Download CSV",
                        data=csv,
                        file_name="review_queue.csv",
                        mime="text/csv"
                    )

            with col3:
                st.subheader("New/Missing Poles")
                if 'new_missing' in classifications:
                    new_missing = classifications['new_missing']
                    st.metric("Count", f"{len(new_missing):,}")

                    csv = new_missing.to_csv(index=False)
                    st.download_button(
                        "Download CSV",
                        data=csv,
                        file_name="new_missing_poles.csv",
                        mime="text/csv"
                    )

            # Summary report
            st.subheader("Summary Report")

            if summary:
                report = f"""
# Pole Verification Summary Report

## Overall Metrics
- **Total Poles Processed:** {summary['total_poles']:,}
- **Verified Good:** {summary['verified_good']:,} ({summary['automation_rate']:.1f}%)
- **Review Queue:** {summary['in_question']:,} ({summary['review_queue_rate']:.1f}%)
- **New/Missing:** {summary['new_missing']:,}

## Performance
- **Automation Rate:** {summary['automation_rate']:.1f}%
- **Manual Review Required:** {summary['review_queue_rate']:.1f}%

## Cost Savings (at $5/pole manual inspection)
- **Automated:** ${summary['verified_good'] * 5:,}
- **Estimated AI Cost:** ${summary['total_poles'] * 0.03:,.2f}
- **Net Savings:** ${(summary['verified_good'] * 5) - (summary['total_poles'] * 0.03):,.2f}

---
Generated by PoleLocations AI System
"""
                st.download_button(
                    "Download Summary Report (Markdown)",
                    data=report,
                    file_name="pole_verification_summary.md",
                    mime="text/markdown"
                )

        else:
            st.warning("No export data available. Run classification pipeline first.")


if __name__ == "__main__":
    main()
