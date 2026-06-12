"""dosemap_view.py - Mapa de dose 2D (aplica a curva de calibracao no filme)."""
import streamlit as st
from i18n import t, get_lang
from theme import COLORS
from auth import notify_user_activity


def dosemap_view(state, go):
    st.markdown(f"<div style='font-size:12px;color:{COLORS['text_muted']};margin-bottom:14px'>"
                f"{t('group_dosimetry')}</div>", unsafe_allow_html=True)

    # Precisa de calibracao
    study = state.get("study", {})
    cal = study.get("calibration")
    if not cal or not cal.get("points"):
        st.warning(t("dm_need_calib"))
        if st.button(t("cal_go_upload")):
            go("calibration")
        return

    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils"))
        from utils.image_bridge import bytes_to_array
        from utils.film_detection import detect_films, order_films_by_intensity
        from utils.dose_map_engine import compute_dose_map, render_dose_map_png
        from calibration import CalibrationData, fit_calibration
        import numpy as np
    except Exception as e:
        st.error(f"Erro ao carregar motores: {e}")
        return

    # Reconstruir o modelo de calibracao
    pts = cal["points"]
    nods = np.array([p["nod"] for p in pts])
    doses = np.array([p["dose"] for p in pts])
    model_type = cal.get("model_type", "devic")
    unit = cal.get("unit", "cGy")
    try:
        model_obj = fit_calibration(CalibrationData(nod=nods, dose=doses), model_type=model_type)
    except Exception as e:
        st.error(f"Erro ao reconstruir a curva: {e}")
        return

    # PV do filme zero (background)
    pv_zero = None
    for p in pts:
        if p["dose"] == 0:
            pv_zero = p["pv_red"]
            break
    if pv_zero is None:
        st.warning(t("dm_need_zero"))
        return

    # ===== Escolha da fonte do filme de medida =====
    st.markdown(f"**{t('dm_source')}**")
    source = st.radio(
        t("dm_source_q"),
        [t("dm_source_upload"), t("dm_source_calib")],
        key="dm_source",
    )

    measure_img = None  # imagem completa onde detectar o filme
    known_dose = None   # dose irradiada conhecida (opcional, p/ upload)
    known_unit = "cGy"

    if source == t("dm_source_upload"):
        st.caption(t("dm_upload_hint"))
        up = st.file_uploader(t("dm_upload"), type=["tif", "tiff", "png", "jpg", "jpeg"],
                              key="dm_upload_widget")
        if up is not None:
            measure_img = bytes_to_array(up.getvalue(), up.name)

        # Dose com que o filme foi irradiado (importante para validacao)
        cda, cdb = st.columns([2, 1])
        with cda:
            known_dose = st.number_input(t("dm_known_dose"), min_value=0.0,
                                         value=0.0, step=1.0, key="dm_known_dose_val")
        with cdb:
            known_unit = st.radio(t("up_unit"), ["cGy", "Gy"], horizontal=True,
                                  key="dm_known_unit")
        st.caption(t("dm_known_dose_hint"))
    else:
        saved_films = state.get("uploaded_films", [])
        if not saved_films:
            st.warning(t("dm_no_calib_films"))
            return
        measure_img = bytes_to_array(saved_films[0]["bytes"], saved_films[0]["name"])

    if measure_img is None:
        st.info(t("dm_waiting_film"))
        return

    # Detectar filmes na imagem de medida
    films, _ = detect_films(measure_img)
    ordered = order_films_by_intensity(films)
    if not ordered:
        st.warning(t("up_load_first"))
        return

    # Se houver mais de um filme, deixa escolher qual analisar.
    # Se o scan tiver o MESMO numero de filmes da calibracao salva, casa por
    # ordem de intensidade e mostra a DOSE de cada um no seletor — evita
    # confundir filmes vizinhos (ex.: #7=400 vs #8=600), que sao parecidos.
    calib_doses_by_order = None
    try:
        from utils.study_store import get_module
        upsaved = get_module(state, "upload")
        if upsaved and upsaved.get("films") and \
                int(upsaved.get("n_films", -1)) == len(ordered):
            unit_up = upsaved.get("unit", "cGy")
            fac = 100.0 if unit_up == "Gy" else 1.0
            calib_doses_by_order = {
                int(fi["order"]): float(fi.get("dose", 0.0)) * fac
                for fi in upsaved["films"]
            }
    except Exception:
        calib_doses_by_order = None

    def _film_label(f):
        base = f"#{f['order']+1}"
        if calib_doses_by_order is not None and f["order"] in calib_doses_by_order:
            return f"{base} · {calib_doses_by_order[f['order']]:.0f} cGy"
        return base

    if len(ordered) > 1:
        st.markdown(f"**{t('dm_select_film')}**")
        labels = [_film_label(f) for f in ordered]
        sel = st.selectbox(t("dm_film"), labels, key="dm_film_sel")
        film = ordered[labels.index(sel)]
        if calib_doses_by_order is not None:
            st.caption(t("dm_film_dose_hint"))
    else:
        film = ordered[0]
        sel = "#1"

    # ===== Opcoes de exibicao =====
    col1, col2 = st.columns(2)
    with col1:
        display_mode = st.radio(t("dm_display"),
                                [t("dm_percent"), t("dm_absolute")],
                                key="dm_display")
    with col2:
        theme_choice = st.radio(t("cal_graph_theme"),
                                [t("cal_theme_dark"), t("cal_theme_light")],
                                horizontal=True, key="dm_theme")
    theme_val = "dark" if theme_choice == t("cal_theme_dark") else "light"
    is_percent = display_mode == t("dm_percent")

    # Paleta de cores do mapa de dose (heatmap)
    dm_cmap = st.selectbox(
        t("dm_colormap"),
        ["jet", "turbo", "viridis", "inferno", "plasma", "magma", "hot", "rainbow"],
        index=0, key="dm_cmap",
    )

    # Rotacao do filme (ex.: filme irradiado deitado -> girar p/ visualizar)
    rot_choice = st.selectbox(t("dm_rotate"), ["0°", "90°", "180°", "270°"],
                              index=0, key="dm_rotate",
                              help=t("dm_rotate_hint"))

    # Margem de exclusao de borda: a borda cortada do filme tem sombra
    # escura no scan que vira dose falsa ALTA e contamina maximo/P99
    # (pratica padrao: Dosepy/OMG analisam dentro do filme).
    margin_mm = st.slider(t("dm_edge_margin"), 0.0, 5.0, 3.0, 0.5,
                          key="dm_edge_margin", help=t("dm_edge_margin_hint"))

    # Re-escala one-scan (Lewis 2012): um filme de REFERENCIA com dose
    # conhecida, escaneado JUNTO do filme de medida, re-escala a curva e
    # elimina desvios sistematicos entre scans/tempos (caminho para 1-2%).
    rescale_k = None
    with st.expander(t("dm_rescale_title")):
        st.caption(t("dm_rescale_hint"))
        ref_file = st.file_uploader(t("dm_rescale_file"),
                                    type=["tif", "tiff", "png", "jpg", "jpeg"],
                                    key="dm_ref_file")
        rc1, rc2 = st.columns(2)
        with rc1:
            ref_dose_val = st.number_input(t("dm_rescale_dose"), 0.0, 100000.0,
                                           0.0, key="dm_ref_dose")
        with rc2:
            ref_dose_unit = st.radio(t("up_unit"), ["cGy", "Gy"],
                                     horizontal=True, key="dm_ref_unit")

    # Fonte do background (PV0). Ordem por robustez na pratica real:
    #  1) regiao nao irradiada do proprio filme = mesmo scan/tempo (mais robusto)
    #  2) upload de background separado = so funciona se mesmo lote E mesmo scan
    #  3) filme zero da calibracao (pode divergir se escaneado em outro momento)
    bg_mode = st.radio(t("dm_bg_source"),
                       [t("dm_bg_film"), t("dm_bg_upload"), t("dm_bg_calib")],
                       key="dm_bg_source")
    st.caption(t("dm_bg_hint"))
    with st.expander(t("protocol_title")):
        st.markdown(t("protocol_items"))

    bg_img = None
    if bg_mode == t("dm_bg_upload"):
        st.warning(t("dm_bg_upload_warn"))
        bgup = st.file_uploader(t("dm_bg_upload_label"),
                                type=["tif", "tiff", "png", "jpg", "jpeg"],
                                key="dm_bg_upload_widget")
        if bgup is not None:
            bg_img = bytes_to_array(bgup.getvalue(), bgup.name)

    use_film_bg = bg_mode == t("dm_bg_film")
    use_bg_upload = bg_mode == t("dm_bg_upload")

    if use_bg_upload and bg_img is None:
        st.info(t("dm_bg_waiting"))
        return

    with st.spinner("..."):
        import numpy as np
        from utils.dose_map_engine import _red_channel
        minr, minc, maxr, maxc = film["bbox"]
        crop = measure_img[minr:maxr, minc:maxc]

        # Rotacao escolhida pelo usuario (90 graus anti-horario por passo)
        rot_k = {"0°": 0, "90°": 1, "180°": 2, "270°": 3}.get(rot_choice, 0)
        if rot_k:
            crop = np.rot90(crop, k=rot_k, axes=(0, 1))

        pv_zero_use = pv_zero
        if use_bg_upload and bg_img is not None:
            # PV0 = mediana da REGIAO CENTRAL do filme de background (evita bordas).
            try:
                bfilms, _ = detect_films(bg_img)
                bordered = order_films_by_intensity(bfilms)
                if bordered:
                    bb = bordered[0]["bbox"]
                    bg_crop = bg_img[bb[0]:bb[2], bb[1]:bb[3]]
                else:
                    bg_crop = bg_img
                bred = _red_channel(bg_crop)
                bh, bw = bred.shape
                # regiao central 50% (evita bordas contaminadas)
                central_bg = bred[int(bh*0.25):int(bh*0.75), int(bw*0.25):int(bw*0.75)]
                pv_zero_use = float(np.median(central_bg))
            except Exception:
                pv_zero_use = float(np.median(_red_channel(bg_img)))
        elif use_film_bg:
            # PV0 = regiao NAO IRRADIADA do proprio filme. v3 (moda robusta):
            # o conjunto de pixels nao irradiados forma um CLUSTER claro no
            # histograma; o PICO desse cluster e o PV0 verdadeiro (insensivel
            # a caudas de ruido e a posicao do campo — funciona com o filme
            # deitado, campo cruzando cantos etc.). Refina com a mediana dos
            # pixels a ±2% do pico.
            red = _red_channel(crop)

            def _moda_cluster(reg):
                """Moda do cluster claro de uma regiao + selecao usada."""
                if reg.size < 400:
                    return None, None
                s = reg[reg >= np.percentile(reg, 80)]
                hist_, edges_ = np.histogram(s, bins=256)
                p = float(0.5 * (edges_[np.argmax(hist_)] + edges_[np.argmax(hist_) + 1]))
                selm = (reg >= p * 0.98) & (reg <= p * 1.02)
                if selm.sum() < 200:
                    return None, None
                return float(np.median(reg[selm])), selm

            hh0, ww0 = red.shape
            pvL, selL = _moda_cluster(red[:, :ww0 // 2])
            pvR, selR = _moda_cluster(red[:, ww0 // 2:])

            bg_sel = np.zeros_like(red, dtype=bool)
            if pvL is not None and pvR is not None:
                # v4: PV0 POR COLUNA, interpolado entre as duas laterais
                # (correcao de 1a ordem do LRA). REFINO v4.1: usa apenas o
                # TERCO EXTERNO de cada lateral — o scatter (dose espalhada)
                # decai com a distancia do campo, entao as colunas mais
                # distantes tem PV0 menos contaminado.
                selL_g = np.zeros_like(red, dtype=bool)
                selL_g[:, :ww0 // 2] = selL
                selR_g = np.zeros_like(red, dtype=bool)
                selR_g[:, ww0 // 2:] = selR
                colsL = np.where(selL_g.any(axis=0))[0]
                colsR = np.where(selR_g.any(axis=0))[0]
                if colsL.size >= 9 and colsR.size >= 9:
                    nL3 = max(3, colsL.size // 3)
                    nR3 = max(3, colsR.size // 3)
                    cmL = np.zeros(ww0, dtype=bool); cmL[colsL[:nL3]] = True
                    cmR = np.zeros(ww0, dtype=bool); cmR[colsR[-nR3:]] = True
                    extL = selL_g & cmL[None, :]
                    extR = selR_g & cmR[None, :]
                    if extL.sum() >= 200 and extR.sum() >= 200:
                        pvL = float(np.median(red[extL]))
                        pvR = float(np.median(red[extR]))
                        selL_g, selR_g = extL, extR
                xL = float(np.median(np.where(selL_g.any(axis=0))[0]))
                xR = float(np.median(np.where(selR_g.any(axis=0))[0]))
                pv_zero_use = np.interp(np.arange(ww0), [xL, xR], [pvL, pvR])
                bg_sel = selL_g | selR_g
                st.caption(t("dm_bg_film_pv0_lr").format(
                    l=f"{pvL:.0f}", r=f"{pvR:.0f}"))
                lra_pct = 100.0 * abs(pvL - pvR) / max(0.5 * (pvL + pvR), 1e-6)
                if lra_pct > 1.0:
                    st.info(t("dm_lra_corrected").format(pct=f"{lra_pct:.1f}"))
            else:
                # fallback: moda unica (filme com so uma lateral limpa)
                pv0s, sel0 = _moda_cluster(red)
                if pv0s is None:
                    sel = red[red >= np.percentile(red, 80)]
                    hist, edges = np.histogram(sel, bins=256)
                    pico = float(0.5 * (edges[np.argmax(hist)] + edges[np.argmax(hist) + 1]))
                    bg_sel = (red >= pico * 0.98) & (red <= pico * 1.02)
                    viz = red[bg_sel]
                    pv_zero_use = float(np.median(viz)) if viz.size else pico
                else:
                    pv_zero_use = pv0s
                    bg_sel = sel0
                st.caption(t("dm_bg_film_pv0").format(pv=f"{float(np.mean(pv_zero_use)):.0f}"))

            # Transparencia: MOSTRA onde o background foi medido (verde)
            frac_bg = float(bg_sel.mean())
            try:
                from PIL import Image as _PILImage
                base = crop[:, :, :3] if crop.ndim == 3 else np.stack([crop]*3, axis=-1)
                base = base.astype(np.float64)
                if base.max() > 255:           # 16-bit -> 8-bit p/ exibir
                    base = base / base.max() * 255.0
                over = base.copy()
                over[bg_sel] = 0.45 * over[bg_sel] + 0.55 * np.array([0, 220, 90])
                with st.expander(t("dm_bg_where"), expanded=False):
                    st.image(over.astype(np.uint8), use_container_width=True,
                             caption=t("dm_bg_where_cap").format(pct=f"{100*frac_bg:.0f}"))
            except Exception:
                frac_bg = float(bg_sel.mean())

            # Aviso: filme aparentemente TODO irradiado (ex.: PDD) ->
            # nao existe regiao de dose zero; o PV0 fica contaminado.
            if frac_bg < 0.10:
                st.warning(t("dm_bg_all_irradiated"))

        dpi_scan = int(state.get("upload_params", {}).get("dpi",
                       state.get("setup_data", {}).get("dpi", 72)))
        margin_px = max(2, int(round(margin_mm * dpi_scan / 25.4))) if margin_mm > 0 else 0

        result = compute_dose_map(crop, pv_zero_use, model_obj,
                                  normalize="max" if is_percent else None,
                                  edge_margin_px=margin_px)

        # Aplica a re-escala one-scan, se um filme de referencia foi dado.
        if ref_file is not None and ref_dose_val > 0:
            try:
                from PIL import Image as _PILImg
                import io as _io2
                ref_img = np.array(_PILImg.open(_io2.BytesIO(ref_file.getvalue())))
                ref_red = _red_channel(ref_img)
                rh, rw = ref_red.shape
                # mediana da regiao central (50%) do filme de referencia
                ref_pv = float(np.median(
                    ref_red[rh // 4: 3 * rh // 4, rw // 4: 3 * rw // 4]))
                pv0_scalar = float(np.mean(pv_zero_use))
                ref_netod = max(0.0, float(np.log10(max(pv0_scalar, 1e-6) /
                                                    max(ref_pv, 1e-6))))
                from calibration import predict_dose as _pd
                ref_measured = float(np.asarray(
                    _pd(model_obj, np.array([ref_netod])))[0])
                ref_known = ref_dose_val * 100.0 if ref_dose_unit == "Gy" else ref_dose_val
                if ref_measured > 1e-6:
                    rescale_k = ref_known / ref_measured
                    result["dose_map"] = result["dose_map"] * rescale_k
                    for kk in ("dose_min", "dose_max", "dose_mean"):
                        result[kk] = result[kk] * rescale_k
                    if "ref_dose" in result:
                        result["ref_dose"] = result["ref_dose"] * rescale_k
            except Exception:
                rescale_k = None
        if is_percent:
            png = render_dose_map_png(result["dose_map_pct"], unit, get_lang(),
                                      theme_val, percent=True, colormap=dm_cmap)
        else:
            png = render_dose_map_png(result["dose_map"], unit, get_lang(),
                                      theme_val, colormap=dm_cmap)

    st.image(png, use_container_width=True)

    if rescale_k is not None:
        st.success(t("dm_rescale_applied").format(k=f"{rescale_k:.4f}"))

    # Metricas
    c1, c2, c3 = st.columns(3)
    if is_percent:
        c1.metric(t("dm_dose_min"), f"{result['pct_min']:.0f}%")
        c2.metric(t("dm_dose_mean"), f"{result['pct_mean']:.0f}%")
        c3.metric(t("dm_dose_max"), f"{result['pct_max']:.0f}%")
        st.caption(f"{t('dm_ref')}: {result['ref_dose']:.0f} {unit} (P99)")
    else:
        c1.metric(t("dm_dose_min"), f"{result['dose_min']:.0f} {unit}")
        c2.metric(t("dm_dose_mean"), f"{result['dose_mean']:.0f} {unit}")
        c3.metric(t("dm_dose_max"), f"{result['dose_max']:.0f} {unit}")

    # Comparacao com a dose irradiada conhecida (se informada no upload)
    known_cgy = None
    if known_dose and known_dose > 0:
        known_cgy = known_dose * 100.0 if known_unit == "Gy" else known_dose
        # Protecao contra troca de filme: se este scan e o da calibracao e a
        # dose informada diverge muito da dose DESTE filme, avisa.
        if calib_doses_by_order is not None:
            sug = calib_doses_by_order.get(film["order"])
            if sug and sug > 0 and abs(known_cgy - sug) / sug > 0.20:
                st.warning(t("dm_film_mismatch").format(
                    sel=f"#{film['order']+1}", sug=f"{sug:.0f}",
                    inf=f"{known_cgy:.0f}"))
        import numpy as np
        from scipy.ndimage import median_filter
        dm_abs = result["dose_map"]
        # Tipo do campo para a validacao:
        #  - UNIFORME: ha um plato de dose plena -> mediana do top 5% (P95).
        #  - GRADIENTE/PDD (ex.: filme deitado atravessado pelo feixe): nao ha
        #    plato; a dose nominal refere-se ao PICO -> mediana do top 1% (P99).
        val_mode = st.radio(t("dm_val_mode"),
                            [t("dm_val_uniform"), t("dm_val_gradient"),
                             t("dm_val_manual")],
                            horizontal=True, key="dm_val_mode",
                            help=t("dm_val_mode_hint"))
        # Boas praticas (literatura): medir em AREA, nao pixel; suavizar ruido.
        dm_smooth = median_filter(dm_abs, size=5)
        if val_mode == t("dm_val_manual"):
            # Regiao definida pelo usuario (em % do mapa), com preview.
            # Default: caixa centrada no PONTO DE DOSE MAXIMA do mapa
            # (regiao de dose plena), nao no centro geometrico.
            hh, ww = dm_smooth.shape
            # Default: caixa centrada no CENTROIDE da regiao top-1% (robusto;
            # um argmax de pixel unico pode cair em artefato pontual).
            try:
                p99c = np.nanpercentile(dm_smooth, 99)
                ys, xs = np.where(dm_smooth >= p99c)
                iy, ix = int(np.median(ys)), int(np.median(xs))
            except Exception:
                iy, ix = hh // 2, ww // 2
            cx_pct = int(100 * ix / ww); cy_pct = int(100 * iy / hh)
            dx0 = max(0, cx_pct - 12); dx1 = min(100, cx_pct + 12)
            dy0 = max(0, cy_pct - 12); dy1 = min(100, cy_pct + 12)
            st.caption(t("dm_val_manual_hint"))
            rc1, rc2 = st.columns(2)
            with rc1:
                x0, x1 = st.slider(t("dm_val_region_x"), 0, 100, (dx0, dx1),
                                   key="dm_val_x")
            with rc2:
                y0, y1 = st.slider(t("dm_val_region_y"), 0, 100, (dy0, dy1),
                                   key="dm_val_y")
            c0, c1_ = int(ww * x0 / 100), max(int(ww * x1 / 100), int(ww * x0 / 100) + 2)
            r0, r1_ = int(hh * y0 / 100), max(int(hh * y1 / 100), int(hh * y0 / 100) + 2)
            region = dm_smooth[r0:r1_, c0:c1_]
            measured = float(np.nanmedian(region)) if region.size else 0.0
            # preview do retangulo sobre o mapa
            try:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                import io as _io
                figp, axp = plt.subplots(figsize=(4.6, 3.6), dpi=100)
                axp.imshow(dm_smooth, cmap=dm_cmap)
                axp.add_patch(plt.Rectangle((c0, r0), c1_ - c0, r1_ - r0,
                                            fill=False, edgecolor="white",
                                            linewidth=2))
                axp.set_xticks([]); axp.set_yticks([])
                axp.set_title(t("dm_val_region_prev"), fontsize=9)
                bufp = _io.BytesIO()
                figp.savefig(bufp, format="png", bbox_inches="tight")
                plt.close(figp)
                st.image(bufp.getvalue(), width=420)
            except Exception:
                pass
        else:
            hh, ww = dm_smooth.shape
            if val_mode == t("dm_val_uniform"):
                # Plato (campo uniforme): mediana do MIOLO do campo.
                # O campo e detectado (>=50% do maximo robusto) e ERODIDO
                # (~3 mm) para excluir a penumbra. Corrige o vies do antigo
                # 'mediana do top 5%', que media a CAUDA DO RUIDO e
                # superestimava a dose do plato em +0.5 a +3%.
                from scipy.ndimage import binary_erosion
                finite = np.isfinite(dm_smooth)
                thr_f = 0.5 * np.nanpercentile(dm_smooth, 99.5)
                field_m = finite & (dm_smooth >= thr_f)
                er_px = max(3, int(round(3.0 * dpi_scan / 25.4)))   # ~3 mm
                core_m = binary_erosion(field_m, iterations=er_px)
                if core_m.sum() < 100:
                    core_m = field_m
                region_mask = core_m
                measured = float(np.nanmedian(dm_smooth[region_mask])) \
                    if region_mask.any() else float(np.nanmedian(dm_smooth))
            else:
                # PDD: pico no EIXO CENTRAL do campo (como o fisico mede).
                # Percentil global pega hot spots e os 'horns' do perfil
                # lateral; o eixo central compara com a dose nominal correta.
                field = dm_smooth >= 0.5 * np.nanpercentile(dm_smooth, 99.5)
                wsum = field.sum(axis=0).astype(float)
                if wsum.sum() > 0:
                    center_col = int(round(np.average(np.arange(ww), weights=wsum + 1e-9)))
                else:
                    center_col = ww // 2
                half_band = max(3, int(round(2.0 * dpi_scan / 25.4)))  # ±2 mm
                c0b = max(0, center_col - half_band)
                c1b = min(ww, center_col + half_band + 1)
                band = dm_smooth[:, c0b:c1b]
                profile = np.nanmedian(band, axis=1)
                profile = median_filter(profile, size=9)
                ipk = int(np.nanargmax(profile))
                measured = float(profile[ipk])
                region_mask = np.zeros_like(dm_smooth, dtype=bool)
                region_mask[:, c0b:c1b] = True
            # Overlay diagnostico: VER exatamente o que foi medido.
            try:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                import io as _io
                figd, axd = plt.subplots(figsize=(4.6, 3.6), dpi=100)
                axd.imshow(dm_smooth, cmap=dm_cmap)
                ov = np.zeros((hh, ww, 4))
                ov[region_mask] = [1, 1, 1, 0.35]   # branco translucido
                axd.imshow(ov)
                if val_mode != t("dm_val_uniform"):
                    axd.axhline(ipk, color="white", lw=1.4, ls="--")
                axd.set_xticks([]); axd.set_yticks([])
                axd.set_title(t("dm_val_region_prev"), fontsize=9)
                bufd = _io.BytesIO()
                figd.savefig(bufd, format="png", bbox_inches="tight")
                plt.close(figd)
                with st.expander(t("dm_val_see_region"), expanded=False):
                    st.image(bufd.getvalue(), width=420)
            except Exception:
                pass
        diff_pct = (measured - known_cgy) / known_cgy * 100.0 if known_cgy else 0.0
        diff_abs = measured - (known_cgy or 0.0)
        st.markdown(f"**{t('dm_validation')}**")
        v1, v2, v3 = st.columns(3)
        v1.metric(t("dm_irradiated"), f"{known_cgy:.0f} cGy")
        v2.metric(t("dm_measured_center"), f"{measured:.0f} cGy")
        v3.metric(t("dm_difference"), f"{diff_abs:+.0f} cGy ({diff_pct:+.1f}%)")
        st.caption(t("dm_diff_hint"))
        # Interpretacao por FAIXA de dose: em dose baixa (<100 cGy) o erro
        # percentual engana (1-2 cGy de ruido viram 10-20%); julga-se pelo
        # erro ABSOLUTO. Em dose alta, pelo percentual, como de costume.
        if known_cgy and known_cgy < 100.0:
            aa = abs(diff_abs)
            st.caption(t("dm_lowdose_note"))
            if aa <= 5:
                st.success(t("dm_diff_great_abs"))
            elif aa <= 10:
                st.info(t("dm_diff_ok_abs"))
            else:
                st.warning(t("dm_diff_check"))
        else:
            ad = abs(diff_pct)
            if ad <= 3:
                st.success(t("dm_diff_great"))
            elif ad <= 5:
                st.info(t("dm_diff_ok"))
            else:
                st.warning(t("dm_diff_check"))
        central = measured

    st.markdown(f"<hr style='border:none;border-top:0.5px solid {COLORS['border_soft']};margin:16px 0'>",
                unsafe_allow_html=True)
    cc1, cc2 = st.columns([3, 1])
    with cc2:
        if st.button(t("cal_save"), use_container_width=True, type="primary"):
            state["done"]["dosemap"] = True
            state["dosemap_png"] = png
            state["dosemap_is_percent"] = is_percent
            # Guarda o mapa de dose ABSOLUTO (cGy/Gy) e metadados para o
            # modulo de Isodose reaproveitar sem recalcular.
            state["dosemap_array"] = result["dose_map"]
            state["dosemap_unit"] = unit
            if known_cgy:
                state["dosemap_known_cgy"] = known_cgy
            _save_dosemap(state, sel, result, unit, is_percent, known_cgy)
            notify_user_activity(state.get("user", "?"), "Mapa de dose gerado",
                                 f"Filme {sel}")
            go("dashboard")


def _save_dosemap(state, film_label, result, unit, is_percent, known_cgy=None):
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from utils.study_store import save_module
        data = {"film": film_label, "unit": unit, "is_percent": is_percent,
                "dose_min": result["dose_min"], "dose_max": result["dose_max"],
                "dose_mean": result["dose_mean"]}
        if is_percent:
            data.update({"ref_dose": result.get("ref_dose"),
                         "pct_min": result.get("pct_min"),
                         "pct_mean": result.get("pct_mean"),
                         "pct_max": result.get("pct_max")})
        if known_cgy:
            data["known_dose_cgy"] = known_cgy
        save_module(state, "dosemap", data)
    except Exception:
        pass
