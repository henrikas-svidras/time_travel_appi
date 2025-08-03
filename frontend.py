import folium
import streamlit as st
from streamlit_folium import st_folium
from datetime import datetime
import pytz

import backend as api

# -- session defaults --
defaults = dict(
    start_a=[52.52, 13.405],   # Berlin
    start_b=[52.50, 13.40],
    shapes=None,
    pois=[],
    route=[],
    directions=[],
    trip_summary="",
    common_shapes=None,
    common_pois=[],
)
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# -- tabs --
tab_single, tab_meet = st.tabs(["Single origin", "Meet-in-the-middle"])

# -------------------------------------------------------------
# TAB 1  –  single origin
# -------------------------------------------------------------
with tab_single:
    mode  = st.selectbox("Transport", list(api.Transport))
    tmin  = st.slider("Max travel time", 5, 60, 20, key="t1")
    when  = st.time_input("Departure", value=datetime.now().time(), key="d1")
    if st.button("Get area & POIs", key="btn1"):
        tz   = pytz.timezone("Europe/Berlin")
        dep  = datetime.now(tz).replace(hour=when.hour, minute=when.minute, second=0)
        sh   = api.reachable_shapes(tuple(st.session_state.start_a), mode, tmin, dep)
        st.session_state.shapes = sh
        st.session_state.pois   = api.pois_inside(sh)
        st.session_state.update(route=[], directions=[], trip_summary="")
        st.rerun()

    m = folium.Map(st.session_state.start_a, zoom_start=12)
    folium.Marker(st.session_state.start_a, icon=folium.Icon(color="red")).add_to(m)
    if st.session_state.shapes:
        for s in st.session_state.shapes:
            folium.Polygon([(p.lat, p.lng) for p in s.shell],
                           color="blue", fill=True,
                           weight=2, fill_opacity=0.3).add_to(m)
    for n, lat, lon in st.session_state.pois:
        folium.Marker([lat, lon], popup=n,
                      icon=folium.Icon(color="green")).add_to(m)
    if st.session_state.route:
        folium.PolyLine(st.session_state.route, color="red", weight=4).add_to(m)

    md = st_folium(m, height=500, key="map1")
    if md and md.get("last_clicked"):
        lat, lng = md["last_clicked"]["lat"], md["last_clicked"]["lng"]
        if (lat, lng) != tuple(st.session_state.start_a):
            st.session_state.update(
                start_a=[lat, lng],
                shapes=None, pois=[], route=[],
                directions=[], trip_summary=""
            )
            st.rerun()

    st.sidebar.markdown("### POIs")
    for i, (n, lat, lon) in enumerate(st.session_state.pois, 1):
        if st.sidebar.button(f"{i}. {n}", key=f"poi_{i}"):
            poly, dirs, sec, km = api.route_to(
                tuple(st.session_state.start_a), (lat, lon), mode
            )
            st.session_state.update(
                route=poly, directions=dirs,
                trip_summary=(
                    f'<div style="background:#29230d;padding:10px;margin-bottom:10px;'
                    f'border-radius:5px;font-size:18px;font-weight:bold;'
                    f'border:1px solid #f0c040;">'
                    f'🚶 {n} → {sec//60} min, {km:.2f} km</div>'
                ),
            )
            st.rerun()

    if st.session_state.trip_summary:
        st.markdown(st.session_state.trip_summary, unsafe_allow_html=True)
    if st.session_state.directions:
        st.markdown("### Directions")
        for i, d in enumerate(st.session_state.directions, 1):
            st.markdown(f"**{i}.** {d}")

# -------------------------------------------------------------
# TAB 2  –  common area between two origins 
# -------------------------------------------------------------
with tab_meet:
    st.write("### Pick the two starting points by clicking on the map")

    active_pin = st.radio(
        "Next click sets …",
        ["Start A", "Start B"],
        horizontal=True,
        key="active_pin",
    )

    # current parameters
    mode_m = st.selectbox("Transport", list(api.Transport), key="mode2")
    tmin_m = st.slider("Max travel time", 5, 60, 20, key="t2")
    when_m = st.time_input("Departure", value=datetime.now().time(), key="d2")

    # draw map
    m2 = folium.Map(
        [(st.session_state.start_a[0] + st.session_state.start_b[0]) / 2,
         (st.session_state.start_a[1] + st.session_state.start_b[1]) / 2],
        zoom_start=11,
    )
    folium.Marker(st.session_state.start_a, icon=folium.Icon(color="red")).add_to(m2)
    folium.Marker(st.session_state.start_b, icon=folium.Icon(color="orange")).add_to(m2)

    if st.session_state.common_shapes:
        for s in st.session_state.common_shapes:
            folium.Polygon([(p.lat, p.lng) for p in s.shell],
                           color="purple", fill=True,
                           weight=2, fill_opacity=0.3).add_to(m2)

    for n, lat, lon in st.session_state.common_pois:
        folium.Marker([lat, lon], popup=n,
                      icon=folium.Icon(color="green")).add_to(m2)

    if st.session_state.route:
        folium.PolyLine(st.session_state.route, color="red", weight=4).add_to(m2)

    # handle click
    md2 = st_folium(m2, height=500, key="map2")
    if md2 and md2.get("last_clicked"):
        lat, lng = md2["last_clicked"]["lat"], md2["last_clicked"]["lng"]

        if active_pin == "Start A":
            st.session_state.start_a = [lat, lng]
        else:
            st.session_state.start_b = [lat, lng]

        # moving a pin invalidates previous calculations
        st.session_state.update(
            common_shapes=None,
            common_pois=[],
            route=[], directions=[], trip_summary="",
        )
        st.rerun()

    # (re)compute intersection & POIs
    if st.button("Find common area", key="btn2"):
        tz   = pytz.timezone("Europe/Berlin")
        dep  = datetime.now(tz).replace(hour=when_m.hour, minute=when_m.minute, second=0)
        cs = api.intersection_shapes(
                tuple(st.session_state.start_a),
                tuple(st.session_state.start_b),
                mode_m, tmin_m, dep)
        st.session_state.common_shapes = cs
        st.session_state.common_pois   = api.pois_inside(cs)
        st.session_state.update(route=[], directions=[], trip_summary="")
        st.rerun()

