"""tps_view.py - Importador universal de dados do TPS.

O usuario anexa QUALQUER arquivo que tiver do TPS (.ALL, .dcm, .csv, .txt,
imagem) e o software identifica o formato e extrai o que houver: mapa de dose,
resolucao espacial, unidade, plano/corte, isodoses ou pontos. Nada e assumido:
o parser detecta e valida cada arquivo.
"""
import streamlit as st
from i18n import t, get_lang
from theme import COLORS
from auth import notify_user_activity


def tps_view(state, go):
    st.markdown(f"<div style='font-size:12px;color:{COLORS['text_muted']};margin-bottom:14px'>"
                f"{t('group_config')}</div>", unsafe_allow_html=True)

    st.markdown(f"**{t('tps_title')}**")
    st.caption(t("tps_hint"))

    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        import tps_parser as tp
        import numpy as np
    except Exception as e:
        st.error(f"Erro ao carregar o parser de TPS: {e}")
        return

    files = st.file_uploader(
        t("tps_upload"),
        type=["all", "dcm", "csv", "txt", "png", "jpg", "jpeg", "tif", "tiff"],
        accept_multiple_files=True,
        key="tps_files",
    )

    if not files:
        st.markdown(f"<div style='background:{COLORS['bg_surface']};border-radius:8px;"
                    f"padding:32px;text-align:center;color:{COLORS['text_muted']};font-size:12px'>"
                    f"{t('tps_waiting')}</div>", unsafe_allow_html=True)
        return

    # Acumula o que for extraido de cada arquivo
    extracted = state.setdefault("tps_extracted", {})
    dose_dists = []   # lista de DoseDistribution
    contours = []     # IsodoseContours
    points = []       # DosePoints

    for up in files:
        data = up.getvalue()
        name = up.name
        st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:12px 0'>",
                    unsafe_allow_html=True)
        st.markdown(f"**{name}**")
        try:
            fmt = tp.detect_format(data, filename=name)
        except Exception as e:
            st.warning(f"{t('tps_unreadable')}: {e}")
            continue

        st.caption(f"{t('tps_detected')}: `{fmt}`")

        try:
            result = tp.read_tps(data, filename=name)
        except Exception as e:
            st.warning(f"{t('tps_read_err')}: {e}")
            continue

        # DoseDistribution (mapa de dose)
        if hasattr(result, "dose") and hasattr(result, "resolution_mm"):
            s = result.summary()
            dose_dists.append((name, result))
            meta = result.metadata or {}

            cA, cB, cC = st.columns(3)
            cA.metric(t("tps_shape"), f"{s['shape'][0]}×{s['shape'][1]}")
            cB.metric(t("tps_res"), f"{s['resolution_mm']:.1f} mm")
            cC.metric(t("tps_maxdose"), f"{s['max_dose_cgy']:.0f} cGy")

            # Metadados extraidos do cabecalho (tudo que o arquivo traz)
            with st.expander(t("tps_metadata")):
                if meta.get("patient_id"):
                    st.caption(f"**{t('tps_patient')}:** {meta['patient_id']}")
                if meta.get("plane_desc"):
                    st.caption(f"**{t('tps_plane')}:** {meta['plane_desc']}")
                if meta.get("datetime"):
                    st.caption(f"**{t('tps_datetime')}:** {meta['datetime']}")
                if meta.get("dose_reference"):
                    st.caption(f"**{t('tps_doseref')}:** {meta['dose_reference']} ({meta.get('unit_source','?')})")
                if meta.get("upperleft_mm"):
                    ul = meta["upperleft_mm"]
                    st.caption(f"**{t('tps_origin')}:** ({ul[0]:.1f}, {ul[1]:.1f}) mm")
                if meta.get("calc_grid_mm"):
                    g = meta["calc_grid_mm"]
                    st.caption(f"**{t('tps_calcgrid')}:** {g[0]:.1f} × {g[1]:.1f} × {g[2]:.1f} mm")
                if meta.get("qa_plane_mm"):
                    q = meta["qa_plane_mm"]
                    st.caption(f"**{t('tps_qaplane')}:** {q[0]:.0f} × {q[1]:.0f} mm")
                # tamanho fisico real derivado da resolucao
                hmm = s['shape'][0] * s['resolution_mm']
                wmm = s['shape'][1] * s['resolution_mm']
                st.caption(f"**{t('tps_physize')}:** {wmm:.0f} × {hmm:.0f} mm "
                           f"({wmm/10:.1f} × {hmm/10:.1f} cm)")

            if meta.get("dims_match_declared") is False:
                st.warning(t("tps_dims_warn"))

            # Pre-visualizacao: mapa de dose E isodoses (lado a lado)
            try:
                from utils.dose_map_engine import render_dose_map_png
                dose_cgy_map = result.dose * 100.0  # interno Gy -> cGy
                pcol1, pcol2 = st.columns(2)
                with pcol1:
                    png = render_dose_map_png(dose_cgy_map, unit="cGy",
                                              lang=get_lang(), theme="dark",
                                              title=t("tps_dose_map"))
                    st.image(png, use_container_width=True)
                with pcol2:
                    # Isodoses do TPS, geradas pelo MESMO motor do filme.
                    try:
                        from isodose_engine import render_isodose_png, DEFAULT_CLINICAL_LEVELS
                        # base = % da dose maxima do proprio TPS (sem exigir Rx aqui)
                        iso_png = render_isodose_png(
                            dose_cgy_map, DEFAULT_CLINICAL_LEVELS, basis="max",
                            level_pcts=DEFAULT_CLINICAL_LEVELS, unit="cGy",
                            lang=get_lang(), theme="dark", linestyle="solid",
                            colormap="jet", show_background=True,
                            title=t("tps_isodose_preview"), smooth_sigma=1.0,
                        )
                        st.image(iso_png, use_container_width=True)
                    except Exception as e:
                        st.caption(f"({t('tps_iso_fail')}: {e})")
            except Exception as e:
                st.caption(f"({t('tps_preview_fail')}: {e})")

        # IsodoseContours
        elif hasattr(result, "contours") or result.__class__.__name__ == "IsodoseContours":
            contours.append((name, result))
            st.success(t("tps_got_isodose"))

        # DosePoints (pontos de dose do RTPLAN ou CSV)
        elif result.__class__.__name__ == "DosePoints":
            points.append((name, result))
            pts = result.points or []
            st.success(f"{t('tps_got_points')} ({len(pts)})")
            if pts:
                import pandas as pd
                rows = []
                for p in pts:
                    rows.append({
                        t("tps_pt_name"): p.get("name", "?"),
                        "X (mm)": p.get("x_mm"),
                        "Y (mm)": p.get("y_mm"),
                        "Z (mm)": p.get("z_mm"),
                        t("tps_pt_dose"): (f"{p.get('dose_gy')*100:.0f}"
                                           if p.get("dose_gy") is not None else "-"),
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Resumo geral
    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:16px 0'>",
                unsafe_allow_html=True)
    n_dose = len(dose_dists)
    st.markdown(f"**{t('tps_summary')}:** "
                f"{n_dose} {t('tps_dose_maps')}, {len(contours)} {t('tps_isodoses')}, "
                f"{len(points)} {t('tps_pointsets')}")

    # ── CRUZAMENTO: dose do TPS em cada ponto do filme ─────────────────────
    # Se temos um RTDOSE com volume 3D E pontos (do RTSTRUCT), calculamos a
    # dose planejada de cada ponto por interpolacao trilinear no volume.
    vol_dist = None
    for nm, d in dose_dists:
        meta = d.metadata or {}
        if meta.get("dose_volume_gy") is not None and meta.get("geometry"):
            vol_dist = d
            break

    all_points = []
    for nm, dp in points:
        all_points.extend(dp.points or [])

    if vol_dist is not None and all_points:
        st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:16px 0'>",
                    unsafe_allow_html=True)
        st.markdown(f"**{t('tps_pointdose_title')}**")
        st.caption(t("tps_pointdose_hint"))
        meta = vol_dist.metadata
        vol = meta["dose_volume_gy"]
        geom = meta["geometry"]
        import pandas as pd
        rows = []
        enriched = []
        for p in all_points:
            d_gy = None
            if p.get("x_mm") is not None:
                d_gy = tp.interpolate_dose_3d(vol, geom, p["x_mm"], p["y_mm"], p["z_mm"])
            q = dict(p); q["tps_dose_gy"] = d_gy
            enriched.append(q)
            rows.append({
                t("tps_pt_name"): p.get("name", "?"),
                "X (mm)": round(p.get("x_mm", 0), 1) if p.get("x_mm") is not None else "-",
                "Y (mm)": round(p.get("y_mm", 0), 1) if p.get("y_mm") is not None else "-",
                "Z (mm)": round(p.get("z_mm", 0), 1) if p.get("z_mm") is not None else "-",
                t("tps_pt_planned"): f"{d_gy*100:.1f}" if d_gy is not None else "-",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        state["tps_points_dose"] = enriched

        # Mostra o PLANO CORRETO: a fatia do volume que contem os pontos
        # (essencial para filme em pe, cujo plano nao e o axial z=0).
        try:
            k, dose_2d_gy, z_mm = tp.slice_with_most_points(vol, geom, all_points)
            from utils.dose_map_engine import render_dose_map_png
            from isodose_engine import render_isodose_png, DEFAULT_CLINICAL_LEVELS
            dose_2d_cgy = dose_2d_gy * 100.0
            st.caption(f"{t('tps_plane_with_points')}: fatia {k}, z={z_mm:.1f} mm  ·  "
                       f"{t('tps_maxdose')} {dose_2d_cgy.max():.0f} cGy")
            pcol1, pcol2 = st.columns(2)
            with pcol1:
                png = render_dose_map_png(dose_2d_cgy, unit="cGy", lang=get_lang(),
                                          theme="dark", title=t("tps_plane_dose_map"))
                st.image(png, use_container_width=True)
            with pcol2:
                iso = render_isodose_png(dose_2d_cgy, DEFAULT_CLINICAL_LEVELS,
                                         basis="max", level_pcts=DEFAULT_CLINICAL_LEVELS,
                                         unit="cGy", lang=get_lang(), theme="dark",
                                         colormap="jet", show_background=True,
                                         title=t("tps_isodose_preview"), smooth_sigma=1.0)
                st.image(iso, use_container_width=True)
        except Exception as e:
            st.caption(f"({t('tps_preview_fail')}: {e})")

        st.info(t("tps_pointdose_next"))

    # Se houver mais de um mapa de dose, deixa escolher qual e o principal
    chosen_idx = 0
    if n_dose > 1:
        labels = [nm for nm, _ in dose_dists]
        chosen = st.selectbox(t("tps_choose_main"), labels, key="tps_main_dose")
        chosen_idx = labels.index(chosen)

    c1, c2 = st.columns([4, 1])
    with c2:
        if st.button(t("continue"), use_container_width=True, type="primary",
                     disabled=(n_dose == 0 and not contours and not points)):
            # Guarda o principal mapa de dose (em cGy) para uso na comparacao
            if n_dose > 0:
                nm, dist = dose_dists[chosen_idx]
                state["tps_dose_cgy"] = (dist.dose * 100.0)
                state["tps_dose_res_mm"] = dist.resolution_mm
                state["tps_dose_name"] = nm
                state["tps_dose_meta"] = dist.metadata
            state["done"]["tps"] = True
            _save_tps(state, dose_dists, contours, points, chosen_idx)
            notify_user_activity(state.get("user", "?"), "TPS importado",
                                 f"{n_dose} mapa(s) de dose")
            go("dashboard")


def _save_tps(state, dose_dists, contours, points, chosen_idx):
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from utils.study_store import save_module
        main = None
        if dose_dists:
            nm, dist = dose_dists[chosen_idx]
            s = dist.summary()
            main = {"name": nm, "shape": list(s["shape"]),
                    "resolution_mm": s["resolution_mm"],
                    "max_dose_cgy": s["max_dose_cgy"],
                    "plane": (dist.metadata or {}).get("plane_desc")}
        data = {
            "n_dose_maps": len(dose_dists),
            "n_isodoses": len(contours),
            "n_pointsets": len(points),
            "main_dose": main,
        }
        save_module(state, "tps", data)
    except Exception:
        pass
