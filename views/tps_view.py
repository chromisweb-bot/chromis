"""tps_view.py - Importador universal de dados do TPS + analise de pontos.

O usuario anexa os arquivos do TPS (.ALL, .dcm RTDOSE/RTPLAN/RTSTRUCT, .csv,
imagem). O software identifica cada um, extrai mapa de dose, pontos e geometria,
calcula a dose do TPS em cada ponto (interpolacao trilinear no volume 3D),
deixa o usuario escolher o ponto central, e gera mapas e perfis de dose.
A coluna de ERRO fica preparada (aguardando a dose medida no filme).
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
        accept_multiple_files=True, key="tps_files",
    )
    if not files:
        # Se ja existe um TPS salvo, RE-EXIBE o conteudo (tabela + imagens),
        # para o usuario rever o que fez sem precisar reanexar os arquivos.
        from utils.study_store import get_module
        saved = get_module(state, "tps")
        if saved is not None:
            _render_saved_tps(state, saved)
            st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:16px 0'>",
                        unsafe_allow_html=True)
            st.caption(t("tps_reupload_hint"))
            st.markdown(f"<div style='background:{COLORS['bg_surface']};border-radius:8px;"
                        f"padding:20px;text-align:center;color:{COLORS['text_muted']};font-size:12px'>"
                        f"{t('tps_waiting')}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='background:{COLORS['bg_surface']};border-radius:8px;"
                        f"padding:32px;text-align:center;color:{COLORS['text_muted']};font-size:12px'>"
                        f"{t('tps_waiting')}</div>", unsafe_allow_html=True)
        return

    dose_dists, contours, points = [], [], []

    # ── 1) Lê cada arquivo ──────────────────────────────────────────────────
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

        if hasattr(result, "dose") and hasattr(result, "resolution_mm"):
            s = result.summary()
            dose_dists.append((name, result))
            meta = result.metadata or {}
            cA, cB, cC = st.columns(3)
            cA.metric(t("tps_shape"), f"{s['shape'][0]}×{s['shape'][1]}")
            cB.metric(t("tps_res"), f"{s['resolution_mm']:.1f} mm")
            vol3d = meta.get("dose_volume_gy")
            if vol3d is not None and getattr(vol3d, "ndim", 2) == 3 and vol3d.shape[0] > 1:
                maxdose_cgy = float(np.nanmax(vol3d)) * 100.0
                cC.metric(t("tps_maxdose"), f"{maxdose_cgy:.0f} cGy")
                st.caption(t("tps_maxdose_vol_note"))
            else:
                cC.metric(t("tps_maxdose"), f"{s['max_dose_cgy']:.0f} cGy")
            with st.expander(t("tps_metadata")):
                for key, label in [("patient_id","tps_patient"),("plane_desc","tps_plane"),
                                   ("datetime","tps_datetime")]:
                    if meta.get(key):
                        st.caption(f"**{t(label)}:** {meta[key]}")
                if meta.get("upperleft_mm"):
                    ul = meta["upperleft_mm"]; st.caption(f"**{t('tps_origin')}:** ({ul[0]:.1f}, {ul[1]:.1f}) mm")
                if meta.get("origin_patient_mm"):
                    o = meta["origin_patient_mm"]; st.caption(f"**{t('tps_origin')}:** ({o[0]:.1f}, {o[1]:.1f}, {o[2]:.1f}) mm")
                if meta.get("calc_grid_mm"):
                    g = meta["calc_grid_mm"]; st.caption(f"**{t('tps_calcgrid')}:** {g[0]:.1f} × {g[1]:.1f} × {g[2]:.1f} mm")

        elif result.__class__.__name__ == "IsodoseContours" or hasattr(result, "contours"):
            contours.append((name, result)); st.success(t("tps_got_isodose"))
        elif result.__class__.__name__ == "DosePoints":
            points.append((name, result))
            st.success(f"{t('tps_got_points')} ({len(result.points or [])})")

    # ── 2) Junta pontos e acha volume 3D ────────────────────────────────────
    vol_dist = None
    for nm, d in dose_dists:
        m = d.metadata or {}
        if m.get("dose_volume_gy") is not None and m.get("geometry"):
            vol_dist = d; break

    all_points = []
    for nm, dp in points:
        all_points.extend(dp.points or [])

    # ── 3) Calcula dose do TPS em cada ponto (interpolacao trilinear) ───────
    enriched = []
    if vol_dist is not None and all_points:
        vol = vol_dist.metadata["dose_volume_gy"]
        geom = vol_dist.metadata["geometry"]
        for p in all_points:
            d_gy = None
            if p.get("x_mm") is not None:
                d_gy = tp.interpolate_dose_3d(vol, geom, p["x_mm"], p["y_mm"], p["z_mm"])
            q = dict(p); q["tps_dose_gy"] = d_gy
            enriched.append(q)
        state["tps_points_dose"] = enriched

    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:16px 0'>",
                unsafe_allow_html=True)

    # ── 4) Analise dos pontos (so se houver pontos) ─────────────────────────
    central_name = None
    if enriched:
        _render_points_analysis(state, tp, np, vol_dist, enriched)
        central_name = state.get("tps_central_point")

    # ── 5) Resumo geral, salvar e continuar ─────────────────────────────────
    n_dose = len(dose_dists)
    st.markdown(f"**{t('tps_summary')}:** {n_dose} {t('tps_dose_maps')}, "
                f"{len(contours)} {t('tps_isodoses')}, {len(points)} {t('tps_pointsets')}")

    chosen_idx = 0
    if n_dose > 1:
        labels = [nm for nm, _ in dose_dists]
        chosen = st.selectbox(t("tps_choose_main"), labels, key="tps_main_dose")
        chosen_idx = labels.index(chosen)

    can_save = (n_dose > 0 or bool(contours) or bool(points))

    # Mostra se ja foi salvo nesta sessao
    from utils.study_store import get_module
    if get_module(state, "tps") is not None:
        st.success(t("tps_saved_ok"))

    c1, c2, c3 = st.columns([3, 1, 1])
    with c2:
        if st.button(t("save"), use_container_width=True, disabled=not can_save,
                     key="tps_save_btn"):
            _persist_tps(state, dose_dists, contours, points, chosen_idx, enriched,
                         state.get("tps_central_point"))
            st.success(t("tps_saved_ok"))
            st.rerun()
    with c3:
        if st.button(t("continue"), use_container_width=True, type="primary",
                     disabled=not can_save, key="tps_continue_btn"):
            _persist_tps(state, dose_dists, contours, points, chosen_idx, enriched,
                         state.get("tps_central_point"))
            notify_user_activity(state.get("user", "?"), "TPS importado",
                                 f"{n_dose} mapa(s), {len(enriched)} ponto(s)")
            go("dashboard")


def _render_saved_tps(state, saved):
    """Re-exibe o conteudo do TPS ja salvo no estudo (sem reanexar arquivos)."""
    import pandas as pd
    np_saved = len(saved.get("points", []) or [])
    st.success(t("tps_already_saved").format(n=np_saved))

    # Resumo
    md = saved.get("main_dose") or {}
    cols = st.columns(3)
    cols[0].metric(t("tps_r_npoints") if False else t("tps_pt_name") + "s", str(np_saved))
    if saved.get("central_point"):
        cols[1].metric(t("tps_central_select"), saved["central_point"])
    if md.get("max_dose_cgy") is not None:
        cols[2].metric(t("tps_maxdose"), f"{md['max_dose_cgy']:.0f} cGy")

    # Tabela de pontos salvos
    pts = saved.get("points", []) or []
    if pts:
        doses = [p.get("tps_dose_cgy") for p in pts if p.get("tps_dose_cgy") is not None]
        dmax_v = max(doses) if doses else None
        dmin_v = min(doses) if doses else None
        rows = []
        for p in pts:
            d = p.get("tps_dose_cgy")
            flag = ""
            if d is not None and dmax_v is not None and abs(d - dmax_v) < 1e-6:
                flag = "▲ max"
            elif d is not None and dmin_v is not None and abs(d - dmin_v) < 1e-6:
                flag = "▼ min"
            if p.get("name") == saved.get("central_point"):
                flag = (flag + " ◎").strip()
            rows.append({
                t("tps_pt_name"): p.get("name", "?"),
                "X (mm)": round(p["x_mm"], 1) if p.get("x_mm") is not None else "-",
                "Y (mm)": round(p["y_mm"], 1) if p.get("y_mm") is not None else "-",
                "Z (mm)": round(p["z_mm"], 1) if p.get("z_mm") is not None else "-",
                t("tps_pt_tpsdose"): f"{d:.1f}" if d is not None else "-",
                "": flag,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Imagens salvas
    if saved.get("map_image"):
        st.markdown(f"**{t('tps_map_with_points')}**")
        st.image(saved["map_image"], use_container_width=True)
    if saved.get("profiles_image"):
        st.markdown(f"**{t('tps_profiles')}**")
        st.image(saved["profiles_image"], use_container_width=True)


def _persist_tps(state, dose_dists, contours, points, chosen_idx, enriched, central_name):
    """Salva os dados E garante o estado do modulo (dose principal + flag done)."""
    if dose_dists:
        nm, dist = dose_dists[chosen_idx]
        state["tps_dose_cgy"] = (dist.dose * 100.0)
        state["tps_dose_res_mm"] = dist.resolution_mm
        state["tps_dose_name"] = nm
        state["tps_dose_meta"] = dist.metadata
    state.setdefault("done", {})["tps"] = True
    _save_tps(state, dose_dists, contours, points, chosen_idx, enriched, central_name)


def _render_points_analysis(state, tp, np, vol_dist, enriched):
    """Tabela de pontos, selecao de centro, mapas e perfis."""
    import pandas as pd

    st.markdown(f"### {t('tps_points_section')}")

    # pontos validos (com dose e que nao sao o contorno do corpo)
    valid = [q for q in enriched if q.get("tps_dose_gy") is not None
             and str(q.get("name", "")).lower() != "patient"]
    if not valid:
        st.info(t("tps_no_valid_points"))
        return

    doses_cgy = np.array([q["tps_dose_gy"] * 100 for q in valid])
    pmax = valid[int(np.argmax(doses_cgy))]
    pmin = valid[int(np.argmin(doses_cgy))]

    # Resumo
    m1, m2, m3 = st.columns(3)
    m1.metric(t("tps_dmax_pt"), f"{doses_cgy.max():.1f} cGy", pmax["name"])
    m2.metric(t("tps_dmin_pt"), f"{doses_cgy.min():.1f} cGy", pmin["name"])
    m3.metric(t("tps_dmean_pt"), f"{doses_cgy.mean():.1f} cGy")

    # Selecao do ponto central (o usuario escolhe)
    names = [q["name"] for q in valid]
    default_idx = names.index(pmax["name"]) if pmax["name"] in names else 0
    central = st.selectbox(t("tps_central_select"), names, index=default_idx,
                           key="tps_central_point", help=t("tps_central_hint"))

    # Tabela completa com erro preparado
    rows = []
    for q in valid:
        d_cgy = q["tps_dose_gy"] * 100
        flag = ""
        if q["name"] == pmax["name"]: flag = "▲ max"
        elif q["name"] == pmin["name"]: flag = "▼ min"
        if q["name"] == central: flag = (flag + " ◎ centro").strip()
        rows.append({
            t("tps_pt_name"): q["name"],
            "X (mm)": round(q.get("x_mm", 0), 1),
            "Y (mm)": round(q.get("y_mm", 0), 1),
            "Z (mm)": round(q.get("z_mm", 0), 1),
            t("tps_pt_tpsdose"): f"{d_cgy:.1f}",
            t("tps_pt_filmdose"): "—",          # aguardando filme
            t("tps_pt_error"): "—",             # aguardando filme
            "": flag,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(t("tps_error_pending"))

    # Toggle: mostrar pontos nas imagens
    show_points = st.checkbox(t("tps_show_points_imgs"), value=True, key="tps_show_pts")

    geom = vol_dist.metadata["geometry"]
    vol = vol_dist.metadata["dose_volume_gy"]

    # Fatia que contem os pontos
    k, dose_2d_gy, z_mm = tp.slice_with_most_points(vol, geom, valid)
    dose_2d_cgy = dose_2d_gy * 100.0
    st.caption(f"{t('tps_plane_with_points')}: fatia {k}, z={z_mm:.1f} mm  ·  "
               f"{t('tps_maxdose')} {dose_2d_cgy.max():.0f} cGy")

    # pontos nesta fatia
    oz = geom["origin_mm"][2]
    gfov = list(geom.get("grid_frame_offset", [0.0]))
    spacing_z = (gfov[1] - gfov[0]) if len(gfov) > 1 else 1.0
    pts_here = []
    for q in valid:
        kp = int(round((q["z_mm"] - oz) / spacing_z)) if spacing_z else 0
        if abs(kp - k) <= 1:
            pts_here.append(q)

    from utils.dose_map_engine import render_dose_map_png
    from isodose_engine import (render_isodose_png, DEFAULT_CLINICAL_LEVELS,
                                 LEVELS_10_TO_150)
    from utils.dose_points_plot import render_dose_map_with_points, render_dose_profiles

    # Seletor de niveis de isodose (presets + edicao livre), % da dose maxima.
    st.caption(t("iso_presets"))
    bp1, bp2, bp3 = st.columns(3)
    if bp1.button(t("iso_preset_clinical"), use_container_width=True, key="tps_iso_p1"):
        st.session_state["tps_iso_levels"] = ", ".join(str(x) for x in DEFAULT_CLINICAL_LEVELS)
    if bp2.button("10 → 150", use_container_width=True, key="tps_iso_p2"):
        st.session_state["tps_iso_levels"] = ", ".join(str(x) for x in LEVELS_10_TO_150)
    if bp3.button(t("iso_preset_main"), use_container_width=True, key="tps_iso_p3"):
        st.session_state["tps_iso_levels"] = "50, 100"
    levels_str = st.text_input(t("tps_iso_levels_label"),
                               value=", ".join(str(x) for x in DEFAULT_CLINICAL_LEVELS),
                               key="tps_iso_levels", help=t("iso_levels_pct_hint"))
    try:
        iso_levels = [float(x.strip()) for x in levels_str.split(",") if x.strip()]
    except Exception:
        st.error(t("iso_levels_err")); iso_levels = list(DEFAULT_CLINICAL_LEVELS)
    if not iso_levels:
        iso_levels = list(DEFAULT_CLINICAL_LEVELS)

    # Aparencia das imagens: tema, paleta de cores e rotulo de % nas isodoses.
    ac1, ac2, ac3 = st.columns(3)
    with ac1:
        theme_choice = st.radio(t("cal_graph_theme"),
                                [t("cal_theme_dark"), t("cal_theme_light")],
                                horizontal=True, key="tps_theme")
        theme_val = "dark" if theme_choice == t("cal_theme_dark") else "light"
    with ac2:
        cmap = st.selectbox(t("tps_colormap"),
                            ["jet", "turbo", "viridis", "plasma", "inferno", "rainbow"],
                            key="tps_cmap")
    with ac3:
        label_iso = st.checkbox(t("tps_iso_label_pct"), value=True, key="tps_iso_lbl")

    # Mapa de dose e mapa de isodose (lado a lado)
    st.markdown(f"**{t('tps_maps_title')}**")
    cc1, cc2 = st.columns(2)
    with cc1:
        png = render_dose_map_png(dose_2d_cgy, unit="cGy", lang=get_lang(),
                                  theme=theme_val, title=t("tps_plane_dose_map"),
                                  colormap=cmap)
        st.image(png, use_container_width=True)
    with cc2:
        iso = render_isodose_png(dose_2d_cgy, iso_levels, basis="max",
                                 level_pcts=iso_levels, unit="cGy",
                                 lang=get_lang(), theme=theme_val, colormap=cmap,
                                 show_background=True, title=t("tps_isodose_preview"),
                                 smooth_sigma=1.0, label_on_curves=label_iso)
        st.image(iso, use_container_width=True)

    # Mapa de dose com pontos
    st.markdown(f"**{t('tps_map_with_points')}**")
    iso_fracs = tuple(iso_levels)  # usados como % da dose maxima no mapa c/ pontos
    png_pts = render_dose_map_with_points(
        dose_2d_cgy, geom, pts_here if show_points else [], lang=get_lang(),
        theme=theme_val, colormap=cmap, title=t("tps_map_with_points"),
        smooth_sigma=1.0, show_isodoses=True, level_pcts=iso_fracs,
        label_points=show_points)
    st.image(png_pts, use_container_width=True)
    if show_points:
        st.caption(f"{len(pts_here)} {t('tps_points_in_plane')}")
    # Guarda para o relatorio
    state["tps_map_image"] = png_pts

    # Perfis: PDD no eixo central + laterais na profundidade escolhida
    ref = next((q for q in valid if q["name"] == central), pmax)
    st.markdown(f"**{t('tps_profiles')}** — {t('tps_pt_name')}: {ref['name']}")

    # Profundidade (Y) dos perfis laterais: padrao = a do ponto de referencia.
    ys = [q["y_mm"] for q in valid if q.get("y_mm") is not None]
    if ys:
        ymin, ymax = float(min(ys)), float(max(ys))
        depth_y = st.slider(
            t("tps_lateral_depth"), min_value=round(ymin, 1), max_value=round(ymax, 1),
            value=float(round(ref["y_mm"], 1)),
            help=t("tps_lateral_depth_hint"), key="tps_lat_depth")
    else:
        depth_y = ref.get("y_mm")

    try:
        prof = render_dose_profiles(vol, geom, ref,
                                    points=valid, show_points=show_points,
                                    lateral_depth_y_mm=depth_y,
                                    lang=get_lang(), theme=theme_val)
        st.image(prof, use_container_width=True)
        state["tps_profiles_image"] = prof   # guarda para o relatorio
    except Exception as e:
        st.caption(f"({t('tps_profiles_fail')}: {e})")


def _save_tps(state, dose_dists, contours, points, chosen_idx, enriched, central):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from utils.study_store import save_module
    main = None
    if dose_dists:
        nm, dist = dose_dists[chosen_idx]
        s = dist.summary()
        main = {"name": nm, "shape": list(s["shape"]),
                "resolution_mm": s["resolution_mm"], "max_dose_cgy": s["max_dose_cgy"]}
    pts_summary = []
    for q in enriched:
        if q.get("tps_dose_gy") is not None:
            pts_summary.append({"name": q["name"],
                                "x_mm": q.get("x_mm"), "y_mm": q.get("y_mm"),
                                "z_mm": q.get("z_mm"),
                                "tps_dose_cgy": q["tps_dose_gy"] * 100})
    # As imagens sao guardadas DENTRO do estudo (nao em state solto), para
    # persistirem e aparecerem no relatorio mesmo apos navegar entre telas.
    data = {
        "n_dose_maps": len(dose_dists), "n_isodoses": len(contours),
        "n_pointsets": len(points), "main_dose": main,
        "points": pts_summary, "central_point": central,
        "map_image": state.get("tps_map_image"),
        "profiles_image": state.get("tps_profiles_image"),
    }
    save_module(state, "tps", data)
